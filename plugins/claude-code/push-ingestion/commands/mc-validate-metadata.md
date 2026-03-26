# /mc-validate-metadata

Verify that pushed table metadata is visible and correct in Monte Carlo via the GraphQL API.

## What to ask the customer

1. **Table(s) to check**: database, schema, table name(s)
2. **Warehouse UUID** (MC resource UUID)
3. **GraphQL API key** (`MC_API_KEY_ID` / `MC_API_KEY_TOKEN`)
4. **What to verify**: schema only? schema + row counts? detector status?

## Verification steps

### Step 1 — Resolve the MCON

```graphql
query {
  getTable(fullTableId: "<database>:<schema>.<table>", dwId: "<warehouse-uuid>") {
    mcon
    fullTableId
    displayName
  }
}
```

`fullTableId` format: `database:schema.table` (e.g. `analytics:public.orders`)

### Step 2 — Check schema (columns)

```graphql
query {
  getTable(mcon: "<mcon>") {
    versions {
      edges {
        node {
          fields { name fieldType }
        }
      }
    }
  }
}
```

Compare the returned fields against the customer's expected schema.

### Step 3 — Check volume metrics (optional)

Load `references/validation.md` → "Verify volume and freshness metrics" section.

Use `getMetricsV4` with `metricName: "total_row_count"`.

### Step 4 — Check detector status (optional)

```graphql
query {
  getTable(mcon: "<mcon>") {
    thresholds {
      freshness { status }
      size { status }
    }
  }
}
```

`"no data"` or `"training"` is normal on a newly-pushed table. See anomaly-detection.md for requirements.

## Python helper

Load `scripts/sample_verify.py` for the `graphql()` helper function and pre-built verification functions.
