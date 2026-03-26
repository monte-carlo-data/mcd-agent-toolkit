# /mc-create-lineage-node

Create or update a custom lineage node in Monte Carlo via the GraphQL API.

Use this for non-warehouse assets: dbt models, Airflow DAGs, Fivetran connectors, BI
dashboards, custom ETL jobs — anything that's not a table/view in a registered MC warehouse.

## What to ask the customer

1. **objectType**: what kind of asset is this? (e.g. `"table"`, `"view"`, `"model"`,
   `"report"`, `"dashboard"`, `"job"`)
2. **objectId**: a stable unique identifier for this asset within the resource
   (e.g. `"dbt://my_project/models/staging/stg_orders"` or `"analytics:public.orders"`)
3. **Resource**: which MC warehouse/resource does this belong to?
   Use `resourceId` (UUID) or `resourceName` (string name)
4. **Display name**: human-readable name for the MC UI
5. **Permanent or temporary?** (default is 7 days — use `"9999-12-31"` for permanent)

## Critical: expireAt

If you don't set `expireAt`, the node **expires after 7 days** and vanishes silently.
For any node that should persist in the lineage graph, always use:
```
expireAt: "9999-12-31"
```

## GraphQL mutation

```graphql
mutation CreateOrUpdateLineageNode(
  $objectType: String!
  $objectId:   String!
  $resourceId:   UUID
  $resourceName: String
  $name:       String
  $expireAt:   DateTime
) {
  createOrUpdateLineageNode(
    objectType:   $objectType
    objectId:     $objectId
    resourceId:   $resourceId
    resourceName: $resourceName
    name:         $name
    expireAt:     $expireAt
  ) {
    node { mcon displayName objectType isCustom expireAt }
  }
}
```

**Save the returned `mcon`** — you'll need it to create edges or delete this node later.

## After creating the node

Offer to create edges connecting this node to other assets using `/mc-create-lineage-edge`.
