# /mc-build-lineage-collector

Generate a Python script that collects table and column lineage from your data warehouse
and pushes it to Monte Carlo.

## What to ask the customer

1. **Warehouse type**: Snowflake, BigQuery, Databricks, Redshift, Hive, or other
2. **MC resource UUID**
3. **Lineage level**: table-only (default) or table + column?
4. **Lookback window**: how many hours/days of query history to scan? (default: 24 hours)
5. **Connection parameters**
6. **Script pattern**: combined (collect + push in one) or separate scripts?

## Warehouse-specific notes

- **Databricks**: uses `system.access.table_lineage` and `system.access.column_lineage` —
  no SQL parsing needed, this is the most reliable source
- **Snowflake / Redshift**: parses `QUERY_HISTORY` / `SYS_QUERY_HISTORY` SQL for CTAS and
  INSERT INTO SELECT patterns
- **BigQuery**: combines `INFORMATION_SCHEMA.SCHEMATA_LINKS` (for data shares) with
  `list_jobs()` SQL parsing
- **Hive**: parses the local HiveServer2 log file (`/tmp/root/hive.log`)

## How to generate the script

1. Check if a template exists in `scripts/templates/<warehouse>/`
2. If a template exists: load it and walk through each `# ← SUBSTITUTE:` comment
3. If **no template exists**: use the existing templates as reference patterns. Study how they
   query system catalogs and parse SQL for lineage, then derive the equivalent approach for
   the customer's warehouse. For file-based sources (like Hive logs), provide the command to
   retrieve the file, parse it, and transform it into `LineageEvent` / `ColumnLineageField` objects.
4. Explain the source (which table/view/log provides the lineage data)
5. Note that push table lineage appears in the MC graph within **seconds to a few minutes** (fast
   direct path to Neo4j via PushLineageProcessor)
6. Note that pushed **table lineage does not expire**, but **column lineage expires after 10 days**
7. Include batching — split events into chunks to stay under the 1MB compressed request limit

## Follow-up

- Offer `/mc-validate-lineage` to verify the pushed edges
- For non-warehouse assets (dbt, Airflow), suggest `/mc-create-lineage-node` + `/mc-create-lineage-edge`
