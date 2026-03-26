# /mc-delete-lineage-node

Delete a custom lineage node from Monte Carlo. This also removes all edges and objects
associated with the node.

**This operation is irreversible.** Always confirm with the customer before executing.

## What to ask the customer

1. **Which node?** — MCON, or enough info to resolve it (objectType + objectId + resource)
2. **Confirm** — show the customer what will be deleted (node + all connected edges) before executing

## Find the MCON if unknown

If the customer has the MCON from a previous `createOrUpdateLineageNode` call, use it directly.

Otherwise, for a warehouse table:
```graphql
query {
  getTable(fullTableId: "<database>:<schema>.<table>", dwId: "<warehouse-uuid>") {
    mcon
    displayName
  }
}
```

## GraphQL mutation

```graphql
mutation DeleteLineageNode($mcon: String!) {
  deleteLineageNode(mcon: $mcon) {
    objectsDeleted
    nodesDeleted
    edgesDeleted
  }
}
```

Variables:
```json
{ "mcon": "<node-mcon>" }
```

The response shows how many objects, nodes, and edges were removed.

## Note

This mutation works on **custom** lineage nodes (created via `createOrUpdateLineageNode` or
push-ingested via `IngestionService.send_lineage()`). Pull-collected tables are managed by
the collector, not by this API.

To delete **push-ingested tables** (the asset record, not just the lineage node), use
`/mc-delete-push-tables` instead.
