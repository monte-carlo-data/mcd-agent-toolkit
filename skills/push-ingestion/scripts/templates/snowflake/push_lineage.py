#!/usr/bin/env python3
"""
Push lineage events to Monte Carlo from a JSON manifest — push only.

Reads a manifest file produced by ``collect_lineage.py`` and sends the lineage
events to Monte Carlo using the pycarlo push ingestion API.  Large payloads are
split into batches to stay under the 1 MB compressed limit.

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
    python push_lineage.py \\
        --key-id  <MC_INGEST_KEY_ID> \\
        --key-token <MC_INGEST_KEY_TOKEN> \\
        --resource-uuid <MC_RESOURCE_UUID> \\
        --input-file lineage_output.json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from pycarlo.core import Client, Session
from pycarlo.features.ingestion import IngestionService
from pycarlo.features.ingestion.models import (
    ColumnLineageField,
    ColumnLineageSourceField,
    LineageAssetRef,
    LineageEvent,
)

# ← SUBSTITUTE: set RESOURCE_TYPE to match your Monte Carlo connection type
RESOURCE_TYPE = "snowflake"

# Maximum events per batch — conservative default to keep compressed payload under 1 MB
# ← SUBSTITUTE: tune based on average edge complexity (number of sources, column mappings)
_BATCH_SIZE = 500


def _build_table_lineage_events(edges: list[dict]) -> list[LineageEvent]:
    """Build table-level LineageEvent objects from manifest edge dicts."""
    events = []
    for edge in edges:
        dest = edge["destination"]
        sources = edge.get("sources", [])
        if not sources:
            continue
        events.append(
            LineageEvent(
                destination=LineageAssetRef(
                    type="TABLE",
                    name=dest["table"],
                    database=dest["database"],
                    schema=dest["schema"],
                ),
                sources=[
                    LineageAssetRef(
                        type="TABLE",
                        name=s["table"],
                        database=s["database"],
                        schema=s["schema"],
                    )
                    for s in sources
                ],
            )
        )
    return events


def _build_column_lineage_events(edges: list[dict]) -> list[LineageEvent]:
    """Build column-level LineageEvent objects from manifest edge dicts."""
    events = []
    for edge in edges:
        dest = edge["destination"]
        sources = edge.get("sources", [])
        col_mappings = edge.get("col_mappings", [])
        if not sources:
            continue

        dest_asset_id = f"{dest['database']}__{dest['schema']}__{dest['table']}"
        source_asset_ids = {
            (s["database"], s["schema"], s["table"]): f"{s['database']}__{s['schema']}__{s['table']}"
            for s in sources
        }

        col_fields: dict[str, ColumnLineageField] = {}
        for mapping in col_mappings:
            dest_col = mapping["dest_col"]
            src_table = mapping["src_table"]
            src_col = mapping["src_col"]
            # Match src_table to the first source with that table name
            match = next(
                (s for s in sources if s["table"] == src_table),
                sources[0] if sources else None,
            )
            if not match:
                continue
            src_aid = source_asset_ids[(match["database"], match["schema"], match["table"])]
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
                    schema=dest["schema"],
                    asset_id=dest_asset_id,
                ),
                sources=[
                    LineageAssetRef(
                        type="TABLE",
                        name=s["table"],
                        database=s["database"],
                        schema=s["schema"],
                        asset_id=source_asset_ids[(s["database"], s["schema"], s["table"])],
                    )
                    for s in sources
                ],
                fields=list(col_fields.values()) if col_fields else None,
            )
        )
    return events


def push(
    input_file: str,
    resource_uuid: str,
    key_id: str,
    key_token: str,
    batch_size: int = _BATCH_SIZE,
    output_file: str = "lineage_push_result.json",
) -> dict:
    """
    Read a lineage manifest and push events to Monte Carlo in batches.

    Returns a result dict with invocation IDs for each batch.
    """
    with open(input_file) as fh:
        manifest = json.load(fh)

    edges = manifest.get("edges", [])
    resource_type = manifest.get("resource_type", RESOURCE_TYPE)
    column_lineage = manifest.get("column_lineage", False)

    if column_lineage:
        events = _build_column_lineage_events(edges)
        label = "column-level"
    else:
        events = _build_table_lineage_events(edges)
        label = "table-level"

    print(f"Loaded {len(events)} {label} lineage event(s) from {input_file}")

    if not events:
        print("No lineage events to push.")
        push_result = {
            "resource_uuid": resource_uuid,
            "resource_type": resource_type,
            "invocation_ids": [],
            "pushed_at": datetime.now(tz=timezone.utc).isoformat(),
            "total_events": 0,
            "batch_count": 0,
            "batch_size": batch_size,
        }
        with open(output_file, "w") as fh:
            json.dump(push_result, fh, indent=2)
        return push_result

    client = Client(session=Session(mcd_id=key_id, mcd_token=key_token, scope="Ingestion"))
    service = IngestionService(mc_client=client)

    invocation_ids: list[str | None] = []
    total_batches = (len(events) + batch_size - 1) // batch_size or 1

    for i in range(0, len(events), batch_size):
        batch = events[i : i + batch_size]
        batch_num = i // batch_size + 1
        print(f"  Pushing batch {batch_num}/{total_batches} ({len(batch)} events) ...")

        result = service.send_lineage(
            resource_uuid=resource_uuid,
            resource_type=resource_type,
            events=batch,
        )
        invocation_id = service.extract_invocation_id(result)
        invocation_ids.append(invocation_id)
        print(f"    Response: {json.dumps(result, indent=2) if result else '(empty)'}")
        if invocation_id:
            print(f"    Invocation ID: {invocation_id}")

    push_result = {
        "resource_uuid": resource_uuid,
        "resource_type": resource_type,
        "invocation_ids": invocation_ids,
        "pushed_at": datetime.now(tz=timezone.utc).isoformat(),
        "total_events": len(events),
        "batch_count": total_batches,
        "batch_size": batch_size,
    }
    with open(output_file, "w") as fh:
        json.dump(push_result, fh, indent=2)
    print(f"Push result written to {output_file}")

    return push_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push Snowflake lineage from a manifest to Monte Carlo",
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
        default="lineage_output.json",
        help="Path to the collect manifest to read (default: lineage_output.json)",
    )
    parser.add_argument(
        "--output-file",
        default="lineage_push_result.json",
        help="Path to write the push result (default: lineage_push_result.json)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_BATCH_SIZE,
        help=f"Max events per push batch (default: {_BATCH_SIZE})",
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
