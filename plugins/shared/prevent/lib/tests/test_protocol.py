import os
import json
import pytest

import lib.cache as cache
from lib.protocol import (
    HookInput,
    HookOutput,
    evaluate_pre_edit,
    evaluate_post_edit,
    evaluate_pre_commit,
    evaluate_turn_end,
    evaluate_validate_command,
    scan_transcript_for_markers,
    scan_history_jsonl_for_markers,
    scan_sidechain_transcripts_for_markers,
)


class TestScanTranscriptForMarkers:
    def test_marker_found(self, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('line1\n<!-- MC_IMPACT_CHECK_COMPLETE: orders -->\nline3\n')
        result = scan_transcript_for_markers(str(transcript), "orders")
        assert result["impact_check"] is True

    def test_marker_not_found(self, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('line1\nline2\n')
        result = scan_transcript_for_markers(str(transcript), "orders")
        assert result["impact_check"] is False

    def test_file_not_found(self):
        result = scan_transcript_for_markers("/nonexistent/path", "orders")
        assert result["impact_check"] is False

    def test_monitor_gap_marker(self, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('<!-- MC_MONITOR_GAP: orders -->\n<!-- MC_IMPACT_CHECK_COMPLETE: orders -->\n')
        result = scan_transcript_for_markers(str(transcript), "orders")
        assert result["impact_check"] is True
        assert result["monitor_gap"] is True

    def test_partial_table_name_no_match(self, tmp_path):
        """client_hub should not match client_hub_master."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('<!-- MC_IMPACT_CHECK_COMPLETE: client_hub -->\n')
        result = scan_transcript_for_markers(str(transcript), "client_hub_master")
        assert result["impact_check"] is False


def _cc_entry(entry_type, content, extra=None):
    """One Claude Code transcript line: author in "type", message nested."""
    entry = {"type": entry_type, "message": {"role": entry_type, "content": content}}
    entry.update(extra or {})
    return json.dumps(entry)


def _cc_assistant_text(text):
    return _cc_entry("assistant", [{"type": "text", "text": text}], {"isSidechain": True})


def _cc_tool_result(text):
    """A tool result — delivered under "user", where hook output is persisted."""
    return _cc_entry("user", [{"type": "tool_result", "content": text}],
                     {"isSidechain": True})


def _cc_session(tmp_path, session_id="sess1", main_lines=""):
    """Build a Claude Code project dir: main transcript + its subagents/ dir.

      <project>/<session_id>.jsonl
      <project>/<session_id>/subagents/agent-<agent_id>.jsonl
    """
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    main = project / f"{session_id}.jsonl"
    main.write_text(main_lines)
    sidechains = project / session_id / "subagents"
    sidechains.mkdir(parents=True, exist_ok=True)
    return main, sidechains


class TestScanSidechainTranscripts:
    """Sub-agent turns never reach the main transcript — their files count too."""

    def test_marker_found_for_acting_agent(self, tmp_path):
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            _cc_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: orders -->") + "\n")
        result = scan_sidechain_transcripts_for_markers(str(main), "orders", "a1")
        assert result["impact_check"] is True

    def test_marker_found_without_agent_id(self, tmp_path):
        """Harnesses that report no agent id still get the session-wide sweep."""
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            _cc_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: orders -->") + "\n")
        result = scan_sidechain_transcripts_for_markers(str(main), "orders")
        assert result["impact_check"] is True

    def test_unknown_agent_id_falls_back_to_sweep(self, tmp_path):
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            _cc_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: orders -->") + "\n")
        result = scan_sidechain_transcripts_for_markers(str(main), "orders", "nosuchagent")
        assert result["impact_check"] is True

    def test_nested_agent_found_by_id(self, tmp_path):
        """A sub-agent spawned by a sub-agent sits a directory deeper."""
        main, sidechains = _cc_session(tmp_path)
        nested = sidechains / "a1"
        nested.mkdir()
        (nested / "agent-a2.jsonl").write_text(
            _cc_assistant_text(
                "<!-- MC_MONITOR_GAP: orders --> <!-- MC_IMPACT_CHECK_COMPLETE: orders -->"
            ) + "\n")
        result = scan_sidechain_transcripts_for_markers(str(main), "orders", "a2")
        assert result["impact_check"] is True
        assert result["monitor_gap"] is True

    def test_marker_in_tool_result_does_not_count(self, tmp_path):
        """Only the model's own text may unlock the gate — not what was fed to it."""
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            _cc_tool_result("[Hook] ... MC_IMPACT_CHECK_COMPLETE: orders ...") + "\n")
        result = scan_sidechain_transcripts_for_markers(str(main), "orders", "a1")
        assert result["impact_check"] is False

    def test_no_marker_stays_false(self, tmp_path):
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            _cc_assistant_text("Reading the model file now.") + "\n")
        result = scan_sidechain_transcripts_for_markers(str(main), "orders", "a1")
        assert result == {"impact_check": False, "monitor_gap": False}

    def test_other_table_marker_does_not_match(self, tmp_path):
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            _cc_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: customers -->") + "\n")
        result = scan_sidechain_transcripts_for_markers(str(main), "orders", "a1")
        assert result["impact_check"] is False

    def test_no_sidechain_dir_returns_nothing(self, tmp_path):
        """Harnesses without sub-agent transcripts are unaffected."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(_cc_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: orders -->") + "\n")
        result = scan_sidechain_transcripts_for_markers(str(transcript), "orders", "a1")
        assert result == {"impact_check": False, "monitor_gap": False}

    def test_malformed_line_skipped_valid_line_still_found(self, tmp_path):
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            "this is not json\n"
            + _cc_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: orders -->") + "\n"
            + "{also not valid\n")
        result = scan_sidechain_transcripts_for_markers(str(main), "orders", "a1")
        assert result["impact_check"] is True

    def test_entries_missing_message_skipped(self, tmp_path):
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            json.dumps({"type": "assistant"}) + "\n"
            + json.dumps({"type": "assistant", "message": None}) + "\n"
            + json.dumps(["not", "a", "dict"]) + "\n")
        result = scan_sidechain_transcripts_for_markers(str(main), "orders", "a1")
        assert result == {"impact_check": False, "monitor_gap": False}


class TestDenyReasonSelfBypass:
    """The pre-edit deny reason must never contain a marker that its own
    scanner would match. Harnesses that persist hook output back into the
    transcript (e.g. Cortex records it as a tool_result) would otherwise let
    the gate falsely unlock itself after the first deny. This is the
    source-side guard and protects every harness's scanner.
    """

    def _deny_reason(self, tmp_path, dirname, filename, body):
        d = tmp_path / dirname
        d.mkdir()
        sql_file = d / filename
        sql_file.write_text(body)
        result = evaluate_pre_edit(
            HookInput(session_id="s1", file_path=str(sql_file), transcript_path="")
        )
        assert result.action == "deny"
        return result.reason

    def test_model_deny_reason_does_not_self_unlock_raw_line(self, tmp_path):
        reason = self._deny_reason(tmp_path, "models", "orders.sql",
                                   "SELECT * FROM {{ ref('raw') }}")
        transcript = tmp_path / "t.jsonl"
        transcript.write_text(reason + "\n")
        result = scan_transcript_for_markers(str(transcript), "orders")
        assert result["impact_check"] is False, \
            "deny reason must not satisfy the raw-line scanner (CC/Codex/Cursor/Copilot)"

    def test_macro_deny_reason_does_not_self_unlock_raw_line(self, tmp_path):
        reason = self._deny_reason(tmp_path, "macros", "helper.sql",
                                   "{% macro helper() %} SELECT 1 {% endmacro %}")
        transcript = tmp_path / "t.jsonl"
        transcript.write_text(reason + "\n")
        result = scan_transcript_for_markers(str(transcript), "macro:helper")
        assert result["impact_check"] is False

    def test_model_deny_reason_does_not_self_unlock_history_jsonl(self, tmp_path):
        """The same invariant for the Cortex JSONL scanner (the path this work added)."""
        reason = self._deny_reason(tmp_path, "models", "orders.sql",
                                   "SELECT * FROM {{ ref('raw') }}")
        # As Cortex actually persists it — a tool_result under role "user" (ignored).
        tr = tmp_path / "tr.history.jsonl"
        tr.write_text(_user_tool_result(reason) + "\n")
        assert scan_history_jsonl_for_markers(str(tr), "orders")["impact_check"] is False
        # And even if it somehow landed in an assistant text block, the wording must not match.
        at = tmp_path / "at.history.jsonl"
        at.write_text(_assistant_text(reason) + "\n")
        assert scan_history_jsonl_for_markers(str(at), "orders")["impact_check"] is False

    def test_macro_deny_reason_does_not_self_unlock_history_jsonl(self, tmp_path):
        reason = self._deny_reason(tmp_path, "macros", "helper.sql",
                                   "{% macro helper() %} SELECT 1 {% endmacro %}")
        at = tmp_path / "at.history.jsonl"
        at.write_text(_assistant_text(reason) + "\n")
        assert scan_history_jsonl_for_markers(str(at), "macro:helper")["impact_check"] is False

    def test_model_deny_reason_does_not_self_unlock_sidechain(self, tmp_path):
        """The same invariant for sub-agent transcripts: the deny reason lands there
        as a tool result, and must not unlock the gate it was emitted by."""
        reason = self._deny_reason(tmp_path, "models", "orders.sql",
                                   "SELECT * FROM {{ ref('raw') }}")
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(_cc_tool_result(reason) + "\n")
        assert scan_sidechain_transcripts_for_markers(
            str(main), "orders", "a1")["impact_check"] is False
        # And even if the wording were echoed back as assistant text, it must not match.
        (sidechains / "agent-a1.jsonl").write_text(_cc_assistant_text(reason) + "\n")
        assert scan_sidechain_transcripts_for_markers(
            str(main), "orders", "a1")["impact_check"] is False


class TestEvaluatePreEdit:
    def test_non_dbt_file_noop(self):
        inp = HookInput(session_id="s1", file_path="/project/scripts/hello.py")
        result = evaluate_pre_edit(inp)
        assert result.action == "noop"

    def test_dbt_model_first_edit_denies(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        sql_file = model_dir / "orders.sql"
        sql_file.write_text("SELECT * FROM {{ ref('raw') }}")

        inp = HookInput(session_id="s1", file_path=str(sql_file), transcript_path="")
        result = evaluate_pre_edit(inp)
        assert result.action == "deny"
        assert "impact assessment" in result.reason
        assert "orders" in result.reason

    def test_verified_state_noop(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        sql_file = model_dir / "orders.sql"
        sql_file.write_text("SELECT * FROM {{ ref('raw') }}")

        cache.mark_impact_check_injected("s1", "orders")
        cache.mark_impact_check_verified("s1", "orders")

        inp = HookInput(session_id="s1", file_path=str(sql_file))
        result = evaluate_pre_edit(inp)
        assert result.action == "noop"

    def test_injected_within_grace_no_marker_denies(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        sql_file = model_dir / "orders.sql"
        sql_file.write_text("SELECT * FROM {{ ref('raw') }}")

        cache.mark_impact_check_injected("s1", "orders")
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"content": "some other message"}\n')

        inp = HookInput(session_id="s1", file_path=str(sql_file), transcript_path=str(transcript))
        result = evaluate_pre_edit(inp)
        assert result.action == "deny"
        assert "not completed yet" in result.reason

    def test_injected_with_marker_noop(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        sql_file = model_dir / "orders.sql"
        sql_file.write_text("SELECT * FROM {{ ref('raw') }}")

        cache.mark_impact_check_injected("s1", "orders")
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('<!-- MC_IMPACT_CHECK_COMPLETE: orders -->\n')

        inp = HookInput(session_id="s1", file_path=str(sql_file), transcript_path=str(transcript))
        result = evaluate_pre_edit(inp)
        assert result.action == "noop"
        assert cache.get_impact_check_state("s1", "orders") == "verified"

    def test_new_file_noop(self, tmp_path):
        """Non-existent file (new model) should not be blocked."""
        inp = HookInput(session_id="s1", file_path=str(tmp_path / "models" / "new.sql"))
        result = evaluate_pre_edit(inp)
        assert result.action == "noop"

    def test_macro_file_denies_with_macro_message(self, tmp_path):
        macro_dir = tmp_path / "macros"
        macro_dir.mkdir()
        sql_file = macro_dir / "helper.sql"
        sql_file.write_text("{% macro helper() %} SELECT 1 {% endmacro %}")

        inp = HookInput(session_id="s1", file_path=str(sql_file), transcript_path="")
        result = evaluate_pre_edit(inp)
        assert result.action == "deny"
        assert "macro" in result.reason.lower()
        assert "helper" in result.reason


class TestEvaluatePreEditSubAgent:
    """A sub-agent must be able to satisfy the gate it was blocked by.

    Hook input reports the main session's id and transcript_path even when the
    edit comes from a sub-agent, whose turns are written to a separate file. With
    only the main transcript scanned, "injected" could never reach "verified":
    the edit was denied inside the grace period and the full instruction
    re-injected after it, with no way out.
    """

    def _model(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        sql_file = model_dir / "mixpanel_mcp_events.sql"
        sql_file.write_text("SELECT * FROM {{ ref('raw') }}")
        return sql_file

    def test_injected_with_marker_in_sidechain_verifies(self, tmp_path):
        sql_file = self._model(tmp_path)
        cache.mark_impact_check_injected("s1", "mixpanel_mcp_events")
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            _cc_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: mixpanel_mcp_events -->") + "\n")

        inp = HookInput(session_id="s1", file_path=str(sql_file),
                        transcript_path=str(main), agent_id="a1")
        result = evaluate_pre_edit(inp)
        assert result.action == "noop"
        assert cache.get_impact_check_state("s1", "mixpanel_mcp_events") == "verified"

    def test_state_none_with_marker_in_sidechain_verifies(self, tmp_path):
        sql_file = self._model(tmp_path)
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            _cc_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: mixpanel_mcp_events -->") + "\n")

        inp = HookInput(session_id="s1", file_path=str(sql_file),
                        transcript_path=str(main), agent_id="a1")
        result = evaluate_pre_edit(inp)
        assert result.action == "noop"
        assert cache.get_impact_check_state("s1", "mixpanel_mcp_events") == "verified"

    def test_monitor_gap_in_sidechain_recorded(self, tmp_path):
        sql_file = self._model(tmp_path)
        cache.mark_impact_check_injected("s1", "mixpanel_mcp_events")
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            _cc_assistant_text(
                "<!-- MC_MONITOR_GAP: mixpanel_mcp_events -->\n"
                "<!-- MC_IMPACT_CHECK_COMPLETE: mixpanel_mcp_events -->"
            ) + "\n")

        inp = HookInput(session_id="s1", file_path=str(sql_file),
                        transcript_path=str(main), agent_id="a1")
        assert evaluate_pre_edit(inp).action == "noop"
        assert cache.has_monitor_gap("s1", "mixpanel_mcp_events") is True

    def test_no_assessment_in_sidechain_still_denies(self, tmp_path):
        """The gate still holds: a sub-agent that skipped the assessment is blocked."""
        sql_file = self._model(tmp_path)
        cache.mark_impact_check_injected("s1", "mixpanel_mcp_events")
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            _cc_assistant_text("Editing the model now.") + "\n")

        inp = HookInput(session_id="s1", file_path=str(sql_file),
                        transcript_path=str(main), agent_id="a1")
        result = evaluate_pre_edit(inp)
        assert result.action == "deny"
        assert cache.get_impact_check_state("s1", "mixpanel_mcp_events") == "injected"

    def test_marker_for_other_table_in_sidechain_still_denies(self, tmp_path):
        sql_file = self._model(tmp_path)
        cache.mark_impact_check_injected("s1", "mixpanel_mcp_events")
        main, sidechains = _cc_session(tmp_path)
        (sidechains / "agent-a1.jsonl").write_text(
            _cc_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: some_other_model -->") + "\n")

        inp = HookInput(session_id="s1", file_path=str(sql_file),
                        transcript_path=str(main), agent_id="a1")
        assert evaluate_pre_edit(inp).action == "deny"

    def test_marker_in_main_transcript_still_works(self, tmp_path):
        """Main-loop edits keep verifying off the main transcript."""
        sql_file = self._model(tmp_path)
        cache.mark_impact_check_injected("s1", "mixpanel_mcp_events")
        main, _ = _cc_session(
            tmp_path,
            main_lines="<!-- MC_IMPACT_CHECK_COMPLETE: mixpanel_mcp_events -->\n")

        inp = HookInput(session_id="s1", file_path=str(sql_file), transcript_path=str(main))
        assert evaluate_pre_edit(inp).action == "noop"


class TestEvaluatePostEdit:
    def test_non_dbt_file_noop(self):
        inp = HookInput(session_id="s1", file_path="/project/readme.md")
        result = evaluate_post_edit(inp)
        assert result.action == "noop"
        assert cache.get_edited_tables("s1") == []

    def test_dbt_model_tracked(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        sql_file = model_dir / "orders.sql"
        sql_file.write_text("SELECT * FROM {{ ref('raw') }}")

        inp = HookInput(session_id="s1", file_path=str(sql_file))
        evaluate_post_edit(inp)
        assert cache.get_edited_tables("s1") == ["orders"]


class TestEvaluatePreCommit:
    def test_non_commit_noop(self):
        inp = HookInput(session_id="s1", command="ls -la")
        result = evaluate_pre_commit(inp)
        assert result.action == "noop"

    def test_commit_with_w4_tables_adds_context(self):
        cache.mark_impact_check_injected("s1", "orders")
        cache.mark_impact_check_verified("s1", "orders")

        from unittest.mock import patch
        inp = HookInput(session_id="s1", command="git commit -m 'test'", cwd="/project")
        with patch("lib.protocol._get_staged_model_tables", return_value=["orders"]):
            result = evaluate_pre_commit(inp)
        assert result.action == "context"
        assert "orders" in result.context
        assert "validation" in result.context.lower()

    def test_commit_no_staged_sql_noop(self):
        from unittest.mock import patch
        inp = HookInput(session_id="s1", command="git commit -m 'test'", cwd="/project")
        with patch("lib.protocol._get_staged_model_tables", return_value=[]):
            result = evaluate_pre_commit(inp)
        assert result.action == "noop"


class TestEvaluateTurnEnd:
    def test_no_edits_noop(self):
        inp = HookInput(session_id="s1")
        result = evaluate_turn_end(inp)
        assert result.action == "noop"

    def test_stop_hook_active_noop(self):
        cache.add_edited_table("s1", "orders")
        cache.mark_impact_check_injected("s1", "orders")
        inp = HookInput(session_id="s1", stop_hook_active=True)
        result = evaluate_turn_end(inp)
        assert result.action == "noop"

    def test_edits_with_w4_blocks(self):
        cache.add_edited_table("s1", "orders")
        cache.mark_impact_check_injected("s1", "orders")
        cache.mark_impact_check_verified("s1", "orders")

        inp = HookInput(session_id="s1")
        result = evaluate_turn_end(inp)
        assert result.action == "block"
        assert "orders" in result.reason
        assert "validation" in result.reason.lower()

    def test_moves_to_pending(self):
        cache.add_edited_table("s1", "orders")
        cache.mark_impact_check_injected("s1", "orders")
        cache.mark_impact_check_verified("s1", "orders")

        inp = HookInput(session_id="s1")
        evaluate_turn_end(inp)
        assert cache.get_edited_tables("s1") == []
        assert "orders" in cache.get_pending_validation_tables("s1")

    def test_pending_exists_merges_silently(self):
        cache.add_edited_table("s1", "orders")
        cache.move_to_pending_validation("s1")
        cache.add_edited_table("s1", "customers")
        cache.mark_impact_check_injected("s1", "customers")

        inp = HookInput(session_id="s1")
        result = evaluate_turn_end(inp)
        assert result.action == "noop"
        pending = cache.get_pending_validation_tables("s1")
        assert "orders" in pending
        assert "customers" in pending

    def test_edits_without_w4_noop(self):
        cache.add_edited_table("s1", "orders")
        inp = HookInput(session_id="s1")
        result = evaluate_turn_end(inp)
        assert result.action == "noop"


class TestMonitorGapCleared:
    def test_turn_end_clears_gap_after_prompting(self):
        session_id = "test_clear_turnend"
        cache.mark_impact_check_injected(session_id, "orders")
        cache.mark_monitor_gap(session_id, "orders")
        cache.add_edited_table(session_id, "orders")

        result = evaluate_turn_end(HookInput(session_id=session_id, validate_command="/mc-validate"))

        assert "monitor coverage" in result.reason.lower()
        assert cache.has_monitor_gap(session_id, "orders") is False, \
            "gap should be cleared after the prompt is delivered"

    def test_pre_commit_clears_gap_after_prompting(self, monkeypatch):
        import lib.protocol as protocol
        session_id = "test_clear_precommit"
        cache.mark_impact_check_verified(session_id, "orders")
        cache.mark_monitor_gap(session_id, "orders")

        monkeypatch.setattr(protocol, "_get_staged_model_tables", lambda cwd: ["orders"])

        result = evaluate_pre_commit(HookInput(
            session_id=session_id,
            command="git commit -m test",
            cwd=".",
        ))

        assert "monitor coverage" in result.context.lower()
        assert cache.has_monitor_gap(session_id, "orders") is False, \
            "gap should be cleared after the pre-commit prompt is delivered"

    def test_turn_end_does_not_clear_when_no_gap(self):
        session_id = "test_no_clear"
        cache.mark_impact_check_injected(session_id, "orders")
        cache.add_edited_table(session_id, "orders")

        # No gap marked
        result = evaluate_turn_end(HookInput(session_id=session_id, validate_command="/mc-validate"))

        # Should still prompt for validation (the main turn_end behavior)
        assert result.action == "block"
        # And no gap was created as a side-effect
        assert cache.has_monitor_gap(session_id, "orders") is False


class TestEvaluateValidateCommand:
    def test_no_tables_returns_context(self):
        inp = HookInput(session_id="s1")
        result = evaluate_validate_command(inp)
        assert result.action == "context"
        assert "No dbt model changes" in result.context

    def test_pending_tables_returns_instruction(self):
        cache.add_edited_table("s1", "orders")
        cache.move_to_pending_validation("s1")
        cache.mark_impact_check_injected("s1", "orders")
        cache.mark_impact_check_verified("s1", "orders")

        inp = HookInput(session_id="s1")
        result = evaluate_validate_command(inp)
        assert result.action == "context"
        assert "orders" in result.context
        assert "validation query workflow" in result.context


def _history_line(role, blocks):
    """Build one Anthropic Messages-style .history.jsonl line."""
    return json.dumps({"role": role, "content": blocks})


def _assistant_text(text):
    return _history_line("assistant", [{"type": "text", "text": text}])


def _user_tool_result(text):
    """A tool_result delivered under role 'user' — how Cortex persists hook output."""
    return _history_line("user", [{
        "type": "tool_result",
        "tool_result": {"content": [{"type": "text", "text": text}]},
    }])


class TestScanHistoryJsonl:
    """Cortex scans only assistant-authored text blocks of <id>.history.jsonl."""

    def test_marker_in_assistant_text_found(self, tmp_path):
        h = tmp_path / "s.history.jsonl"
        h.write_text(
            _assistant_text("Assessment complete. <!-- MC_IMPACT_CHECK_COMPLETE: orders -->\n") + "\n"
        )
        result = scan_history_jsonl_for_markers(str(h), "orders")
        assert result["impact_check"] is True

    def test_marker_in_tool_result_not_found(self, tmp_path):
        """The persisted hook deny reason lives in a tool_result (role user) and
        must NOT unlock the gate, even if it contains a verbatim marker."""
        h = tmp_path / "s.history.jsonl"
        h.write_text(_user_tool_result("[Hook] ... MC_IMPACT_CHECK_COMPLETE: orders ...") + "\n")
        result = scan_history_jsonl_for_markers(str(h), "orders")
        assert result["impact_check"] is False

    def test_monitor_gap_in_assistant_text_found(self, tmp_path):
        h = tmp_path / "s.history.jsonl"
        h.write_text(
            _assistant_text("<!-- MC_MONITOR_GAP: orders --> <!-- MC_IMPACT_CHECK_COMPLETE: orders -->") + "\n"
        )
        result = scan_history_jsonl_for_markers(str(h), "orders")
        assert result["impact_check"] is True
        assert result["monitor_gap"] is True

    def test_string_content_assistant_found(self, tmp_path):
        h = tmp_path / "s.history.jsonl"
        h.write_text(_history_line("assistant", "inline MC_IMPACT_CHECK_COMPLETE: orders here") + "\n")
        result = scan_history_jsonl_for_markers(str(h), "orders")
        assert result["impact_check"] is True

    def test_partial_table_name_no_match(self, tmp_path):
        h = tmp_path / "s.history.jsonl"
        h.write_text(_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: client_hub -->") + "\n")
        result = scan_history_jsonl_for_markers(str(h), "client_hub_master")
        assert result["impact_check"] is False

    # --- robustness: must fail closed, never raise ---

    def test_missing_file_not_found(self):
        result = scan_history_jsonl_for_markers("/nonexistent/s.history.jsonl", "orders")
        assert result == {"impact_check": False, "monitor_gap": False}

    def test_malformed_line_skipped_valid_line_still_found(self, tmp_path):
        h = tmp_path / "s.history.jsonl"
        h.write_text(
            "this is not json\n"
            + _assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: orders -->") + "\n"
            + "{also not valid\n"
        )
        result = scan_history_jsonl_for_markers(str(h), "orders")
        assert result["impact_check"] is True

    def test_lines_missing_role_or_content_skipped(self, tmp_path):
        h = tmp_path / "s.history.jsonl"
        h.write_text(
            json.dumps({"foo": "bar"}) + "\n"
            + json.dumps({"role": "assistant"}) + "\n"            # no content key
            + json.dumps({"role": "user", "content": None}) + "\n"
            + json.dumps(["not", "a", "dict"]) + "\n"
        )
        result = scan_history_jsonl_for_markers(str(h), "orders")
        assert result == {"impact_check": False, "monitor_gap": False}


class TestEvaluatePreEditCortex:
    """evaluate_pre_edit honors transcript_format='messages_jsonl' for Cortex."""

    def _model(self, tmp_path):
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        sql_file = model_dir / "orders.sql"
        sql_file.write_text("SELECT * FROM {{ ref('raw') }}")
        return sql_file

    def test_injected_with_marker_in_history_verifies(self, tmp_path):
        sql_file = self._model(tmp_path)
        cache.mark_impact_check_injected("s1", "orders")
        h = tmp_path / "s.history.jsonl"
        h.write_text(_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: orders -->") + "\n")

        inp = HookInput(session_id="s1", file_path=str(sql_file),
                        transcript_path=str(h), transcript_format="messages_jsonl")
        result = evaluate_pre_edit(inp)
        assert result.action == "noop"
        assert cache.get_impact_check_state("s1", "orders") == "verified"

    def test_state_none_with_marker_in_history_verifies(self, tmp_path):
        sql_file = self._model(tmp_path)
        h = tmp_path / "s.history.jsonl"
        h.write_text(_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: orders -->") + "\n")

        inp = HookInput(session_id="s1", file_path=str(sql_file),
                        transcript_path=str(h), transcript_format="messages_jsonl")
        result = evaluate_pre_edit(inp)
        assert result.action == "noop"
        assert cache.get_impact_check_state("s1", "orders") == "verified"

    def test_marker_only_in_tool_result_does_not_unlock(self, tmp_path):
        """End-to-end: a marker the gate itself emitted (persisted as a tool_result)
        must not unlock the gate — the edit stays denied within the grace period."""
        sql_file = self._model(tmp_path)
        cache.mark_impact_check_injected("s1", "orders")
        h = tmp_path / "s.history.jsonl"
        h.write_text(_user_tool_result("[Hook] ... MC_IMPACT_CHECK_COMPLETE: orders ...") + "\n")

        inp = HookInput(session_id="s1", file_path=str(sql_file),
                        transcript_path=str(h), transcript_format="messages_jsonl")
        result = evaluate_pre_edit(inp)
        assert result.action == "deny"
        assert cache.get_impact_check_state("s1", "orders") == "injected"

    def test_empty_transcript_path_denies(self, tmp_path):
        """Cortex format with no transcript yet (e.g. first turn) -> fail closed."""
        sql_file = self._model(tmp_path)
        inp = HookInput(session_id="s1", file_path=str(sql_file),
                        transcript_path="", transcript_format="messages_jsonl")
        assert evaluate_pre_edit(inp).action == "deny"

    def test_unknown_transcript_format_fails_closed(self, tmp_path):
        """A misspelled/unknown format must not unlock via the wrong scanner."""
        sql_file = self._model(tmp_path)
        cache.mark_impact_check_injected("s1", "orders")
        h = tmp_path / "s.history.jsonl"
        h.write_text(_assistant_text("<!-- MC_IMPACT_CHECK_COMPLETE: orders -->") + "\n")
        inp = HookInput(session_id="s1", file_path=str(sql_file),
                        transcript_path=str(h), transcript_format="messages-jsonl")  # typo
        assert evaluate_pre_edit(inp).action == "deny"
