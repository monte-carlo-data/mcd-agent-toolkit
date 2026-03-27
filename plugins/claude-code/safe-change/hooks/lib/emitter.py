"""Event assembly and non-blocking emission to Monte Carlo.

Assembles change events from local cache state and sends them via a daemon
thread POST. Never blocks the hook, never throws to the caller.
"""
import json
import os
import subprocess
import threading
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
    """Read the first user message from a JSONL transcript."""
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("role") == "user":
                    msg = entry.get("message", "")
                    return msg[:INTENT_MAX_LENGTH] if msg else None
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
    ic_states = {t: get_impact_check_state(t) for t in edited_tables}
    has_pending = bool(get_pending_validation_tables(session_id))
    w4_tables = [t for t in edited_tables if ic_states[t] in ("injected", "verified")]

    return {
        "impact_check_fired": any(s is not None for s in ic_states.values()),
        "edit_gated": any(s in ("injected", "verified") for s in ic_states.values()),
        "validation_prompted": not has_pending and len(w4_tables) > 0,
        "validation_generated": None,
        "monitor_gap_detected": any(has_monitor_gap(t) for t in edited_tables),
        "monitor_generated": None,
    }
