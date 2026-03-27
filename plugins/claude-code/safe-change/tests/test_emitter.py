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
