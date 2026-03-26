#!/usr/bin/env python3
"""
Push a collected Hive metadata manifest to Monte Carlo — push only.

Reads a JSON manifest produced by ``collect_metadata.py``, builds
RelationalAsset objects, and calls ``send_metadata`` in batches.  The manifest
is updated in-place with ``resource_uuid`` and ``invocation_id`` after a
successful push.

Can be run standalone via CLI or imported (use the ``push()`` function).

Substitution points
-------------------
- MC_INGEST_KEY_ID    (env) / --key-id        (CLI) : Monte Carlo ingestion key ID
- MC_INGEST_KEY_TOKEN (env) / --key-token      (CLI) : Monte Carlo ingestion key token
- MC_RESOURCE_UUID    (env) / --resource-uuid  (CLI) : MC resource UUID for this connection

Prerequisites
-------------
    pip install pycarlo python-dotenv

Usage
-----
    python push_metadata.py \\
        --key-id  <MC_INGEST_KEY_ID> \\
        --key-token <MC_INGEST_KEY_TOKEN> \\
        --resource-uuid <MC_RESOURCE_UUID> \\
        --input-file metadata_output.json
"""

import argparse
import json
import os
from datetime import datetime, timezone

from pycarlo.core import Client, Session
from pycarlo.features.ingestion import IngestionService
from pycarlo.features.ingestion.models import (
    AssetField,
    AssetFreshness,
    AssetMetadata,
    AssetVolume,
    RelationalAsset,
)

# ← SUBSTITUTE: default batch size for metadata push (assets per request)
DEFAULT_BATCH_SIZE = 500

# ← SUBSTITUTE: HTTP timeout for MC ingestion requests (seconds)
DEFAULT_TIMEOUT_SECONDS = 120


def _build_assets(manifest: dict) -> list[RelationalAsset]:
    """Rebuild RelationalAsset objects from a collected metadata manifest."""
    assets = []
    for a in manifest.get("assets", []):
        fields = [
            AssetField(
                name=f["name"],
                type=f["type"],
                description=f.get("description"),
            )
            for f in a.get("fields", [])
        ]

        volume = None
        row_count = a.get("row_count")
        byte_count = a.get("byte_count")
        if row_count or byte_count:
            volume = AssetVolume(
                row_count=row_count if row_count and row_count > 0 else None,
                byte_count=byte_count if byte_count and byte_count > 0 else None,
            )

        freshness = None
        last_modified = a.get("last_modified")
        if last_modified:
            freshness = AssetFreshness(last_update_time=last_modified)

        assets.append(
            RelationalAsset(
                type="TABLE",
                metadata=AssetMetadata(
                    name=a["name"],
                    database=a["database"],
                    schema=a["schema"],
                    description=a.get("description"),
                    created_on=a.get("created_on"),
                ),
                fields=fields,
                volume=volume,
                freshness=freshness,
            )
        )
    return assets


def push(
    manifest: dict,
    resource_uuid: str,
    key_id: str,
    key_token: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str | None:
    """
    Push collected metadata to Monte Carlo and update the manifest in-place.

    Assets are sent in batches of ``batch_size`` (default 500) to avoid
    oversized payloads.  The manifest is enriched with ``resource_uuid``
    and the last ``invocation_id`` from the response.

    Args:
        manifest: Dict loaded from a ``collect_metadata.py`` output file.
        resource_uuid: MC resource UUID for this Hive connection.
        key_id: MC ingestion key ID.
        key_token: MC ingestion key token.
        batch_size: Assets per POST request (default 500).
        timeout_seconds: HTTP timeout per request (default 120).

    Returns:
        The last invocation ID string if returned by MC, otherwise None.
    """
    resource_type = manifest.get("resource_type", "data-lake")

    assets = _build_assets(manifest)
    n = len(assets)
    batches = (n + batch_size - 1) // batch_size if n else 0

    if batches > 1:
        print(f"Pushing {n} asset(s) to Monte Carlo in {batches} batch(es) of up to {batch_size} ...")
    else:
        print(f"Pushing {n} asset(s) to Monte Carlo ...")

    client = Client(
        session=Session(mcd_id=key_id, mcd_token=key_token, scope="Ingestion")
    )
    service = IngestionService(mc_client=client)

    invocation_ids: list[str] = []
    for b in range(batches):
        lo = b * batch_size
        hi = min(lo + batch_size, n)
        part = assets[lo:hi]
        try:
            result = service.send_metadata(
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
            print(f"  Batch {b + 1}/{batches}: {len(part)} assets — response: {json.dumps(result) if result else '(empty)'}")
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
        description="Push a collected Hive metadata manifest to Monte Carlo",
    )
    parser.add_argument(
        "--key-id",
        default=os.environ.get("MC_INGEST_KEY_ID"),
        help="Monte Carlo ingestion key ID (env: MC_INGEST_KEY_ID)",  # ← SUBSTITUTE env var name if different
    )
    parser.add_argument(
        "--key-token",
        default=os.environ.get("MC_INGEST_KEY_TOKEN"),
        help="Monte Carlo ingestion key token (env: MC_INGEST_KEY_TOKEN)",  # ← SUBSTITUTE env var name if different
    )
    parser.add_argument(
        "--resource-uuid",
        default=os.environ.get("MC_RESOURCE_UUID"),
        required=False,
        help="Monte Carlo resource UUID for this Hive connection (env: MC_RESOURCE_UUID)",
    )
    parser.add_argument(
        "--input-file",
        default="metadata_output.json",
        help="Path to the JSON manifest written by collect_metadata.py (default: metadata_output.json)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        metavar="N",
        help=f"Max assets per POST (default: {DEFAULT_BATCH_SIZE})",
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
        batch_size=args.batch_size,
        timeout_seconds=args.timeout,
    )

    with open(args.input_file, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"Manifest updated in-place: {args.input_file}")
    print("Done.")


if __name__ == "__main__":
    main()
