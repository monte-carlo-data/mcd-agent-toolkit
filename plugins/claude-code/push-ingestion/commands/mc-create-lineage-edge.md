# /mc-create-lineage-edge

Create or update a directed lineage edge between two nodes in Monte Carlo.

## What to ask the customer

1. **Source node**: objectType, objectId, resourceId or resourceName
2. **Destination node**: same fields
3. **Edge direction**: IS_DOWNSTREAM (default) means "destination is downstream of source"
4. **Permanent or temporary?** (default 7 days — always use `"9999-12-31"` for permanent edges)

## Critical: expireAt

Like nodes, edges expire after **7 days** if `expireAt` is not set. For permanent edges:
```
expireAt: "9999-12-31"
```

## NodeInput shape

```graphql
input NodeInput {
  objectType:   String!
  objectId:     String!
  resourceId:   UUID          # use this OR resourceName
  resourceName: String
}
```

## GraphQL mutation

```graphql
mutation CreateOrUpdateLineageEdge(
  $source:      NodeInput!
  $destination: NodeInput!
  $expireAt:    DateTime
  $edgeType:    EdgeType
) {
  createOrUpdateLineageEdge(
    source:      $source
    destination: $destination
    expireAt:    $expireAt
    edgeType:    $edgeType
  ) {
    edge {
      source      { mcon displayName objectType }
      destination { mcon displayName objectType }
      isCustom
      expireAt
    }
  }
}
```

## Example: dbt model → Snowflake table

```json
{
  "source": {
    "objectType": "model",
    "objectId":   "dbt://my_project/models/staging/stg_orders",
    "resourceName": "dbt-production"
  },
  "destination": {
    "objectType": "table",
    "objectId":   "analytics:public.orders",
    "resourceId": "<snowflake-warehouse-uuid>"
  },
  "expireAt":  "9999-12-31",
  "edgeType":  "IS_DOWNSTREAM"
}
```

## Resolving objectId for existing warehouse tables

For tables already in MC, find objectId via:
```graphql
query {
  getTable(fullTableId: "analytics:public.orders", dwId: "<warehouse-uuid>") {
    mcon
    objectId
  }
}
```

Then use that `objectId` in NodeInput.
