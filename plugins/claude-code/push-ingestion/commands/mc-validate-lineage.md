# /mc-validate-lineage

Verify that pushed table and column lineage is visible in Monte Carlo via the GraphQL API.

## What to ask the customer

1. **Destination table**: the table that should have sources (database, schema, table)
2. **Expected source tables**: list of source tables that should appear upstream
3. **Warehouse UUID**
4. **Column lineage?**: specific source column → destination column mappings to check?

## Timing note

Table lineage appears within **seconds to a few minutes** after push (fast direct path to
Neo4j). Column lineage may take a few more minutes. If the customer just pushed, wait 2–3
minutes before running verification.

## Verification steps

### Step 1 — Resolve destination table MCON

```graphql
query {
  getTable(fullTableId: "<database>:<schema>.<table>", dwId: "<warehouse-uuid>") {
    mcon
    fullTableId
  }
}
```

### Step 2 — Check upstream table lineage

```graphql
query {
  getTableLineage(mcon: "<destination-mcon>", direction: "upstream", hops: 1) {
    connectedNodes { mcon displayName objectId }
    flattenedEdges { directlyConnectedMcons }
  }
}
```

Check that each expected source table's MCON appears in `connectedNodes` or
`flattenedEdges[].directlyConnectedMcons`.

### Step 3 — Check column lineage (optional)

For each source table + source column, verify the destination table and column appear:

```graphql
query {
  getDerivedTablesPartialLineage(
    mcon: "<source-table-mcon>"
    column: "<source-column-name>"
    pageSize: 1000
  ) {
    destinations {
      table { mcon displayName }
      columns { columnName }
    }
  }
}
```

## Python helper

Load `scripts/sample_verify.py` for the `verify_table_lineage()` and `verify_column_lineage()` functions.
