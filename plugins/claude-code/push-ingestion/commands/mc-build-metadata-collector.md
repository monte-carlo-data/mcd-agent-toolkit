# /mc-build-metadata-collector

Generate a Python script that collects table metadata from your data warehouse and pushes
it to Monte Carlo using the push ingestion API.

## What to ask the customer

1. **Warehouse type** (if not already stated): Snowflake, BigQuery, Databricks, Redshift, Hive, or other
2. **MC resource UUID** (the UUID of the warehouse connection in Monte Carlo)
3. **Connection parameters**: host/account, credentials format, any database/schema filters
4. **What to include**: schema only? schema + row counts? schema + row counts + freshness?
5. **Script pattern**: does the customer want:
   - **Combined** (collect + push in one script) — simplest, good for cron jobs
   - **Separate** (collect script + push script) — useful if they want to inspect collected
     data before pushing, or reuse collection without pushing

## How to generate the script

1. Check if a template exists in `scripts/templates/<warehouse>/`
2. If a template exists: load it and walk through each `# ← SUBSTITUTE:` comment with the
   customer and fill in their values
3. If **no template exists**: use the existing templates as reference patterns. Study how they
   query system catalogs and build `RelationalAsset` objects, then derive the equivalent queries
   for the customer's warehouse or metadata API. For file-based sources (like Hive Metastore),
   provide the command to retrieve the file, parse it, and transform it into the pycarlo models.
4. Explain what each section does — which warehouse views/API it queries, what it extracts
5. Show the pycarlo push call and explain the `invocation_id` they should save
6. Explain the output manifest file (metadata_output.json)
7. Include batching — split assets into chunks to stay under the 1MB compressed request limit

## Follow-up

After generating:
- Offer to generate the validation script too (`/mc-validate-metadata`)
- Remind them to set up their Ingestion key if they haven't already (see prerequisites.md)
- Mention that anomaly detection needs consistent hourly pushes to activate (see anomaly-detection.md)
