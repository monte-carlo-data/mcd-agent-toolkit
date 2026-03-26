"""
BigQuery — Query Log Push (push only)
======================================
Reads a manifest file produced by ``collect_query_logs.py`` and pushes the query
log entries to Monte Carlo using the pycarlo push ingestion API.  Large payloads
are split into batches to stay under the 1 MB compressed limit.

Can be run standalone via CLI or imported (use the ``push()`` function).

Substitution points (search for "← SUBSTITUTE"):
  - MC_INGEST_KEY_ID / MC_INGEST_KEY_TOKEN : Monte Carlo API credentials
  - MC_RESOURCE_UUID      : UUID of the BigQuery connection in Monte Carlo

Prerequisites:
  pip install pycarlo
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone

from pycarlo.core import Client, Session
from pycarlo.features.ingestion import IngestionService
from pycarlo.features.ingestion.models import QueryLogEntry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

LOG_TYPE = "bigquery"

# Maximum entries per batch — conservative default to keep compressed payload under 1 MB.
# Query logs include full SQL text, so use a smaller batch size than metadata.
# ← SUBSTITUTE: tune based on average query length
_BATCH_SIZE = 250


def _build_query_log_entries(queries: list[dict]) -> list[QueryLogEntry]:
    """Convert manifest query dicts into QueryLogEntry objects."""
    entries = []
    for q in queries:
        entry = QueryLogEntry(
            query_id=q.get("query_id"),
            query_text=q.get("query_text") or "",
            start_time=q.get("start_time"),
            end_time=q.get("end_time"),
            user=q.get("user"),
            # Pass warehouse-specific extras as keyword arguments
            total_bytes_billed=q.get("total_bytes_billed"),
            statement_type=q.get("statement_type"),
        )
        entries.append(entry)
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
    log.info("Loaded %d query log entry/entries from %s", len(entries), input_file)

    if not entries:
        log.info("No query log entries to push.")
        push_result = {
            "resource_uuid": resource_uuid,
            "log_type": log_type,
            "invocation_ids": [],
            "pushed_at": datetime.now(timezone.utc).isoformat(),
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
        log.info("Pushing batch %d/%d (%d entries) ...", batch_num, total_batches, len(batch))

        result = service.push_custom_query_logs(
            resource_uuid=resource_uuid,
            log_type=log_type,
            query_logs=batch,
        )
        invocation_id = service.extract_invocation_id(result)
        invocation_ids.append(invocation_id)
        if invocation_id:
            log.info("  Invocation ID: %s", invocation_id)

    push_result = {
        "resource_uuid": resource_uuid,
        "log_type": log_type,
        "invocation_ids": invocation_ids,
        "pushed_at": datetime.now(timezone.utc).isoformat(),
        "total_entries": len(entries),
        "batch_count": total_batches,
        "batch_size": batch_size,
    }
    with open(output_file, "w") as fh:
        json.dump(push_result, fh, indent=2)
    log.info("Push result written to %s", output_file)

    return push_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push BigQuery query logs from a manifest to Monte Carlo",
    )
    parser.add_argument("--resource-uuid", default=os.getenv("MC_RESOURCE_UUID"))
    parser.add_argument("--key-id", default=os.getenv("MC_INGEST_KEY_ID"))
    parser.add_argument("--key-token", default=os.getenv("MC_INGEST_KEY_TOKEN"))
    parser.add_argument("--input-file", default="query_logs_output.json")
    parser.add_argument("--output-file", default="query_logs_push_result.json")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_BATCH_SIZE,
        help=f"Max entries per push batch (default: {_BATCH_SIZE})",
    )
    args = parser.parse_args()

    required = ["resource_uuid", "key_id", "key_token"]
    missing = [k for k in required if getattr(args, k) is None]
    if missing:
        parser.error(f"Missing required arguments/env vars: {missing}")

    push(
        input_file=args.input_file,
        resource_uuid=args.resource_uuid,
        key_id=args.key_id,
        key_token=args.key_token,
        batch_size=args.batch_size,
        output_file=args.output_file,
    )


if __name__ == "__main__":
    main()
