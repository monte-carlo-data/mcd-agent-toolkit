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
    qualified name instead of just "client_hub".
    """
    esc = re.escape(table_name)
    return (
        re.compile(rf"MC_IMPACT_CHECK_COMPLETE:\s+(?:\S+\.)?{esc}\b"),
        re.compile(rf"MC_MONITOR_GAP:\s+(?:\S+\.)?{esc}\b"),
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

    Malformed (non-JSON) lines are skipped, and undecodable bytes are replaced
    (errors="replace") so a stray non-UTF-8 byte doesn't abort the whole scan and
    miss a genuine marker. Worst case the scan finds no marker and the gate stays
    denied (fail closed) rather than raising into the adapter's safe_run (which
    would exit 0 and let the edit through).
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
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(entry, dict):
                    continue
                for text in extract_texts(entry):
                    if ic_pattern.search(text):
                        found["impact_check"] = True
                    if mg_pattern.search(text):
                        found["monitor_gap"] = True
    except (OSError, UnicodeDecodeError):
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


# Sub-agent (sidechain) turns are written to their own transcript files and never
# into the main one:
#   <transcript_dir>/<session_id>/subagents/[<parent_agent_id>/]agent-<agent_id>.jsonl
# Hook input still reports the main session's id and transcript_path, so a marker
# a sub-agent emitted is invisible to a scan of the main transcript alone.
_SIDECHAIN_DIR = "subagents"
_JSONL_SUFFIX = ".jsonl"


def _sidechain_transcripts(transcript_path: str, agent_id: str | None) -> list[str]:
    """Sub-agent transcript files belonging to a main transcript.

    Prefers the acting sub-agent's own file when `agent_id` is known; nested
    sub-agents sit a directory deeper, so the id is matched anywhere below
    `subagents/`. Falls back to every sidechain of the session when no id was
    reported or it doesn't resolve — a marker there is still scoped to this
    session and this table, the same scope the main-transcript scan accepts.
    Returns nothing for harnesses that don't write sidechains, leaving their
    behavior unchanged.
    """
    if not transcript_path.endswith(_JSONL_SUFFIX):
        return []
    session_dir = transcript_path[: -len(_JSONL_SUFFIX)]
    sidechain_dir = os.path.join(session_dir, _SIDECHAIN_DIR)
    if not os.path.isdir(sidechain_dir):
        return []
    if agent_id:
        own = glob.glob(os.path.join(sidechain_dir, "**", f"agent-{agent_id}{_JSONL_SUFFIX}"),
                        recursive=True)
        if own:
            return own
    return sorted(glob.glob(os.path.join(sidechain_dir, "**", f"*{_JSONL_SUFFIX}"),
                            recursive=True))


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
    scan, plus the session's sub-agent transcripts — a sub-agent's turns never
    reach the main transcript, so without them an assessment run inside a
    sub-agent can never satisfy the gate. An unrecognized format (e.g. a future
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
        return _merge_markers(
            scan_transcript_for_markers(path, table_name),
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
