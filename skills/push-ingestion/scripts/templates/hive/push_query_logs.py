#!/usr/bin/env python3
"""
Push a collected Hive query log manifest to Monte Carlo — push only.

Reads a JSON manifest produced by ``collect_query_logs.py``, builds
QueryLogEntry objects, and calls ``send_query_logs`` in batches.  The manifest
is updated in-place with ``resource_uuid`` and ``invocation_id`` after a
successful push.

Can be run standalone via CLI or imported (use the ``push()`` function).

Substitution points
-------------------
- MC_INGEST_KEY_ID    (env) / --key-id        (CLI) : Monte Carlo ingestion key ID
- MC_INGEST_KEY_TOKEN (env) / --key-token      (CLI) : Monte Carlo ingestion key token
- MC_RESOURCE_UUID    (env) / --resource-uuid  (CLI) : MC resource UUID (optional for query logs)

Prerequisites
-------------
    pip install pycarlo python-dateutil python-dotenv

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

from dateutil.parser import isoparse

from pycarlo.core import Client, Session
from pycarlo.features.ingestion import IngestionService
from pycarlo.features.ingestion.models import QueryLogEntry

# ← SUBSTITUTE: default batch size for query log push (events per request)
DEFAULT_BATCH_SIZE = 250

# ← SUBSTITUTE: HTTP timeout for MC ingestion requests (seconds)
DEFAULT_TIMEOUT_SECONDS = 120


def _build_events(manifest: dict) -> list[QueryLogEntry]:
    """
    Rebuild QueryLogEntry objects from a collected query log manifest.

    ISO timestamp strings are parsed back to datetime.  Entries are
    deduplicated by query_id.
    """
    seen: set[str] = set()
    events = []
    for q in manifest.get("queries", []):
        qid = q.get("query_id")
        if qid and qid in seen:
            continue
        if qid:
            seen.add(qid)

        start_time = isoparse(q["start_time"])
        if not start_time.tzinfo:
            start_time = start_time.replace(tzinfo=timezone.utc)

        end_time = isoparse(q["end_time"])
        if not end_time.tzinfo:
            end_time = end_time.replace(tzinfo=timezone.utc)

        events.append(
            QueryLogEntry(
                start_time=start_time,
                end_time=end_time,
                query_text=q["query"],
                query_id=qid or None,
                user=q.get("user", "hadoop"),  # ← SUBSTITUTE: set the user appropriate for your cluster
                returned_rows=q.get("returned_rows"),
            )
        )
    return events


def push(
    manifest: dict,
    key_id: str,
    key_token: str,
    resource_uuid: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str | None:
    """
    Push collected query logs to Monte Carlo and update the manifest in-place.

    Events are sent in batches of ``batch_size`` (default 250) to avoid
    oversized payloads.

    Args:
        manifest: Dict loaded from a ``collect_query_logs.py`` output file.
        key_id: MC ingestion key ID.
        key_token: MC ingestion key token.
        resource_uuid: Optional MC resource UUID.
        batch_size: Events per POST request (default 250).
        timeout_seconds: HTTP timeout per request (default 120).

    Returns:
        The last invocation ID string if returned by MC, otherwise None.
    """
    log_type = manifest.get("log_type", "hive-s3")

    events = _build_events(manifest)
    n = len(events)
    batches = (n + batch_size - 1) // batch_size if n else 0

    if batches > 1:
        print(f"Pushing {n} query log event(s) to Monte Carlo in {batches} batch(es) of up to {batch_size} ...")
    else:
        print(f"Pushing {n} query log event(s) to Monte Carlo ...")

    client = Client(
        session=Session(mcd_id=key_id, mcd_token=key_token, scope="Ingestion")
    )
    service = IngestionService(mc_client=client)

    invocation_ids: list[str] = []
    for b in range(batches):
        lo = b * batch_size
        hi = min(lo + batch_size, n)
        part = events[lo:hi]
        try:
            result = service.send_query_logs(
                resource_uuid=resource_uuid,
                log_type=log_type,
                events=part,
            )
        except Exception as exc:
            print(f"  ERROR pushing batch {b + 1}/{batches}: {exc}")
            raise
        iid = service.extract_invocation_id(result)
        if iid:
            invocation_ids.append(iid)
        if batches > 1:
            print(f"  Batch {b + 1}/{batches}: {len(part)} events — response: {json.dumps(result) if result else '(empty)'}")
        elif result is not None:
            print(f"Response: {json.dumps(result, indent=2)}")

    last_id = invocation_ids[-1] if invocation_ids else None
    if last_id and batches <= 1:
        print(f"Invocation ID: {last_id}")
    elif len(invocation_ids) > 1:
        print(f"Invocation IDs ({len(invocation_ids)} batches): {invocation_ids}")

    manifest["log_type"] = log_type
    if resource_uuid is not None:
        manifest["resource_uuid"] = resource_uuid
    manifest["invocation_id"] = last_id
    if len(invocation_ids) > 1:
        manifest["invocation_ids"] = invocation_ids
    elif "invocation_ids" in manifest:
        del manifest["invocation_ids"]

    return last_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push a collected Hive query log manifest to Monte Carlo",
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
        help="Monte Carlo resource UUID (optional for query logs) (env: MC_RESOURCE_UUID)",
    )
    parser.add_argument(
        "--input-file",
        default="query_logs_output.json",
        help="Path to the JSON manifest written by collect_query_logs.py (default: query_logs_output.json)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        metavar="N",
        help=f"Max events per POST (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        metavar="SEC",
        help=f"HTTP timeout per request in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    args = parser.parse_args()

    if not args.key_id or not args.key_token:
        parser.error("--key-id and --key-token are required (or set MC_INGEST_KEY_ID / MC_INGEST_KEY_TOKEN)")

    with open(args.input_file) as fh:
        manifest = json.load(fh)

    push(
        manifest=manifest,
        key_id=args.key_id,
        key_token=args.key_token,
        resource_uuid=args.resource_uuid,
        batch_size=args.batch_size,
        timeout_seconds=args.timeout,
    )

    with open(args.input_file, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"Manifest updated in-place: {args.input_file}")
    print("Done.")


if __name__ == "__main__":
    main()
