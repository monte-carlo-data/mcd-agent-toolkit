#!/usr/bin/env python3
"""
Push query logs to Monte Carlo from a JSON manifest — push only.

Reads a manifest file produced by ``collect_query_logs.py`` and sends the query
log entries to Monte Carlo using the pycarlo push ingestion API.  Large payloads
are split into batches to stay under the 1 MB compressed limit.

Can be run standalone via CLI or imported (use the ``push()`` function).

Substitution points
-------------------
- MC_INGEST_KEY_ID     (env) / --key-id     (CLI) : Monte Carlo ingestion key ID
- MC_INGEST_KEY_TOKEN  (env) / --key-token  (CLI) : Monte Carlo ingestion key token
- MC_RESOURCE_UUID     (env) / --resource-uuid (CLI) : MC resource UUID for this connection

Prerequisites
-------------
    pip install pycarlo

Usage
-----
    python push_query_logs.py \\
        --key-id  <MC_INGEST_KEY_ID> \\
        --key-token <MC_INGEST_KEY_TOKEN> \\
        --resource-uuid <MC_RESOURCE_UUID> \\
        --input-file query_logs_output.json
"""

import argparse
import json
import os
from datetime import datetime, timezone

from pycarlo.core import Client, Session
from pycarlo.features.ingestion import IngestionService
from pycarlo.features.ingestion.models import QueryLogEntry

# ← SUBSTITUTE: set LOG_TYPE to match your warehouse type (query logs use log_type, not resource_type)
LOG_TYPE = "snowflake"

# Maximum entries per batch — conservative default to keep compressed payload under 1 MB.
# Query logs include full SQL text, so use a smaller batch size than metadata.
# ← SUBSTITUTE: tune based on average query length
_BATCH_SIZE = 250


def _build_query_log_entries(queries: list[dict]) -> list[QueryLogEntry]:
    """Convert manifest query dicts into QueryLogEntry objects."""
    entries = []
    for q in queries:
        start_time = q.get("start_time")
        end_time = q.get("end_time")
        query_text = q.get("query_text") or ""
        query_id = q.get("query_id")
        user_name = q.get("user")
        warehouse_name = q.get("warehouse")
        bytes_scanned = q.get("bytes_scanned")
        rows_produced = q.get("rows_produced")

        entries.append(
            QueryLogEntry(
                start_time=start_time,
                end_time=end_time,
                query_text=query_text,
                query_id=query_id,
                user=user_name,
                returned_rows=int(rows_produced) if rows_produced is not None else None,
                # Pass warehouse and bytes_scanned as extra kwargs for MC enrichment
                warehouse_name=warehouse_name,
                bytes_scanned=int(bytes_scanned) if bytes_scanned is not None else None,
            )
        )
    return entries


def push(
    input_file: str,
    resource_uuid: str,
    key_id: str,
    key_token: str,
    batch_size: int = _BATCH_SIZE,
    output_file: str = "query_logs_push_result.json",
) -> dict:
    """
    Read a query log manifest and push entries to Monte Carlo in batches.

    Returns a result dict with invocation IDs for each batch.
    """
    with open(input_file) as fh:
        manifest = json.load(fh)

    queries = manifest.get("queries", [])
    log_type = manifest.get("log_type", LOG_TYPE)
    entries = _build_query_log_entries(queries)
    print(f"Loaded {len(entries)} query log entry/entries from {input_file}")

    if not entries:
        print("No query log entries to push.")
        push_result = {
            "resource_uuid": resource_uuid,
            "log_type": log_type,
            "invocation_ids": [],
            "pushed_at": datetime.now(tz=timezone.utc).isoformat(),
            "total_entries": 0,
            "batch_count": 0,
            "batch_size": batch_size,
        }
        with open(output_file, "w") as fh:
            json.dump(push_result, fh, indent=2)
        return push_result

    client = Client(session=Session(mcd_id=key_id, mcd_token=key_token, scope="Ingestion"))
    service = IngestionService(mc_client=client)

    invocation_ids: list[str | None] = []
    total_batches = (len(entries) + batch_size - 1) // batch_size or 1

    for i in range(0, len(entries), batch_size):
        batch = entries[i : i + batch_size]
        batch_num = i // batch_size + 1
        print(f"  Pushing batch {batch_num}/{total_batches} ({len(batch)} entries) ...")

        result = service.send_query_logs(
            resource_uuid=resource_uuid,
            log_type=log_type,
            events=batch,
        )
        invocation_id = service.extract_invocation_id(result)
        invocation_ids.append(invocation_id)
        print(f"    Response: {json.dumps(result, indent=2) if result else '(empty)'}")
        if invocation_id:
            print(f"    Invocation ID: {invocation_id}")

    push_result = {
        "resource_uuid": resource_uuid,
        "log_type": log_type,
        "invocation_ids": invocation_ids,
        "pushed_at": datetime.now(tz=timezone.utc).isoformat(),
        "total_entries": len(entries),
        "batch_count": total_batches,
        "batch_size": batch_size,
    }
    with open(output_file, "w") as fh:
        json.dump(push_result, fh, indent=2)
    print(f"Push result written to {output_file}")

    return push_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push Snowflake query logs from a manifest to Monte Carlo",
    )
    parser.add_argument(
        "--key-id",
        default=os.environ.get("MC_INGEST_KEY_ID"),
        help="Monte Carlo ingestion key ID (env: MC_INGEST_KEY_ID)",
    )
    parser.add_argument(
        "--key-token",
        default=os.environ.get("MC_INGEST_KEY_TOKEN"),
        help="Monte Carlo ingestion key token (env: MC_INGEST_KEY_TOKEN)",
    )
    parser.add_argument(
        "--resource-uuid",
        default=os.environ.get("MC_RESOURCE_UUID"),
        help="Monte Carlo resource UUID for this Snowflake connection (env: MC_RESOURCE_UUID)",
    )
    parser.add_argument(
        "--input-file",
        default="query_logs_output.json",
        help="Path to the collect manifest to read (default: query_logs_output.json)",
    )
    parser.add_argument(
        "--output-file",
        default="query_logs_push_result.json",
        help="Path to write the push result (default: query_logs_push_result.json)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_BATCH_SIZE,
        help=f"Max entries per push batch (default: {_BATCH_SIZE})",
    )
    args = parser.parse_args()

    missing = [
        name
        for name, val in [
            ("--key-id", args.key_id),
            ("--key-token", args.key_token),
            ("--resource-uuid", args.resource_uuid),
        ]
        if not val
    ]
    if missing:
        parser.error(f"Missing required arguments: {', '.join(missing)}")

    push(
        input_file=args.input_file,
        resource_uuid=args.resource_uuid,
        key_id=args.key_id,
        key_token=args.key_token,
        batch_size=args.batch_size,
        output_file=args.output_file,
    )
    print("Done.")


if __name__ == "__main__":
    main()
