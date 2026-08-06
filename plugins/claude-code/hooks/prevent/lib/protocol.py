"""Platform-agnostic hook decision logic.

All business logic for the prevent hooks lives here.
Platform adapters (Claude Code, Cursor) call these functions
and translate the result to their platform's JSON format.
"""
import glob
import json
import os
import re
import subprocess

from lib.cache import (
    add_edited_table,
    cleanup_stale_cache,
    clear_monitor_gap,
    get_edited_tables,
    get_impact_check_age_seconds,
    get_impact_check_state,
    get_pending_validation_tables,
    has_monitor_gap,
    mark_impact_check_injected,
    mark_impact_check_verified,
    mark_monitor_gap,
    move_to_pending_validation,
)
from lib.detect import extract_table_name, is_dbt_model, is_dbt_schema_file


# --- Data types ---

class HookInput:
    """Platform-agnostic hook input."""

    __slots__ = ("session_id", "file_path", "command", "transcript_path",
                 "cwd", "tool_name", "stop_hook_active", "validate_command",
                 "transcript_format", "agent_id")

    def __init__(
        self,
        session_id: str,
        file_path: str | None = None,
        command: str | None = None,
        transcript_path: str | None = None,
        cwd: str | None = None,
        tool_name: str | None = None,
        stop_hook_active: bool = False,
        validate_command: str = "/mc-validate",
        transcript_format: str = "raw",
        agent_id: str | None = None,
    ):
        self.session_id = session_id
        self.file_path = file_path
        self.command = command
        self.transcript_path = transcript_path
        self.cwd = cwd
        self.tool_name = tool_name
        self.stop_hook_active = stop_hook_active
        self.validate_command = validate_command
        # Set when the tool call comes from a sub-agent rather than the main
        # loop. Sub-agent turns are written to their own transcript, so the
        # marker scan needs the id to find the right file.
        self.agent_id = agent_id
        # Transcript layout this adapter produced: "raw" (line-scannable text,
        # the default for Claude Code/Cursor/Copilot/Codex) or "messages_jsonl"
        # (Cortex `.history.jsonl`, where only assistant text blocks are scanned).
        self.transcript_format = transcript_format


class HookOutput:
    """Platform-agnostic hook decision."""

    __slots__ = ("action", "reason", "context")

    def __init__(
        self,
        action: str = "noop",
        reason: str | None = None,
        context: str | None = None,
    ):
        self.action = action      # "deny", "context", "block", "noop"
        self.reason = reason
        self.context = context


# --- Shared helpers ---

GRACE_PERIOD_SECONDS = 120


def _compile_marker_patterns(table_name: str):
    """Compile the impact-check and monitor-gap regexes for a table.

    Matches the table name with an optional MCON-style prefix (e.g.
    "analytics:prod.client_hub") so markers work even if the model emits a fully
    qualified name instead of just "client_hub". The name must END the marker
    value: qualification is allowed before it, never after, so a marker for
    "prod.client_hub.events" does not satisfy the gate for "client_hub".
    """
    esc = re.escape(table_name)
    end = r"(?=\s|$)"
    return (
        re.compile(rf"MC_IMPACT_CHECK_COMPLETE:\s+(?:\S+\.)?{esc}{end}"),
        re.compile(rf"MC_MONITOR_GAP:\s+(?:\S+\.)?{esc}{end}"),
    )


def _match_markers_in_lines(lines, table_name: str) -> dict:
    """Run the marker regexes over an iterable of text lines/blocks."""
    ic_pattern, mg_pattern = _compile_marker_patterns(table_name)
    found = {"impact_check": False, "monitor_gap": False}
    for line in lines:
        if ic_pattern.search(line):
            found["impact_check"] = True
        if mg_pattern.search(line):
            found["monitor_gap"] = True
    return found


def _merge_markers(*results: dict) -> dict:
    """Union of marker results — a marker found in any scanned source counts."""
    return {key: any(r[key] for r in results)
            for key in ("impact_check", "monitor_gap")}


def scan_transcript_for_markers(transcript_path: str, table_name: str) -> dict:
    """Scan a plain-text / JSONL transcript line-by-line for prevent markers.

    Used by Claude Code, Cursor, Copilot, and Codex, whose transcripts can be
    scanned as raw text. Cortex uses scan_history_jsonl_for_markers instead.
    """
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            return _match_markers_in_lines(f, table_name)
    except (OSError, UnicodeDecodeError):
        return {"impact_check": False, "monitor_gap": False}


def _iter_assistant_text(content) -> list[str]:
    """Return text from assistant content blocks of type 'text'.

    Defensive against shape drift: tolerates a plain string, a list of blocks,
    or malformed entries (which are skipped).
    """
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    texts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                texts.append(text)
    return texts


def _scan_jsonl_assistant_text(path: str, table_name: str, extract_texts) -> dict:
    """Match markers against assistant-authored text in a JSONL transcript.

    `extract_texts` maps one parsed entry to the assistant text it holds, and
    returns nothing for anything the model didn't author (the prompt it was
    given, tool results). Restricting the match to assistant text ensures
    nothing but the model's own emitted marker can unlock the gate — harnesses
    persist hook output, including this gate's own deny reason, back into the
    transcript.

    Undecodable bytes are replaced (errors="replace") so a stray non-UTF-8 byte
    doesn't abort the scan and miss a genuine marker. Every failure is contained
    at the narrowest scope that can still make progress: a line that won't parse
    or extract is skipped and the rest of the file is still read; a file that
    won't open yields no markers. Both exception guards are deliberately broad —
    the gate must fail CLOSED, and anything escaping into the adapter's safe_run
    exits 0 and lets the edit through. Deeply nested JSON (RecursionError) and
    oversized lines (MemoryError) both take this route.
    """
    found = {"impact_check": False, "monitor_gap": False}
    ic_pattern, mg_pattern = _compile_marker_patterns(table_name)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                    if not isinstance(entry, dict):
                        continue
                    texts = extract_texts(entry)
                except Exception:
                    continue
                for text in texts:
                    if ic_pattern.search(text):
                        found["impact_check"] = True
                    if mg_pattern.search(text):
                        found["monitor_gap"] = True
    except Exception:
        pass
    return found


def _cortex_assistant_texts(entry: dict) -> list[str]:
    """Assistant text of one Cortex `.history.jsonl` entry.

    Each line is an Anthropic Messages-style object:
        {"role": "assistant", "content": [{"type": "text", "text": "..."}, ...]}
    Cortex persists hook output as a tool_result delivered under role "user",
    which this skips.
    """
    if entry.get("role") != "assistant":
        return []
    return _iter_assistant_text(entry.get("content"))


def scan_history_jsonl_for_markers(history_path: str, table_name: str) -> dict:
    """Scan a Cortex `<id>.history.jsonl` transcript for prevent markers."""
    return _scan_jsonl_assistant_text(history_path, table_name, _cortex_assistant_texts)


# Sub-agent (sidechain) turns are written to their own transcript files, keyed by
# the acting agent's id, under the session's own directory:
#   <transcript_dir>/<session_id>/subagents/[<parent_agent_id>/]agent-<agent_id>.jsonl
# Hook input reports the main session's id and transcript_path in both cases.
_SIDECHAIN_DIR = "subagents"
_JSONL_SUFFIX = ".jsonl"


def _under_dir(path: str, directory: str) -> bool:
    """True when `path` resolves to somewhere inside `directory`.

    Symlinks under the transcript directory would otherwise let a scan read
    another session's markers, so every candidate is checked after resolution.
    """
    try:
        root = os.path.realpath(directory)
        return os.path.commonpath([root, os.path.realpath(path)]) == root
    except (OSError, ValueError):
        return False


def _sidechain_transcripts(transcript_path: str, agent_id: str | None) -> list[str]:
    """Sub-agent transcript files belonging to a main transcript.

    Prefers the acting sub-agent's own file; nested sub-agents sit a directory
    deeper, so the id is matched anywhere below `subagents/`. `agent_id` is
    escaped before it reaches the pattern — it comes from the harness payload,
    and a raw glob metacharacter there would select files the caller never named.
    Falls back to every sidechain of the session when the id doesn't resolve.
    Every candidate must resolve inside the session's own directory.
    Returns nothing for harnesses that don't write sidechains.
    """
    if not transcript_path.endswith(_JSONL_SUFFIX):
        return []
    session_dir = transcript_path[: -len(_JSONL_SUFFIX)]
    sidechain_dir = os.path.join(session_dir, _SIDECHAIN_DIR)
    if not os.path.isdir(sidechain_dir):
        return []

    def contained(paths):
        return [p for p in paths if os.path.isfile(p) and _under_dir(p, sidechain_dir)]

    if agent_id:
        own_name = f"agent-{glob.escape(str(agent_id))}{_JSONL_SUFFIX}"
        flat = os.path.join(sidechain_dir, own_name)
        if os.path.isfile(flat) and _under_dir(flat, sidechain_dir):
            return [flat]
        own = contained(glob.glob(os.path.join(sidechain_dir, "**", own_name), recursive=True))
        if own:
            return own
    # Newest first: the acting sub-agent wrote most recently, so the marker is
    # usually in the first file and the scan stops before reading the rest.
    sweep = contained(
        glob.glob(os.path.join(sidechain_dir, "**", f"*{_JSONL_SUFFIX}"), recursive=True))
    return sorted(sweep, key=lambda p: (-os.path.getmtime(p), p))


def _claude_code_assistant_texts(entry: dict) -> list[str]:
    """Assistant text of one Claude Code transcript entry.

    Entries wrap an Anthropic Messages-style object under "message" and carry the
    author in a top-level "type":
        {"type": "assistant", "message": {"content": [{"type": "text", ...}]}}
    """
    if entry.get("type") != "assistant":
        return []
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    return _iter_assistant_text(message.get("content"))


def scan_sidechain_transcripts_for_markers(
    transcript_path: str, table_name: str, agent_id: str | None = None,
) -> dict:
    """Scan a session's sub-agent transcripts for prevent markers."""
    found = {"impact_check": False, "monitor_gap": False}
    for path in _sidechain_transcripts(transcript_path, agent_id):
        found = _merge_markers(
            found,
            _scan_jsonl_assistant_text(path, table_name, _claude_code_assistant_texts),
        )
        if found["impact_check"] and found["monitor_gap"]:
            break
    return found


def _scan_markers(inp: "HookInput", table_name: str) -> dict:
    """Dispatch to the right transcript scanner for the harness's format.

    Adapters that store messages in an Anthropic Messages-style `.history.jsonl`
    (Cortex) set inp.transcript_format == "messages_jsonl" and point
    transcript_path at that sibling file. "raw" (the default) uses the raw-line
    scan over the main transcript. A sub-agent's turns are written to their own
    file, so when the caller is a sub-agent (inp.agent_id is set) its sidechains
    are scanned too. A main-loop edit reports no agent_id and its own transcript
    is the whole surface: the evidence must sit in the context window of the
    agent doing the editing. An unrecognized format (e.g. a future
    adapter's typo) deliberately returns no markers so the gate stays denied —
    failing CLOSED rather than silently scanning with the wrong reader (which
    would drop the assistant-text protection) or raising (which fails OPEN, since
    the adapter's safe_run exits 0).
    """
    no_markers = {"impact_check": False, "monitor_gap": False}
    path = inp.transcript_path or ""
    if not path:
        return no_markers
    if inp.transcript_format == "messages_jsonl":
        return scan_history_jsonl_for_markers(path, table_name)
    if inp.transcript_format == "raw":
        main = scan_transcript_for_markers(path, table_name)
        if not inp.agent_id:
            return main
        return _merge_markers(
            main,
            scan_sidechain_transcripts_for_markers(path, table_name, inp.agent_id),
        )
    return no_markers  # unknown format → fail closed


def _get_staged_model_tables(cwd: str) -> list[str]:
    """Get table names from staged dbt SQL files using the detect library."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        tables = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            full_path = os.path.join(cwd, line)
            if is_dbt_model(full_path):
                tables.append(extract_table_name(full_path))
        return tables
    except (subprocess.SubprocessError, OSError):
        return []


# --- Decision functions ---

def _prevent_hooks_disabled() -> bool:
    return os.environ.get("MC_PREVENT_HOOKS_DISABLED", "").strip() == "1"


def evaluate_pre_edit(inp: HookInput) -> HookOutput:
    """Gate logic: should this file edit be allowed?

    Returns deny if impact assessment hasn't run for this table,
    noop if the edit should proceed.
    """
    if _prevent_hooks_disabled():
        return HookOutput()
    cleanup_stale_cache()

    file_path = inp.file_path or ""
    if not is_dbt_model(file_path):
        return HookOutput()

    # New models have no blast radius — don't block
    if not os.path.exists(file_path):
        return HookOutput()

    session_id = inp.session_id
    table_name = extract_table_name(file_path)
    state = get_impact_check_state(session_id, table_name)

    if state == "verified":
        return HookOutput()

    if state == "injected":
        markers = _scan_markers(inp, table_name)
        if markers["monitor_gap"] and not has_monitor_gap(session_id, table_name):
            mark_monitor_gap(session_id, table_name)
        if markers["impact_check"]:
            mark_impact_check_verified(session_id, table_name)
            return HookOutput()
        # Assessment not completed — block without re-injecting if within grace period
        age = get_impact_check_age_seconds(session_id, table_name)
        if age < GRACE_PERIOD_SECONDS:
            reason = (
                f"Monte Carlo Prevent: the impact assessment for {table_name} "
                f"has not completed yet. Complete the assessment before editing this file."
            )
            return HookOutput(action="deny", reason=reason)
        # Grace period expired and no marker — re-inject full instruction below

    elif state is None:
        markers = _scan_markers(inp, table_name)
        if markers["monitor_gap"] and not has_monitor_gap(session_id, table_name):
            mark_monitor_gap(session_id, table_name)
        if markers["impact_check"]:
            mark_impact_check_verified(session_id, table_name)
            return HookOutput()

    # No marker or failed verification — block the edit
    mark_impact_check_injected(session_id, table_name)

    # The marker is shown as a `MC_IMPACT_CHECK_COMPLETE: <table>` template with a
    # separate substitution note rather than interpolating the table name directly
    # after the token. This keeps the rendered deny reason from satisfying the gate's
    # own scanner — harnesses that persist hook output back into the transcript (e.g.
    # Cortex records it as a tool_result) would otherwise let the gate self-unlock.
    hook_triggered_note = (
        "This assessment is hook-triggered — only emit MC_IMPACT_CHECK_COMPLETE "
        "markers for tables whose lineage and monitor coverage were fetched "
        "directly via Monte Carlo tools. When complete, emit the completion marker "
        "on its own line in the form `MC_IMPACT_CHECK_COMPLETE: <table>`, replacing "
        f"<table> with the bare table name {table_name}."
    )

    no_bypass_note = (
        "IMPORTANT: Do NOT bypass this check by using shell commands, git apply, "
        "or any other workaround. If Monte Carlo MCP tools are not available in "
        "this session, ask the user to authenticate the Monte Carlo MCP server "
        "in their editor settings before proceeding."
    )

    workflow_order_note = (
        "If Workflow 1 (asset-health pre-fetch) has not yet run for this table "
        "this session, run it first via the Skill tool to gather lineage / alerts "
        "/ monitors as data for the impact assessment. Read W1's report as data "
        "and do NOT relay it to the engineer — only surface a disambiguation "
        "prompt (if asset-health asks which match to use) or a one-line "
        "stop-the-world warning (active critical alerts, severe staleness). "
        "Then run Workflow 2 (change impact assessment), reusing the asset-health "
        "data rather than re-fetching. Workflow 2 is the user-facing artifact. "
        "If Workflow 1 already ran for this table, skip directly to Workflow 2."
    )

    if table_name.startswith("macro:"):
        macro_name = table_name.removeprefix("macro:")
        reason = (
            f"Monte Carlo Prevent: this macro ({macro_name}) is inlined into "
            f"models at compile time — changes here affect every model that calls it. "
            f"Identify which models use this macro, then run the change impact "
            f"assessment for the affected models before editing this file. "
            f"{workflow_order_note} {hook_triggered_note} {no_bypass_note}"
        )
    else:
        reason = (
            f"Monte Carlo Prevent: run the change impact assessment "
            f"for {table_name} before editing this file. Present the full "
            f"impact report and synthesis step, then ask the user whether to proceed before retrying the edit. "
            f"{workflow_order_note} {hook_triggered_note} {no_bypass_note}"
        )

    return HookOutput(action="deny", reason=reason)


def evaluate_post_edit(inp: HookInput) -> HookOutput:
    """Track which tables were edited. Always returns noop (silent)."""
    file_path = inp.file_path or ""
    if not is_dbt_model(file_path) and not is_dbt_schema_file(file_path):
        return HookOutput()

    table_name = extract_table_name(file_path)
    add_edited_table(inp.session_id, table_name)
    return HookOutput()


def evaluate_pre_commit(inp: HookInput) -> HookOutput:
    """Commit checkpoint: prompt for validation if dbt models are staged."""
    if _prevent_hooks_disabled():
        return HookOutput()
    command = inp.command or ""
    if "git commit" not in command:
        return HookOutput()

    cwd = inp.cwd or "."
    staged_tables = _get_staged_model_tables(cwd)
    if not staged_tables:
        return HookOutput()

    w4_tables = [t for t in staged_tables
                 if get_impact_check_state(inp.session_id, t) == "verified"]
    if not w4_tables:
        return HookOutput()

    table_list = ", ".join(w4_tables)
    gap_tables = [t for t in w4_tables if has_monitor_gap(inp.session_id, t)]

    message = (
        f"Committing changes to {table_list}. "
        f"Run validation queries before committing? (yes / no)"
    )
    if gap_tables:
        gap_list = ", ".join(gap_tables)
        message += (
            f"\n\nMonitor coverage: the impact assessment found no custom monitors "
            f"on {gap_list}. Generate monitor definitions before committing? (yes / no)"
        )
        for t in gap_tables:
            clear_monitor_gap(inp.session_id, t)

    return HookOutput(action="context", context=message)


def evaluate_turn_end(inp: HookInput) -> HookOutput:
    """End of turn: prompt for validation queries if dbt models were edited."""
    if _prevent_hooks_disabled():
        return HookOutput()
    if inp.stop_hook_active:
        return HookOutput()

    session_id = inp.session_id
    tables = get_edited_tables(session_id)
    if not tables:
        return HookOutput()

    if get_pending_validation_tables(session_id):
        move_to_pending_validation(session_id)
        return HookOutput()

    w4_tables = [t for t in tables
                 if get_impact_check_state(session_id, t) in ("injected", "verified")]
    if not w4_tables:
        return HookOutput()

    gap_tables = [t for t in tables if has_monitor_gap(session_id, t)]

    table_list = ", ".join(tables)
    count = len(tables)
    reason = (
        f"You've changed {count} dbt model(s): {table_list}. "
        f"ASK THE USER whether they would like to run validation queries to "
        f"verify these changes behaved as intended. Present these options and "
        f"WAIT for the user to respond — do NOT answer on their behalf:\n\n"
        f"→ Yes: I'll generate and run queries for all changed models\n"
        f"→ No: You can use {inp.validate_command} anytime to validate changes"
    )
    if gap_tables:
        gap_list = ", ".join(gap_tables)
        reason += (
            f"\n\nAlso ask about monitor coverage: the impact assessment found no "
            f"custom monitors on {gap_list}. Ask the user whether they would like "
            f"to generate monitor definitions:\n\n"
            f"→ Yes: I'll suggest monitors for the new or changed logic\n"
            f"→ No: Skip for now"
        )
        for t in gap_tables:
            clear_monitor_gap(session_id, t)

    move_to_pending_validation(session_id)
    return HookOutput(action="block", reason=reason)


def evaluate_validate_command(inp: HookInput) -> HookOutput:
    """Handle /mc-validate slash command."""
    session_id = inp.session_id

    tables = get_pending_validation_tables(session_id)
    if not tables:
        tables = get_edited_tables(session_id)

    if not tables:
        return HookOutput(
            action="context",
            context=f"No dbt model changes detected in this session. Edit a dbt model first, then run {inp.validate_command}.",
        )

    w4_tables = [t for t in tables
                 if get_impact_check_state(session_id, t) == "verified"]
    if not w4_tables:
        w4_tables = tables

    table_list = ", ".join(w4_tables)
    return HookOutput(
        action="context",
        context=(
            f"Generate validation queries for: {table_list}. "
            f"Use the validation query workflow from the Monte Carlo Prevent skill. "
            f"Save queries to validation/<table_name>_<timestamp>.sql."
        ),
    )
