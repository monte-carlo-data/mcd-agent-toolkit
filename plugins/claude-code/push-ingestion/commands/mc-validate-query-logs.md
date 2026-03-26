# /mc-validate-query-logs

Verify that pushed query logs are visible in Monte Carlo via the GraphQL API.

## Important: async processing delay

Query logs take **at least 15-20 minutes** to process after push. If the customer just pushed,
ask them to wait before running this command. Seeing 0 results immediately is expected.

## What to ask the customer

1. **Tables to check**: which tables should have query activity?
2. **Time window**: start and end time of the pushed logs (ISO-8601)
3. **Warehouse UUID**
4. **Query type**: `"read"` (SELECT), `"write"` (INSERT/UPDATE/DELETE/CREATE), or both?

## Verification steps

### Step 1 — Resolve table MCON

```graphql
query {
  getTable(fullTableId: "<database>:<schema>.<table>", dwId: "<warehouse-uuid>") {
    mcon
    fullTableId
  }
}
```

### Step 2 — Check aggregated query counts

```graphql
query {
  getAggregatedQueries(
    mcon: "<table-mcon>"
    queryType: "read"
    startTime: "<ISO-start>"
    endTime: "<ISO-end>"
    first: 100
    after: null
  ) {
    edges {
      node {
        queryHash
        queryCount
        lastSeen
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
```

Repeat with `queryType: "write"` for write queries. Paginate using `endCursor` if `hasNextPage` is true.

### Step 3 — Interpret results

- **0 results, pushed < 20 minutes ago**: normal — processing is async, wait and retry
- **0 results, pushed > 20 minutes ago**: check the `invocation_id` from the output manifest
  in CloudWatch logs; verify `log_type` matches the warehouse; check if queries
  reference the specific table by name (queries that only use `SHOW DATABASES` or `SHOW TABLES`
  won't attribute to any specific table)
- **Results present**: confirm `queryCount` matches the number of queries pushed

## Python helper

Load `scripts/sample_verify.py` for the `verify_query_logs()` function.
