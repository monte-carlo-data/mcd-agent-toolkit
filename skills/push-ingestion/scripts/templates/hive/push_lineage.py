#!/usr/bin/env python3
"""
Push a collected Hive lineage manifest to Monte Carlo — push only.

Reads a JSON manifest produced by ``collect_lineage.py``, builds LineageEvent
objects (table-level or column-level), and calls ``send_lineage`` in batches.
The manifest is updated in-place with ``resource_uuid`` and ``invocation_id``
after a successful push.

Can be run standalone via CLI or imported (use the ``push()`` function).

Substitution points
-------------------
- MC_INGEST_KEY_ID    (env) / --key-id        (CLI) : Monte Carlo ingestion key ID
- MC_INGEST_KEY_TOKEN (env) / --key-token      (CLI) : Monte Carlo ingestion key token
- MC_RESOURCE_UUID    (env) / --resource-uuid  (CLI) : MC resource UUID for this connection

Prerequisites
-------------
    pip install pycarlo python-dotenv

Usage (table-level):
    python push_lineage.py \\
        --key-id  <MC_INGEST_KEY_ID> \\
        --key-token <MC_INGEST_KEY_TOKEN> \\
        --resource-uuid <MC_RESOURCE_UUID> \\
        --input-file lineage_output.json

Usage (column-level):
    python push_lineage.py ... --column-lineage
"""

import argparse
import json
import os

from pycarlo.core import Client, Session
from pycarlo.features.ingestion import IngestionService
from pycarlo.features.ingestion.models import (
    ColumnLineageField,
    ColumnLineageSourceField,
    LineageAssetRef,
    LineageEvent,
)

# ← SUBSTITUTE: set RESOURCE_TYPE to match your Monte Carlo connection type
RESOURCE_TYPE = "data-lake"

# ← SUBSTITUTE: default batch size for lineage push (events per request)
DEFAULT_BATCH_SIZE = 500

# ← SUBSTITUTE: HTTP timeout for MC ingestion requests (seconds)
DEFAULT_TIMEOUT_SECONDS = 120


def _build_table_lineage(edges_data: list[dict]) -> list[LineageEvent]:
    """Build table-level LineageEvent objects from raw edge dicts."""
    events = []
    for edge in edges_data:
        sources = edge.get("sources", [])
        if not sources:
            continue
        dest = edge["destination"]
        events.append(
            LineageEvent(
                destination=LineageAssetRef(
                    type="TABLE",
                    name=dest["table"],
                    database=dest["database"],
                    schema=dest["database"],
                ),
                sources=[
                    LineageAssetRef(
                        type="TABLE",
                        name=src["table"],
                        database=src["database"],
                        schema=src["database"],
                    )
                    for src in sources
                ],
            )
        )
    return events


def _build_column_lineage(edges_data: list[dict]) -> list[LineageEvent]:
    """Build column-level LineageEvent objects from raw edge dicts."""
    events = []
    for edge in edges_data:
        sources = edge.get("sources", [])
        if not sources:
            continue

        dest = edge["destination"]
        dest_asset_id = f"{dest['database']}__{dest['table']}"
        source_asset_ids = {
            (src["database"], src["table"]): f"{src['database']}__{src['table']}"
            for src in sources
        }

        col_fields: dict[str, ColumnLineageField] = {}
        for mapping in edge.get("col_mappings", []):
            dest_col = mapping["dest_col"]
            src_table = mapping["src_table"]
            src_col = mapping["src_col"]
            # Find the matching source db for this src_table
            src_db = next(
                (src["database"] for src in sources if src["table"] == src_table),
                dest["database"],
            )
            src_aid = source_asset_ids.get((src_db, src_table), f"{src_db}__{src_table}")
            if dest_col not in col_fields:
                col_fields[dest_col] = ColumnLineageField(name=dest_col, source_fields=[])
            col_fields[dest_col].source_fields.append(
                ColumnLineageSourceField(asset_id=src_aid, field_name=src_col)
            )

        events.append(
            LineageEvent(
                destination=LineageAssetRef(
                    type="TABLE",
                    name=dest["table"],
                    database=dest["database"],
                    schema=dest["database"],
                    asset_id=dest_asset_id,
                ),
                sources=[
                    LineageAssetRef(
                        type="TABLE",
                        name=src["table"],
                        database=src["database"],
                        schema=src["database"],
                        asset_id=source_asset_ids[(src["database"], src["table"])],
                    )
                    for src in sources
                ],
                fields=list(col_fields.values()) if col_fields else None,
            )
        )
    return events


def push(
    manifest: dict,
    resource_uuid: str,
    key_id: str,
    key_token: str,
    column_lineage: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str | None:
    """
    Push collected lineage to Monte Carlo and update the manifest in-place.

    Events are sent in batches of ``batch_size`` (default 500) to avoid
    oversized payloads.  Supports both table-level and column-level lineage.

    Args:
        manifest: Dict loaded from a ``collect_lineage.py`` output file.
        resource_uuid: MC resource UUID for this Hive connection.
        key_id: MC ingestion key ID.
        key_token: MC ingestion key token.
        column_lineage: When True, push column-level lineage; otherwise table-level.
        batch_size: Events per POST request (default 500).
        timeout_seconds: HTTP timeout per request (default 120).

    Returns:
        The last invocation ID string if returned by MC, otherwise None.
    """
    resource_type = manifest.get("resource_type", RESOURCE_TYPE)
    edges_data = manifest.get("edges", [])

    if column_lineage:
        events = _build_column_lineage(edges_data)
        label = "column-level"
    else:
        events = _build_table_lineage(edges_data)
        label = "table-level"

    n = len(events)
    batches = (n + batch_size - 1) // batch_size if n else 0

    if batches > 1:
        print(f"Pushing {n} {label} lineage event(s) to Monte Carlo in {batches} batch(es) of up to {batch_size} ...")
    else:
        print(f"Pushing {n} {label} lineage event(s) to Monte Carlo ...")

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
            result = service.send_lineage(
                resource_uuid=resource_uuid,
                resource_type=resource_type,
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

    manifest["resource_uuid"] = resource_uuid
    manifest["invocation_id"] = last_id
    if len(invocation_ids) > 1:
        manifest["invocation_ids"] = invocation_ids
    elif "invocation_ids" in manifest:
        del manifest["invocation_ids"]

    return last_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push a collected Hive lineage manifest to Monte Carlo",
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
        help="Monte Carlo resource UUID for this Hive connection (env: MC_RESOURCE_UUID)",
    )
    parser.add_argument(
        "--input-file",
        default="lineage_output.json",
        help="Path to the JSON manifest written by collect_lineage.py (default: lineage_output.json)",
    )
    parser.add_argument(
        "--column-lineage",
        action="store_true",
        help="Push column-level lineage instead of table-level",
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
    if not args.resource_uuid:
        parser.error("--resource-uuid is required (or set MC_RESOURCE_UUID)")

    with open(args.input_file) as fh:
        manifest = json.load(fh)

    push(
        manifest=manifest,
        resource_uuid=args.resource_uuid,
        key_id=args.key_id,
        key_token=args.key_token,
        column_lineage=args.column_lineage,
        batch_size=args.batch_size,
        timeout_seconds=args.timeout,
    )

    with open(args.input_file, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"Manifest updated in-place: {args.input_file}")
    print("Done.")


if __name__ == "__main__":
    main()
