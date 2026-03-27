import json
import os
import subprocess
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
        cache.mark_impact_check_injected("sess1", "orders")
        result = _extract_workflow_flags("sess1", ["orders"])
        assert result["impact_check_fired"] is True
        assert result["edit_gated"] is True

    def test_ic_verified_and_no_pending(self):
        """IC verified, no prior pending -> validation_prompted = True."""
        cache.mark_impact_check_injected("sess1", "orders")
        cache.mark_impact_check_verified("sess1", "orders")
        result = _extract_workflow_flags("sess1", ["orders"])
        assert result["impact_check_fired"] is True
        assert result["edit_gated"] is True
        assert result["validation_prompted"] is True

    def test_ic_verified_with_pending(self):
        """IC verified but pending already exists -> validation_prompted = False."""
        cache.add_edited_table("sess1", "prior_table")
        cache.move_to_pending_validation("sess1")
        cache.mark_impact_check_injected("sess1", "orders")
        cache.mark_impact_check_verified("sess1", "orders")
        result = _extract_workflow_flags("sess1", ["orders"])
        assert result["validation_prompted"] is False

    def test_monitor_gap_detected(self):
        cache.mark_monitor_gap("sess1", "orders")
        result = _extract_workflow_flags("sess1", ["orders"])
        assert result["monitor_gap_detected"] is True

    def test_mixed_tables(self):
        """Multiple tables, only some have IC state."""
        cache.mark_impact_check_injected("sess1", "orders")
        cache.mark_impact_check_verified("sess1", "orders")
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
            '{"type":"user","message":{"role":"user","content":"update the orders model to filter deleted records"}}\n'
            '{"type":"assistant","message":{"role":"assistant","content":"I will update the model."}}\n'
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
        transcript.write_text(f'{{"type":"user","message":{{"role":"user","content":"{long_msg}"}}}}\n')
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
        transcript.write_text('{"type":"user","message":{"role":"user","content":"fix the bug"}}\n')
        with patch("lib.emitter.subprocess.run", side_effect=Exception("no git")):
            result = _extract_intent("sess1", str(transcript))

        assert result == {"summary": "fix the bug", "source": "transcript"}


from lib.emitter import _build_event, _build_changes, _scan_impact_data, _send


class TestScanImpactData:
    def _write_transcript(self, tmp_path, content):
        """Helper: write a transcript with assistant message content."""
        transcript = tmp_path / "t.jsonl"
        # Build proper JSONL — json.dumps handles escaping correctly
        entry = {"type": "assistant", "message": {"role": "assistant", "content": content}}
        transcript.write_text(json.dumps(entry) + "\n")
        return str(transcript)

    def test_parses_marker_from_transcript(self, tmp_path):
        path = self._write_transcript(tmp_path,
            '<!-- MC_IMPACT_DATA: {"table":"orders","risk_tier":"high","downstream_count":704,"key_asset":true,"monitor_count":2} -->')
        result = _scan_impact_data(path)
        assert result == {
            "orders": {"risk_tier": "high", "downstream_count": 704, "key_asset": True, "monitor_count": 2}
        }

    def test_multiple_tables(self, tmp_path):
        path = self._write_transcript(tmp_path,
            '<!-- MC_IMPACT_DATA: {"table":"orders","risk_tier":"high","downstream_count":10,"key_asset":true,"monitor_count":1} -->\n'
            '<!-- MC_IMPACT_DATA: {"table":"customers","risk_tier":"low","downstream_count":3,"key_asset":false,"monitor_count":0} -->')
        result = _scan_impact_data(path)
        assert "orders" in result
        assert "customers" in result
        assert result["orders"]["risk_tier"] == "high"
        assert result["customers"]["risk_tier"] == "low"

    def test_no_markers_returns_empty(self, tmp_path):
        path = self._write_transcript(tmp_path, "Just a normal response with no markers.")
        result = _scan_impact_data(path)
        assert result == {}

    def test_missing_file_returns_empty(self):
        result = _scan_impact_data("/nonexistent/path.jsonl")
        assert result == {}

    def test_malformed_json_skipped(self, tmp_path):
        path = self._write_transcript(tmp_path,
            '<!-- MC_IMPACT_DATA: {bad json} -->\n'
            '<!-- MC_IMPACT_DATA: {"table":"orders","risk_tier":"low","downstream_count":1,"key_asset":false,"monitor_count":0} -->')
        result = _scan_impact_data(path)
        assert result == {"orders": {"risk_tier": "low", "downstream_count": 1, "key_asset": False, "monitor_count": 0}}


class TestBuildChanges:
    def test_no_impact_data(self):
        changes = _build_changes(["orders", "customers"], {})
        assert changes == [{"table_name": "orders"}, {"table_name": "customers"}]

    def test_with_impact_data(self):
        impact = {"orders": {"risk_tier": "high", "downstream_count": 704}}
        changes = _build_changes(["orders", "customers"], impact)
        assert changes[0] == {"table_name": "orders", "assessment": {"risk_tier": "high", "downstream_count": 704}}
        assert changes[1] == {"table_name": "customers"}

    def test_all_tables_enriched(self):
        impact = {
            "orders": {"risk_tier": "high"},
            "customers": {"risk_tier": "low"},
        }
        changes = _build_changes(["orders", "customers"], impact)
        assert all("assessment" in c for c in changes)


class TestBuildEvent:
    def test_event_structure(self):
        cache.mark_impact_check_injected("sess1", "orders")
        cache.mark_impact_check_verified("sess1", "orders")

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
        cache.mark_impact_check_injected("sess1", "orders")
        cache.set_last_commit_hash("sess1", "old_hash")

        with patch("lib.emitter._get_git_identity", return_value={"git_email": "", "git_name": ""}):
            with patch("lib.emitter._get_current_head", return_value="new_hash"):
                with patch("lib.emitter._get_commit_message", return_value="Fix join"):
                    event = _build_event("sess1", "/tmp/t.jsonl", ["orders"])

        assert event["intent"] == {"summary": "Fix join", "source": "commit_message"}


class TestSend:
    def test_spawns_subprocess_with_event(self):
        event = {"event_type": "test"}
        with patch.dict(os.environ, {"MCD_ID": "id1", "MCD_TOKEN": "tok1"}):
            with patch("lib.emitter.subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_popen.return_value = mock_proc
                _send(event)

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        # Verify detached subprocess
        assert call_args[1]["start_new_session"] is True
        assert call_args[1]["stdin"] == subprocess.PIPE
        # Verify event was written to stdin
        mock_proc.stdin.write.assert_called_once()
        written = mock_proc.stdin.write.call_args[0][0]
        assert json.loads(written.decode()) == event
        mock_proc.stdin.close.assert_called_once()
        # Verify credentials passed as args: [python3, -c, script, url, mcd_id, mcd_token]
        cmd_args = call_args[0][0]
        assert cmd_args[4] == "id1"  # MCD_ID
        assert cmd_args[5] == "tok1"  # MCD_TOKEN

    def test_silently_drops_on_failure(self):
        with patch("lib.emitter.subprocess.Popen", side_effect=Exception("spawn failed")):
            _send({"event_type": "test"})  # should not raise


from lib.emitter import emit, _rate_limit_ok


class TestRateLimit:
    def test_first_call_allowed(self):
        assert _rate_limit_ok("rate_sess") is True

    def test_rapid_second_call_blocked(self):
        _rate_limit_ok("rate_sess2")
        assert _rate_limit_ok("rate_sess2") is False

    def test_allowed_after_interval(self):
        _rate_limit_ok("rate_sess3")
        # Backdate the marker file to make it appear old
        import glob
        markers = glob.glob("/tmp/mc_safe_change_emit_rate_sess3")
        assert len(markers) == 1
        old_time = os.path.getmtime(markers[0]) - 10
        os.utime(markers[0], (old_time, old_time))
        assert _rate_limit_ok("rate_sess3") is True

    def test_independent_sessions(self):
        _rate_limit_ok("rate_a")
        assert _rate_limit_ok("rate_b") is True  # different session, not blocked


class TestEmit:
    def test_calls_send(self):
        cache.mark_impact_check_injected("sess1", "orders")
        with patch("lib.emitter._get_git_identity", return_value={"git_email": "", "git_name": ""}):
            with patch("lib.emitter._extract_intent", return_value=None):
                with patch("lib.emitter._send") as mock_send:
                    with patch.dict(os.environ, {"MCD_ID": "x", "MCD_TOKEN": "y"}):
                        emit("sess1", "/tmp/t.jsonl", ["orders"])

        mock_send.assert_called_once()
        event = mock_send.call_args[0][0]
        assert event["event_type"] == "safe_change.turn_completed"

    def test_fail_open_on_build_error(self):
        """emit() should never raise, even if _build_event fails."""
        with patch.dict(os.environ, {"MCD_ID": "x", "MCD_TOKEN": "y"}):
            with patch("lib.emitter._build_event", side_effect=Exception("boom")):
                emit("sess1", "/tmp/t.jsonl", ["orders"])  # should not raise

    def test_skips_when_no_mcd_id(self):
        """No MCD_ID -> no event emitted."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("lib.emitter._send") as mock_send:
                emit("sess1", "/tmp/t.jsonl", ["orders"])
        mock_send.assert_not_called()

    def test_skips_when_disabled(self):
        """MC_EMIT_EVENTS=0 -> no event emitted."""
        with patch.dict(os.environ, {"MC_EMIT_EVENTS": "0", "MCD_ID": "x", "MCD_TOKEN": "y"}):
            with patch("lib.emitter._send") as mock_send:
                emit("sess1", "/tmp/t.jsonl", ["orders"])
        mock_send.assert_not_called()

    def test_enabled_by_default(self):
        """MC_EMIT_EVENTS not set -> events enabled."""
        with patch("lib.emitter._get_git_identity", return_value={"git_email": "", "git_name": ""}):
            with patch("lib.emitter._extract_intent", return_value=None):
                with patch("lib.emitter._send") as mock_send:
                    with patch.dict(os.environ, {"MCD_ID": "x", "MCD_TOKEN": "y"}, clear=True):
                        emit("sess1", "/tmp/t.jsonl", ["orders"])
        mock_send.assert_called_once()

    def test_dry_run_prints_to_stderr(self, capsys):
        """MC_EMIT_EVENTS=dry_run -> prints event JSON to stderr, no HTTP call."""
        cache.mark_impact_check_injected("sess1", "orders")
        with patch("lib.emitter._get_git_identity", return_value={"git_email": "a@b.com", "git_name": "A"}):
            with patch("lib.emitter._extract_intent", return_value=None):
                with patch("lib.emitter.threading.Thread") as mock_thread:
                    with patch.dict(os.environ, {"MCD_ID": "x", "MC_EMIT_EVENTS": "dry_run"}):
                        emit("sess1", "/tmp/t.jsonl", ["orders"])

        # No HTTP thread spawned
        mock_thread.assert_not_called()

        # Event JSON printed to stderr
        captured = capsys.readouterr()
        event = json.loads(captured.err)
        assert event["event_type"] == "safe_change.turn_completed"
        assert event["session_id"] == "sess1"
        assert event["identity"]["git_email"] == "a@b.com"
        assert event["changes"] == [{"table_name": "orders"}]


class TestEndToEnd:
    def test_dry_run_full_event(self, tmp_path, capsys):
        """Full flow via dry_run: cache setup -> emit -> verify event from stderr."""
        # Set up cache state
        cache.mark_impact_check_injected("sess1", "orders")
        cache.mark_impact_check_verified("sess1", "orders")
        cache.mark_monitor_gap("sess1", "orders")
        cache.set_last_commit_hash("sess1", "old_hash")

        # Create transcript
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text('{"role":"user","message":"fix the join"}\n')

        with patch("lib.emitter._get_git_identity", return_value={"git_email": "a@b.com", "git_name": "A"}):
            with patch("lib.emitter._get_current_head", return_value="new_hash"):
                with patch("lib.emitter._get_commit_message", return_value="Fix stale join"):
                    with patch.dict(os.environ, {"MCD_ID": "x", "MC_EMIT_EVENTS": "dry_run"}):
                        emit("sess1", str(transcript), ["orders"])

        # Parse the event from stderr
        captured = capsys.readouterr()
        event = json.loads(captured.err)

        # Verify complete event structure
        assert event["event_type"] == "safe_change.turn_completed"
        assert event["event_version"] == "1.0"
        assert event["timestamp"].endswith("Z")
        assert event["session_id"] == "sess1"
        assert event["identity"] == {"git_email": "a@b.com", "git_name": "A"}
        assert event["changes"] == [{"table_name": "orders"}]
        assert event["workflows"]["impact_check_fired"] is True
        assert event["workflows"]["edit_gated"] is True
        assert event["workflows"]["validation_prompted"] is True
        assert event["workflows"]["monitor_gap_detected"] is True
        assert event["intent"] == {"summary": "Fix stale join", "source": "commit_message"}

    def test_real_http_send_to_local_server(self):
        """Verify _send() makes a real HTTP POST with correct payload."""
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler

        captured = {}

        class CaptureHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                captured["body"] = json.loads(self.rfile.read(length))
                captured["headers"] = dict(self.headers)
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"accepted"}')

            def log_message(self, format, *args):
                pass  # suppress server logs in test output

        # Start local server on a random available port
        server = HTTPServer(("127.0.0.1", 0), CaptureHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.handle_request, daemon=True)
        server_thread.start()

        # Send a real event to the local server
        event = {
            "event_type": "safe_change.turn_completed",
            "event_version": "1.0",
            "session_id": "test-123",
            "changes": [{"table_name": "orders"}],
        }
        with patch.dict(os.environ, {"MCD_ID": "key1", "MCD_TOKEN": "tok1"}):
            with patch("lib.emitter.MC_CHANGE_EVENTS_URL", f"http://127.0.0.1:{port}/plugin/change-events"):
                _send(event)

        server_thread.join(timeout=5)
        server.server_close()

        # Verify the payload arrived
        # Note: urllib.request title-cases header names (e.g. x-mcd-id -> X-Mcd-Id)
        assert captured["body"] == event
        assert captured["headers"]["X-Mcd-Id"] == "key1"
        assert captured["headers"]["X-Mcd-Token"] == "tok1"
        assert captured["headers"]["Content-Type"] == "application/json"
