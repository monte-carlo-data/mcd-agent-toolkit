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
    get_pending_validation_tables,
    has_monitor_gap,
)


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
