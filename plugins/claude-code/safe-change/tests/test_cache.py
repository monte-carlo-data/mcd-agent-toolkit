import os
import stat
import time
import json
import pytest

from lib.cache import (
    CACHE_DIR,
    IC_PREFIX,
    TURN_PREFIX,
    PENDING_PREFIX,
    _validate_session_id,
    get_impact_check_state,
    mark_impact_check_injected,
    mark_impact_check_verified,
    get_impact_check_age_seconds,
    get_edited_tables,
    add_edited_table,
    clear_edited_tables,
    move_to_pending_validation,
    get_pending_validation_tables,
    clear_pending_validation,
)


class TestImpactCheckState:
    def test_no_marker_returns_none(self):
        assert get_impact_check_state("my_table") is None

    def test_injected_state(self):
        mark_impact_check_injected("my_table")
        assert get_impact_check_state("my_table") == "injected"

    def test_verified_state(self):
        mark_impact_check_injected("my_table")
        mark_impact_check_verified("my_table")
        assert get_impact_check_state("my_table") == "verified"

    def test_marker_age(self):
        mark_impact_check_injected("my_table")
        age = get_impact_check_age_seconds("my_table")
        assert 0 <= age < 2  # Should be very recent

    def test_different_tables_independent(self):
        mark_impact_check_injected("table_a")
        mark_impact_check_verified("table_a")
        assert get_impact_check_state("table_a") == "verified"
        assert get_impact_check_state("table_b") is None


class TestEditAccumulator:
    def test_empty_session(self):
        assert get_edited_tables("session_1") == []

    def test_add_one_table(self):
        add_edited_table("session_1", "orders")
        assert get_edited_tables("session_1") == ["orders"]

    def test_add_multiple_tables(self):
        add_edited_table("session_1", "orders")
        add_edited_table("session_1", "customers")
        tables = get_edited_tables("session_1")
        assert "orders" in tables
        assert "customers" in tables

    def test_deduplication(self):
        add_edited_table("session_1", "orders")
        add_edited_table("session_1", "orders")
        assert get_edited_tables("session_1") == ["orders"]

    def test_clear(self):
        add_edited_table("session_1", "orders")
        clear_edited_tables("session_1")
        assert get_edited_tables("session_1") == []

    def test_sessions_independent(self):
        add_edited_table("session_1", "orders")
        add_edited_table("session_2", "customers")
        assert get_edited_tables("session_1") == ["orders"]
        assert get_edited_tables("session_2") == ["customers"]


class TestPendingValidation:
    def test_move_to_pending(self):
        add_edited_table("session_1", "orders")
        add_edited_table("session_1", "customers")
        move_to_pending_validation("session_1")
        pending = get_pending_validation_tables("session_1")
        assert "orders" in pending
        assert "customers" in pending
        # Turn accumulator should be cleared
        assert get_edited_tables("session_1") == []

    def test_clear_pending(self):
        add_edited_table("session_1", "orders")
        move_to_pending_validation("session_1")
        clear_pending_validation("session_1")
        assert get_pending_validation_tables("session_1") == []

    def test_no_pending_returns_empty(self):
        assert get_pending_validation_tables("session_1") == []


class TestSessionIdValidation:
    def test_valid_alphanumeric(self):
        assert _validate_session_id("abc123") == "abc123"

    def test_valid_with_dashes_underscores(self):
        assert _validate_session_id("session-1_test") == "session-1_test"

    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError):
            _validate_session_id("../../etc/passwd")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError):
            _validate_session_id("session 1")

    def test_rejects_shell_metacharacters(self):
        for bad in ["$(cmd)", "a;b", "a&b", "a|b", "a\nb"]:
            with pytest.raises(ValueError):
                _validate_session_id(bad)

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            _validate_session_id("")


class TestFilePermissions:
    def _get_perms(self, path):
        return stat.S_IMODE(os.stat(path).st_mode)

    def test_impact_check_file_is_owner_only(self):
        mark_impact_check_injected("perm_test_table")
        path = os.path.join(CACHE_DIR, f"{IC_PREFIX}perm_test_table")
        assert self._get_perms(path) == 0o600

    def test_turn_file_is_owner_only(self):
        add_edited_table("perm_test_session", "orders")
        path = os.path.join(CACHE_DIR, f"{TURN_PREFIX}perm_test_session")
        assert self._get_perms(path) == 0o600

    def test_pending_file_is_owner_only(self):
        add_edited_table("perm_test_session2", "orders")
        move_to_pending_validation("perm_test_session2")
        path = os.path.join(CACHE_DIR, f"{PENDING_PREFIX}perm_test_session2")
        assert self._get_perms(path) == 0o600
