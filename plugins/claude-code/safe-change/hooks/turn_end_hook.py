#!/usr/bin/env python3
"""Stop hook: prompts for validation once per turn if dbt models were edited."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from lib.safe_run import safe_run
from lib.cache import (
    get_edited_tables,
    get_impact_check_state,
    get_pending_validation_tables,
    has_monitor_gap,
    move_to_pending_validation,
)
from lib import emitter


@safe_run
def main():
    input_data = json.load(sys.stdin)

    # Prevent infinite loop — if this Stop was triggered by our own block, exit
    if input_data.get("stop_hook_active", False):
        return

    session_id = input_data.get("session_id", "unknown")
    tables = get_edited_tables(session_id)

    if not tables:
        return

    # Emit change event (non-blocking, before validation logic)
    transcript_path = input_data.get("transcript_path", "")
    emitter.emit(session_id, transcript_path, tables)

    # If validation was already prompted (pending tables exist), silently merge
    # new edits into pending rather than re-prompting. This prevents the double-
    # prompt when edits occur after the user was already asked about validation.
    if get_pending_validation_tables(session_id):
        move_to_pending_validation(session_id)
        return

    # Prompt if impact assessment was triggered for at least one edited table
    # "injected" means W4 instruction was sent; "verified" means completion confirmed
    w4_tables = [t for t in tables if get_impact_check_state(t) in ("injected", "verified")]
    if not w4_tables:
        return

    # Check for monitor coverage gaps
    gap_tables = [t for t in tables if has_monitor_gap(t)]

    # Build prompt
    table_list = ", ".join(tables)
    count = len(tables)
    reason = (
        f"You've changed {count} dbt model(s): {table_list}. "
        f"ASK THE USER whether they would like to run validation queries to "
        f"verify these changes behaved as intended. Present these options and "
        f"WAIT for the user to respond — do NOT answer on their behalf:\n\n"
        f"→ Yes: I'll generate and run queries for all changed models\n"
        f"→ No: You can use /mc-validate anytime to validate changes"
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

    # Move tables to pending validation before prompting
    move_to_pending_validation(session_id)

    output = {"decision": "block", "reason": reason}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
