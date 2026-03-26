# /mc-delete-push-tables

Delete push-ingested table assets from Monte Carlo.

**Only works on push-ingested tables** — tables collected via the pull model are excluded
by default and will not be deleted by this operation.

**This operation is irreversible.** Always confirm the MCONs with the customer before executing.

## When to use this

- A table was push-ingested by mistake and needs to be removed
- A push-ingested table has been dropped from the warehouse and should no longer appear in MC
- Cleaning up after testing a push flow

## Note on the pull deletion flow

Pull-collected tables are removed when the collector stops seeing them for 2+ days. Push
tables are intentionally excluded from this flow (`exclude_push_tables=True` by default)
because MC can't know whether a push table is still valid just because it wasn't re-sent
recently. This command is the explicit opt-in deletion path for push tables.

## What to ask the customer

1. **Which tables?** — table names (database, schema, table) or MCONs directly
2. **Confirm** — show the list of MCONs that will be deleted before executing

## Step 1 — Resolve MCONs

```graphql
query {
  getTable(fullTableId: "<database>:<schema>.<table>", dwId: "<warehouse-uuid>") {
    mcon
    fullTableId
    displayName
  }
}
```

Run for each table. Collect the MCONs.

## Step 2 — Delete

```graphql
mutation DeletePushTables($mcons: [String!]!) {
  deletePushIngestedTables(mcons: $mcons) {
    success
    deletedCount
  }
}
```

Variables:
```json
{ "mcons": ["<mcon-1>", "<mcon-2>"] }
```

The response shows `success` (boolean) and `deletedCount`.

## Operational details

- **Limit: 1,000 MCONs per call.** For larger batches, split into multiple requests.
- **All-or-nothing validation**: if any MCON is invalid or not found, **no deletions occur**.
  Verify all MCONs first.
- **Neo4j cleanup included**: the mutation also bulk-deletes the lineage nodes **and all edges
  touching those nodes** in Neo4j. Push-ingested lineage nodes have `expire_at = 9999-12-31`,
  so without explicit deletion they would persist forever as orphans in the lineage graph.
- **Postgres soft-delete**: the table records are soft-deleted in Postgres. Neo4j cleanup only
  runs after all Postgres deletions succeed.
