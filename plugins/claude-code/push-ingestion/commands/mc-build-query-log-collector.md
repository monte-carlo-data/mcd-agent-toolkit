# /mc-build-query-log-collector

Generate a Python script that collects query execution history from your data warehouse
and pushes it to Monte Carlo as query logs.

## What to ask the customer

1. **Warehouse type**: Snowflake, BigQuery, Databricks, Redshift, Hive, or other
2. **MC resource UUID**
3. **Lookback window**: how many hours to collect? (default: 24 hours)
4. **Filters**: specific databases? specific users? minimum query duration?
5. **Connection parameters**

## Critical note on log_type

Query logs use `log_type` (not `resource_type` — this is the only push endpoint where the
field name differs). **Always confirm the correct value** for the customer's warehouse:

| Warehouse | log_type |
|---|---|
| Snowflake | `"snowflake"` |
| BigQuery | `"bigquery"` |
| Databricks | `"databricks"` |
| Redshift | `"redshift"` |
| Hive (EMR) | `"hive-s3"` |
| Athena | `"athena"` |
| Teradata | `"teradata"` |
| ClickHouse | `"clickhouse"` |
| Databricks (SQL Warehouse) | `"databricks-metastore-sql-warehouse"` |
| S3 | `"s3"` |
| Presto (S3) | `"presto-s3"` |

Using the wrong value causes `ValueError: Unsupported ingest query-log log_type`.

## Async processing lag

After pushing, query logs take **at least 15-20 minutes** to appear in `getAggregatedQueries`.
This is expected — tell the customer not to worry if they see 0 results immediately.

## Warehouse-specific latency notes

- **Snowflake `ACCOUNT_USAGE`**: 45-minute write latency — skip the most recent hour when collecting
- **BigQuery**: uses `list_jobs()` API — near real-time
- **Databricks `system.query.history`**: a few minutes of latency
- **Redshift `sys_query_history`**: near real-time on modern clusters; `STL_QUERY` on older ones

## What to ask about script structure

5. **Script pattern**: does the customer want:
   - **Combined** (collect + push in one script) — simplest, good for cron jobs
   - **Separate** (collect script + push script) — useful if they want to inspect collected
     data before pushing, or reuse collection without pushing

## How to generate the script

1. Check if a template exists in `scripts/templates/<warehouse>/`
2. If a template exists: load it and walk through `# ← SUBSTITUTE:` comments
3. If **no template exists**: use the existing templates as reference patterns. Study how they
   query system catalogs and build `QueryLogEntry` objects, then derive the equivalent queries
   for the customer's warehouse. For file-based sources (like Hive logs), provide the command
   to retrieve the file, parse it, and transform it into `QueryLogEntry` objects.
4. Explain the query history source and the `end_time` requirement (required, easy to miss)
5. Point out the `returned_rows` field if the warehouse exposes it
6. Include batching — split entries into chunks (default 250) to stay under the 1MB compressed
   request limit

## Follow-up

- Offer `/mc-validate-query-logs` to verify pushed logs (wait at least 15-20 minutes first)
