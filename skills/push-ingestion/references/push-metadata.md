# Pushing Table Metadata

## Overview

Metadata push sends three types of signals per table:
- **Schema** — column names and types
- **Volume** — row count and byte count
- **Freshness** — last update timestamp

All three travel together in a single `RelationalAsset` object via `POST /ingest/v1/metadata`.

**Expiration**: Pushed table metadata **does not expire**. Once pushed, it remains in Monte
Carlo until explicitly deleted via `deletePushIngestedTables`.

**Batching**: For large numbers of tables, split assets into batches. The compressed request
body must not exceed **1MB** (Kinesis limit).

## pycarlo models

```python
from pycarlo.features.ingestion import (
    IngestionService,
    RelationalAsset,
    AssetMetadata,
    AssetField,
    AssetVolume,
    AssetFreshness,
)
```

## Minimal example

```python
from datetime import datetime, timezone

asset = RelationalAsset(
    metadata=AssetMetadata(
        database="analytics",
        schema="public",
        table_name="orders",
        description="Order transactions",
    ),
    fields=[
        AssetField(name="order_id", field_type="INTEGER"),
        AssetField(name="amount",   field_type="DECIMAL"),
        AssetField(name="created_at", field_type="TIMESTAMP"),
    ],
    volume=AssetVolume(
        row_count=1_500_000,
        total_byte_size=250_000_000,
    ),
    freshness=AssetFreshness(
        last_update_time=datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
    ),
)

result = service.send_metadata(
    resource_uuid="<your-resource-uuid>",
    resource_type="data-lake",   # see note below on resource_type
    assets=[asset],
)
print("invocation_id:", result.invocation_id)   # save this!
```

## resource_type

The `resource_type` value must match the type of the MC resource (warehouse connection) you
are pushing to. Use the same string that appears in the MC UI or the `connectionType` field
from `getUser { account { warehouses { connectionType } } }`.

Common values:
- `"data-lake"` — Hive, EMR, Glue, generic data lake connections
- `"snowflake"` — Snowflake
- `"bigquery"` — BigQuery
- `"databricks"` — Databricks Unity Catalog
- `"redshift"` — Redshift

## Field types

Normalize to SQL-standard uppercase strings. Monte Carlo accepts any string but canonical
values like `INTEGER`, `BIGINT`, `VARCHAR`, `FLOAT`, `BOOLEAN`, `TIMESTAMP`, `DATE`,
`DECIMAL`, `ARRAY`, `STRUCT` work best with downstream features.

## Volume and freshness are optional

If your warehouse doesn't expose row counts or last-modified timestamps, omit `volume`
and/or `freshness` — schema-only metadata is valid.

If you send `freshness`, each push must carry a **changed** `last_update_time` to count as
a new data point for the anomaly detector (repeated identical timestamps don't advance the
training clock).

## Batch multiple tables

`assets` accepts a list. Push all tables in a single call or in batches:

```python
result = service.send_metadata(
    resource_uuid=resource_uuid,
    resource_type="data-lake",
    assets=[asset1, asset2, asset3, ...],
)
```

## Output manifest (include invocation_id)

Always write a local manifest so you can trace issues later:

```python
import json
from datetime import datetime, timezone

manifest = {
    "resource_uuid": resource_uuid,
    "invocation_id": result.invocation_id,   # ← critical for debugging
    "collected_at": datetime.now(tz=timezone.utc).isoformat(),
    "assets": [
        {
            "database": a.metadata.database,
            "schema": a.metadata.schema,
            "table": a.metadata.table_name,
            "row_count": a.volume.row_count if a.volume else None,
            "fields": [{"name": f.name, "type": f.field_type} for f in a.fields],
        }
        for a in assets
    ],
}
with open("metadata_output.json", "w") as f:
    json.dump(manifest, f, indent=2)
```

## Push frequency for anomaly detection

To keep volume and freshness anomaly detectors active:
- Push **at most once per hour** (pushing more frequently produces unpredictable behavior)
- Push **consistently** — gaps longer than a few days will deactivate detectors
- See `references/anomaly-detection.md` for minimum sample requirements
