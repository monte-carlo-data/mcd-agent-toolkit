import json
import pytest
from unittest.mock import patch
from io import StringIO

import lib.cache as cache


def _make_stdin(session_id="test_session", stop_hook_active=False):
    return json.dumps({
        "session_id": session_id,
        "transcript_path": "/tmp/test_transcript.jsonl",
        "cwd": "/project",
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
        "last_assistant_message": "Done editing.",
    })


class TestTurnEndHook:
    def test_no_edits_silent(self, capsys):
        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin())):
            main()
        assert capsys.readouterr().out == ""

    def test_edits_without_impact_check_silent(self, capsys):
        """Edits without impact assessment should not prompt."""
        cache.add_edited_table("test_session", "orders")

        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin())):
            main()
        assert capsys.readouterr().out == ""

    def test_edits_with_impact_check_prompts(self, capsys):
        """Edits + impact assessment verified should produce validation prompt."""
        cache.add_edited_table("test_session", "orders")
        cache.mark_impact_check_injected("orders")
        cache.mark_impact_check_verified("orders")

        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin())):
            main()

        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert parsed["decision"] == "block"
        assert "orders" in parsed["reason"]
        assert "validation" in parsed["reason"].lower()

    def test_stop_hook_active_exits_silently(self, capsys):
        """If stop_hook_active is true, exit silently to prevent infinite loop."""
        cache.add_edited_table("test_session", "orders")
        cache.mark_impact_check_injected("orders")
        cache.mark_impact_check_verified("orders")

        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin(stop_hook_active=True))):
            main()

        assert capsys.readouterr().out == ""

    def test_moves_to_pending_validation(self, capsys):
        """After prompting, tables should move to pending validation."""
        cache.add_edited_table("test_session", "orders")
        cache.mark_impact_check_injected("orders")
        cache.mark_impact_check_verified("orders")

        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin())):
            main()

        assert cache.get_edited_tables("test_session") == []
        assert "orders" in cache.get_pending_validation_tables("test_session")

    def test_multiple_tables_in_prompt(self, capsys):
        cache.add_edited_table("test_session", "orders")
        cache.add_edited_table("test_session", "customers")
        cache.mark_impact_check_injected("orders")
        cache.mark_impact_check_verified("orders")

        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin())):
            main()

        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert "2" in parsed["reason"]  # "2 dbt model(s)"
        assert "orders" in parsed["reason"]
        assert "customers" in parsed["reason"]

    def test_pending_validation_exists_merges_silently(self, capsys):
        """When pending validation already exists, new edits merge silently — no re-prompt."""
        # Simulate first prompt: orders was prompted and moved to pending
        cache.add_edited_table("test_session", "orders")
        cache.move_to_pending_validation("test_session")
        cache.mark_impact_check_injected("orders")
        cache.mark_impact_check_verified("orders")

        # Simulate second turn: new model edited + validation files detected
        cache.add_edited_table("test_session", "client_hub_master")
        cache.mark_impact_check_injected("client_hub_master")
        cache.mark_impact_check_verified("client_hub_master")

        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin())):
            main()

        # Should NOT prompt again
        assert capsys.readouterr().out == ""

        # New tables should be merged into pending
        pending = cache.get_pending_validation_tables("test_session")
        assert "orders" in pending
        assert "client_hub_master" in pending

        # Turn should be cleared
        assert cache.get_edited_tables("test_session") == []

    def test_edits_with_only_injected_state_prompts(self, capsys):
        """Edits with 'injected' state should prompt (assessment was triggered)."""
        cache.add_edited_table("test_session", "orders")
        cache.mark_impact_check_injected("orders")

        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin())):
            main()

        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert parsed["decision"] == "block"
        assert "orders" in parsed["reason"]

    def test_emitter_called_when_tables_edited(self, capsys):
        """Emitter should fire whenever tables were edited in this turn."""
        cache.add_edited_table("test_session", "orders")
        cache.mark_impact_check_injected("orders")
        cache.mark_impact_check_verified("orders")

        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin())):
            with patch("lib.emitter.emit") as mock_emit:
                main()

        mock_emit.assert_called_once_with(
            "test_session",
            "/tmp/test_transcript.jsonl",
            ["orders"],
        )

    def test_emitter_called_on_silent_merge(self, capsys):
        """Emitter fires even when turn merges silently into pending."""
        cache.add_edited_table("test_session", "orders")
        cache.move_to_pending_validation("test_session")
        cache.add_edited_table("test_session", "customers")

        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin())):
            with patch("lib.emitter.emit") as mock_emit:
                main()

        mock_emit.assert_called_once_with(
            "test_session",
            "/tmp/test_transcript.jsonl",
            ["customers"],
        )

    def test_emitter_not_called_when_no_tables(self, capsys):
        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin())):
            with patch("lib.emitter.emit") as mock_emit:
                main()

        mock_emit.assert_not_called()

    def test_emitter_not_called_when_stop_hook_active(self, capsys):
        cache.add_edited_table("test_session", "orders")

        from turn_end_hook import main
        with patch("sys.stdin", StringIO(_make_stdin(stop_hook_active=True))):
            with patch("lib.emitter.emit") as mock_emit:
                main()

        mock_emit.assert_not_called()
