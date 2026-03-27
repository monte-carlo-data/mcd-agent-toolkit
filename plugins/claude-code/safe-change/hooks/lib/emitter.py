"""Event assembly and non-blocking emission to Monte Carlo.

Assembles change events from local cache state and sends them via a daemon
thread POST. Never blocks the hook, never throws to the caller.
"""
import json
import os
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone

MC_CHANGE_EVENTS_URL = os.environ.get(
    "MC_CHANGE_EVENTS_URL",
    "https://integrations.getmontecarlo.com/plugin/change-events",
)


def _get_git_identity():
    """Read git user.email and user.name via subprocess."""
    try:
        email = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        name = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return {"git_email": email, "git_name": name}
    except Exception:
        return {"git_email": "", "git_name": ""}


from lib.cache import (
    get_impact_check_state,
    get_last_commit_hash,
    get_pending_validation_tables,
    has_monitor_gap,
    set_last_commit_hash,
)


INTENT_MAX_LENGTH = 256


def _get_current_head():
    """Return current HEAD commit hash, or None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _get_commit_message():
    """Return the latest commit's subject line."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _get_first_user_message(transcript_path):
    """Read the first human-authored user message from a JSONL transcript.

    Claude Code transcript format:
      {"type":"user","message":{"role":"user","content":"the user's message"}}

    Skips system-generated entries (local-command-caveat, /plugin commands).
    """
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "user":
                    continue
                msg = entry.get("message", {})
                content = msg.get("content", "") if isinstance(msg, dict) else ""
                # Skip system-injected messages (hooks, plugin commands)
                if content.startswith("<"):
                    continue
                if content:
                    return content[:INTENT_MAX_LENGTH]
    except (OSError, UnicodeDecodeError):
        pass
    return None


def _extract_intent(session_id, transcript_path):
    """Try commit message first, fall back to transcript user message.

    Returns: {"summary": str, "source": "commit_message"|"transcript"} or None
    """
    current_head = _get_current_head()
    prior_head = get_last_commit_hash(session_id)

    # Always update cached hash for next comparison
    if current_head:
        set_last_commit_hash(session_id, current_head)

    # Source 1: commit message (if HEAD changed since last emit)
    if current_head and prior_head and current_head != prior_head:
        message = _get_commit_message()
        if message:
            return {"summary": message[:INTENT_MAX_LENGTH], "source": "commit_message"}

    # Source 2: transcript (first user message)
    user_msg = _get_first_user_message(transcript_path)
    if user_msg:
        return {"summary": user_msg, "source": "transcript"}

    # Source 3: None
    return None


def _extract_workflow_flags(session_id, edited_tables):
    """Derive workflow boolean flags from cache state."""
    ic_states = {t: get_impact_check_state(session_id, t) for t in edited_tables}
    has_pending = bool(get_pending_validation_tables(session_id))
    w4_tables = [t for t in edited_tables if ic_states[t] in ("injected", "verified")]

    return {
        "impact_check_fired": any(s is not None for s in ic_states.values()),
        "edit_gated": any(s in ("injected", "verified") for s in ic_states.values()),
        "validation_prompted": not has_pending and len(w4_tables) > 0,
        "validation_generated": None,
        "monitor_gap_detected": any(has_monitor_gap(session_id, t) for t in edited_tables),
        "monitor_generated": None,
    }


import re

_IMPACT_DATA_RE = re.compile(r"MC_IMPACT_DATA:\s*(\{.*?\})")


def _scan_impact_data(transcript_path):
    """Scan transcript for MC_IMPACT_DATA markers, return dict keyed by table name.

    Marker format (inside assistant message content):
      <!-- MC_IMPACT_DATA: {"table":"orders","risk_tier":"high",...} -->

    Parses JSONL first to extract content, then searches content for markers.
    This avoids issues with JSON-escaped quotes in raw JSONL lines.

    Returns: {"orders": {"risk_tier": "high", "downstream_count": 42, ...}, ...}
    """
    results = {}
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = entry.get("message", {})
                content = msg.get("content", "") if isinstance(msg, dict) else ""
                if not content:
                    continue
                for match in _IMPACT_DATA_RE.finditer(content):
                    try:
                        data = json.loads(match.group(1))
                        table = data.pop("table", None)
                        if table:
                            results[table] = data
                    except (json.JSONDecodeError, AttributeError):
                        continue
    except (OSError, UnicodeDecodeError):
        pass
    return results


def _build_changes(edited_tables, impact_data):
    """Build the changes array, enriching with impact data where available."""
    changes = []
    for t in edited_tables:
        entry = {"table_name": t}
        if t in impact_data:
            entry["assessment"] = impact_data[t]
        changes.append(entry)
    return changes


def _build_event(session_id, transcript_path, edited_tables):
    """Assemble the change event from local cache state."""
    impact_data = _scan_impact_data(transcript_path)
    return {
        "event_type": "safe_change.turn_completed",
        "event_version": "1.0",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session_id": session_id,
        "identity": _get_git_identity(),
        "changes": _build_changes(edited_tables, impact_data),
        "workflows": _extract_workflow_flags(session_id, edited_tables),
        "intent": _extract_intent(session_id, transcript_path),
    }


def _send(event):
    """POST to MC API via a detached subprocess. Never blocks the caller.

    Hooks run as short-lived subprocesses, so daemon threads get killed before
    completing. Instead, we spawn a detached Python subprocess that outlives
    the hook process and sends the HTTP request independently.
    """
    try:
        payload = json.dumps(event)
        # Inline script reads event JSON from stdin and POSTs it
        script = ";".join([
            "import json,urllib.request,sys",
            "d=sys.stdin.buffer.read()",
            "urllib.request.urlopen(urllib.request.Request("
            "url=sys.argv[1],"
            "data=d,"
            "headers={'Content-Type':'application/json','x-mcd-id':sys.argv[2],'x-mcd-token':sys.argv[3]},"
            "method='POST'),timeout=3)",
        ])
        proc = subprocess.Popen(
            [
                "python3", "-c", script,
                MC_CHANGE_EVENTS_URL,
                os.environ.get("MCD_ID", ""),
                os.environ.get("MCD_TOKEN", ""),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # detach from parent process
        )
        proc.stdin.write(payload.encode())
        proc.stdin.close()
    except Exception:
        pass


_EMIT_MIN_INTERVAL = 5  # seconds — prevent tight-loop flooding
_EMIT_MARKER_PREFIX = "mc_safe_change_emit_"


def _rate_limit_ok(session_id):
    """Return True if enough time has passed since the last emit for this session."""
    path = os.path.join("/tmp", f"{_EMIT_MARKER_PREFIX}{session_id}")
    now = time.time()
    try:
        if os.path.exists(path):
            if now - os.path.getmtime(path) < _EMIT_MIN_INTERVAL:
                return False
    except OSError:
        pass
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, str(now).encode())
        finally:
            os.close(fd)
    except OSError:
        pass
    return True


def emit(session_id, transcript_path, edited_tables):
    """Assemble event and send in background thread. Never blocks, never throws.

    Modes (via MC_EMIT_EVENTS env var):
      "1" / "true" / unset  -> build event, POST in daemon thread (default)
      "dry_run"             -> build event, print JSON to stderr, no HTTP call
      "0" / "false" / "no"  -> skip entirely
    """
    try:
        mode = os.environ.get("MC_EMIT_EVENTS", "1").lower()
        if mode in ("0", "false", "no"):
            return
        if not os.environ.get("MCD_ID"):
            return
        if not _rate_limit_ok(session_id):
            return
        event = _build_event(session_id, transcript_path, edited_tables)
        if mode == "dry_run":
            import sys as _sys
            print(json.dumps(event, indent=2), file=_sys.stderr)
            return
        _send(event)
    except Exception:
        pass
