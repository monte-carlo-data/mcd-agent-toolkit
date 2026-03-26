"""
Databricks — Query Log Push (push-only)
=========================================
Reads a JSON manifest file produced by collect_query_logs.py and pushes the query
log entries to Monte Carlo via the push ingestion API, with configurable batching
to keep compressed payloads under 1 MB.

Substitution points (search for "← SUBSTITUTE"):
  - MCD_INGEST_ID / MCD_INGEST_TOKEN : Monte Carlo API credentials
  - MCD_RESOURCE_UUID      : UUID of the Databricks connection in Monte Carlo
  - PUSH_BATCH_SIZE       : number of entries per API call (default 250)

Prerequisites:
  pip install pycarlo
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from pycarlo.core import Client, Session
from pycarlo.features.ingestion import IngestionService
from pycarlo.features.ingestion.models import QueryLogEntry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

LOG_TYPE = "databricks"
DEFAULT_BATCH_SIZE = 250  # ← SUBSTITUTE: conservative default to stay under 1 MB compressed


def _entry_from_dict(d: dict[str, Any]) -> QueryLogEntry:
    """Reconstruct a QueryLogEntry from a manifest dict."""
    return QueryLogEntry(
        query_id=d.get("query_id"),
        query_text=d.get("query_text", ""),
        start_time=d.get("start_time"),
        end_time=d.get("end_time"),
        user=d.get("user"),
        returned_rows=d.get("returned_rows"),
        total_task_duration_ms=d.get("total_task_duration_ms"),
        read_rows=d.get("read_rows"),
        read_bytes=d.get("read_bytes"),
    )


def push(
    manifest_path: str,
    resource_uuid: str,
    key_id: str,
    key_token: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    """Read a collect manifest and push query log entries to Monte Carlo in batches.

    Returns a summary dict with invocation IDs and counts.
    """
    with open(manifest_path) as fh:
        manifest = json.load(fh)

    entry_dicts: list[dict[str, Any]] = manifest["entries"]
    entries = [_entry_from_dict(d) for d in entry_dicts]
    log.info("Loaded %d query log entries from %s", len(entries), manifest_path)

    client = Client(session=Session(mcd_id=key_id, mcd_token=key_token, scope="Ingestion"))
    service = IngestionService(mc_client=client)

    pushed_at = datetime.now(timezone.utc).isoformat()
    invocation_ids: list[str] = []

    for i in range(0, len(entries), batch_size):
        batch = entries[i : i + batch_size]
        log.info("Pushing batch %d–%d of %d entries …", i, i + len(batch), len(entries))
        result = service.push_custom_query_logs(
            resource_uuid=resource_uuid,
            log_type=LOG_TYPE,
            query_logs=batch,
        )
        inv_id = service.extract_invocation_id(result)
        invocation_ids.append(inv_id)
        log.info("Batch pushed — invocation_id=%s", inv_id)

    summary = {
        "resource_uuid": resource_uuid,
        "log_type": LOG_TYPE,
        "invocation_ids": invocation_ids,
        "pushed_at": pushed_at,
        "query_log_count": len(entries),
        "batch_count": len(invocation_ids),
        "lookback_hours": manifest.get("lookback_hours"),
        "lookback_lag_hours": manifest.get("lookback_lag_hours"),
    }

    push_manifest_path = manifest_path.replace(".json", "_push_result.json")
    with open(push_manifest_path, "w") as fh:
        json.dump(summary, fh, indent=2)
    log.info("Push result written to %s", push_manifest_path)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Push Databricks query logs to Monte Carlo from manifest")
    parser.add_argument("--manifest", default="manifest_query_logs.json")
    parser.add_argument("--resource-uuid", default=os.getenv("MCD_RESOURCE_UUID"))
    parser.add_argument("--key-id", default=os.getenv("MCD_INGEST_ID"))
    parser.add_argument("--key-token", default=os.getenv("MCD_INGEST_TOKEN"))
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args()

    required = ["resource_uuid", "key_id", "key_token"]
    missing = [k for k in required if getattr(args, k) is None]
    if missing:
        parser.error(f"Missing required arguments/env vars: {missing}")

    push(
        manifest_path=args.manifest,
        resource_uuid=args.resource_uuid,
        key_id=args.key_id,
        key_token=args.key_token,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
