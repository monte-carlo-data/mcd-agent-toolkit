import json
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

from lib.emitter import _get_git_identity


class TestGetGitIdentity:
    def test_returns_email_and_name(self):
        with patch("lib.emitter.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(stdout="alice@company.com\n", returncode=0),
                MagicMock(stdout="Alice Chen\n", returncode=0),
            ]
            result = _get_git_identity()
        assert result == {"git_email": "alice@company.com", "git_name": "Alice Chen"}

    def test_returns_empty_on_failure(self):
        with patch("lib.emitter.subprocess.run", side_effect=Exception("no git")):
            result = _get_git_identity()
        assert result == {"git_email": "", "git_name": ""}


import lib.cache as cache
from lib.emitter import _extract_workflow_flags


class TestExtractWorkflowFlags:
    def test_no_ic_no_gaps(self):
        """Tables edited but no IC triggered, no monitor gaps."""
        result = _extract_workflow_flags("sess1", ["orders"])
        assert result == {
            "impact_check_fired": False,
            "edit_gated": False,
            "validation_prompted": False,
            "validation_generated": None,
            "monitor_gap_detected": False,
            "monitor_generated": None,
        }

    def test_ic_injected(self):
        """IC was triggered (injected) for a table."""
        cache.mark_impact_check_injected("orders")
        result = _extract_workflow_flags("sess1", ["orders"])
        assert result["impact_check_fired"] is True
        assert result["edit_gated"] is True

    def test_ic_verified_and_no_pending(self):
        """IC verified, no prior pending -> validation_prompted = True."""
        cache.mark_impact_check_injected("orders")
        cache.mark_impact_check_verified("orders")
        result = _extract_workflow_flags("sess1", ["orders"])
        assert result["impact_check_fired"] is True
        assert result["edit_gated"] is True
        assert result["validation_prompted"] is True

    def test_ic_verified_with_pending(self):
        """IC verified but pending already exists -> validation_prompted = False."""
        cache.add_edited_table("sess1", "prior_table")
        cache.move_to_pending_validation("sess1")
        cache.mark_impact_check_injected("orders")
        cache.mark_impact_check_verified("orders")
        result = _extract_workflow_flags("sess1", ["orders"])
        assert result["validation_prompted"] is False

    def test_monitor_gap_detected(self):
        cache.mark_monitor_gap("orders")
        result = _extract_workflow_flags("sess1", ["orders"])
        assert result["monitor_gap_detected"] is True

    def test_mixed_tables(self):
        """Multiple tables, only some have IC state."""
        cache.mark_impact_check_injected("orders")
        cache.mark_impact_check_verified("orders")
        result = _extract_workflow_flags("sess1", ["orders", "customers"])
        assert result["impact_check_fired"] is True
        assert result["validation_prompted"] is True


from lib.emitter import _extract_intent


class TestExtractIntent:
    def test_commit_message_when_head_changed(self):
        """When HEAD changed since last emit, use commit message."""
        cache.set_last_commit_hash("sess1", "old_hash")
        with patch("lib.emitter.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(stdout="new_hash\n", returncode=0),
                MagicMock(stdout="Fix stale join logic\n", returncode=0),
            ]
            result = _extract_intent("sess1", "/tmp/nonexistent.jsonl")

        assert result == {"summary": "Fix stale join logic", "source": "commit_message"}

    def test_no_commit_falls_back_to_transcript(self, tmp_path):
        """No commit happened -> fall back to first user message in transcript."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"role":"user","message":"update the orders model to filter deleted records"}\n'
            '{"role":"assistant","message":"I will update the model."}\n'
        )
        cache.set_last_commit_hash("sess1", "same_hash")
        with patch("lib.emitter.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="same_hash\n", returncode=0)
            result = _extract_intent("sess1", str(transcript))

        assert result == {
            "summary": "update the orders model to filter deleted records",
            "source": "transcript",
        }

    def test_transcript_truncated_to_256_chars(self, tmp_path):
        transcript = tmp_path / "transcript.jsonl"
        long_msg = "x" * 500
        transcript.write_text(f'{{"role":"user","message":"{long_msg}"}}\n')
        cache.set_last_commit_hash("sess1", "same")
        with patch("lib.emitter.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="same\n", returncode=0)
            result = _extract_intent("sess1", str(transcript))

        assert result is not None
        assert len(result["summary"]) == 256

    def test_no_prior_hash_no_transcript(self):
        """First emit, no transcript -> intent is None."""
        with patch("lib.emitter.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="hash1\n", returncode=0)
            result = _extract_intent("sess1", "/nonexistent/path")

        assert result is None

    def test_stores_current_hash_for_next_emit(self):
        """After extracting intent, current HEAD is cached for next comparison."""
        with patch("lib.emitter.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="new_hash\n", returncode=0)
            _extract_intent("sess1", "/tmp/t.jsonl")

        assert cache.get_last_commit_hash("sess1") == "new_hash"

    def test_commit_message_truncated_to_256(self):
        cache.set_last_commit_hash("sess1", "old")
        long_commit = "y" * 500
        with patch("lib.emitter.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(stdout="new\n", returncode=0),
                MagicMock(stdout=f"{long_commit}\n", returncode=0),
            ]
            result = _extract_intent("sess1", "/tmp/t.jsonl")

        assert len(result["summary"]) == 256

    def test_git_failure_falls_back_to_transcript(self, tmp_path):
        """If git commands fail, fall back to transcript."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"role":"user","message":"fix the bug"}\n')
        with patch("lib.emitter.subprocess.run", side_effect=Exception("no git")):
            result = _extract_intent("sess1", str(transcript))

        assert result == {"summary": "fix the bug", "source": "transcript"}


from lib.emitter import _build_event, _send


class TestBuildEvent:
    def test_event_structure(self):
        cache.mark_impact_check_injected("orders")
        cache.mark_impact_check_verified("orders")

        with patch("lib.emitter._get_git_identity", return_value={"git_email": "a@b.com", "git_name": "A"}):
            with patch("lib.emitter._extract_intent", return_value=None):
                event = _build_event("sess1", "/tmp/t.jsonl", ["orders"])

        assert event["event_type"] == "safe_change.turn_completed"
        assert event["event_version"] == "1.0"
        assert "timestamp" in event
        assert event["session_id"] == "sess1"
        assert event["identity"] == {"git_email": "a@b.com", "git_name": "A"}
        assert event["changes"] == [{"table_name": "orders"}]
        assert event["workflows"]["impact_check_fired"] is True
        assert event["intent"] is None

    def test_multiple_tables(self):
        with patch("lib.emitter._get_git_identity", return_value={"git_email": "", "git_name": ""}):
            with patch("lib.emitter._extract_intent", return_value=None):
                event = _build_event("sess1", "/tmp/t.jsonl", ["orders", "customers"])

        assert len(event["changes"]) == 2
        assert event["changes"][0]["table_name"] == "orders"
        assert event["changes"][1]["table_name"] == "customers"

    def test_timestamp_is_utc_iso(self):
        with patch("lib.emitter._get_git_identity", return_value={"git_email": "", "git_name": ""}):
            with patch("lib.emitter._extract_intent", return_value=None):
                event = _build_event("sess1", "/tmp/t.jsonl", ["orders"])

        assert event["timestamp"].endswith("Z")
        datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))

    def test_event_includes_intent_from_commit(self):
        cache.mark_impact_check_injected("orders")
        cache.set_last_commit_hash("sess1", "old_hash")

        with patch("lib.emitter._get_git_identity", return_value={"git_email": "", "git_name": ""}):
            with patch("lib.emitter._get_current_head", return_value="new_hash"):
                with patch("lib.emitter._get_commit_message", return_value="Fix join"):
                    event = _build_event("sess1", "/tmp/t.jsonl", ["orders"])

        assert event["intent"] == {"summary": "Fix join", "source": "commit_message"}


class TestSend:
    def test_posts_to_mc(self):
        event = {"event_type": "test"}
        with patch.dict(os.environ, {"MCD_ID": "id1", "MCD_TOKEN": "tok1"}):
            with patch("lib.emitter.urllib.request.urlopen") as mock_urlopen:
                _send(event)

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.method == "POST"
        body = json.loads(req.data.decode())
        assert body == event
        assert req.get_header("X-mcd-id") == "id1"
        assert req.get_header("X-mcd-token") == "tok1"
        assert req.get_header("Content-type") == "application/json"

    def test_silently_drops_on_failure(self):
        with patch("lib.emitter.urllib.request.urlopen", side_effect=Exception("network")):
            _send({"event_type": "test"})  # should not raise

    def test_timeout_3s(self):
        with patch("lib.emitter.urllib.request.urlopen") as mock_urlopen:
            _send({"event_type": "test"})
        _, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") == 3


