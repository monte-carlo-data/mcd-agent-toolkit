#!/usr/bin/env python3
"""Stop hook: prompts for validation once per turn if dbt models were edited."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from lib.safe_run import safe_run
from lib.cache import (
    get_edited_tables,
    get_workflow4_state,
    move_to_pending_validation,
)


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

    # Prompt if Workflow 4 was triggered for at least one edited table
    # "injected" means W4 instruction was sent; "verified" means completion confirmed
    w4_tables = [t for t in tables if get_workflow4_state(t) in ("injected", "verified")]
    if not w4_tables:
        return

    # Build validation prompt
    table_list = ", ".join(tables)
    count = len(tables)
    reason = (
        f"You've changed {count} dbt model(s): {table_list}. "
        f"Would you like to run validation queries to verify these changes "
        f"behaved as intended?\n\n"
        f"→ Yes: I'll generate and run queries for all changed models\n"
        f"→ No: You can use /mc-validate anytime to validate changes"
    )

    # Move tables to pending validation before prompting
    move_to_pending_validation(session_id)

    output = {"decision": "block", "reason": reason}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
