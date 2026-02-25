---
name: monte-carlo
description: |
  Use this skill when working with dbt models, SQL files, or data pipelines where you need
  table health, lineage, active alerts, or data quality monitors from Monte Carlo Data.
  Activate when the user opens or edits a dbt model, asks about a table's status, wants to
  add monitoring for new logic, or needs to triage a data quality incident.
version: 1.0.0
---

# Monte Carlo Data — AI Editor Skill

This skill brings Monte Carlo's data observability context directly into your editor. When you're modifying a dbt model or SQL pipeline, use it to surface table health, lineage, active alerts, and to generate monitors-as-code without leaving Claude Code.

## When to activate this skill

Activate proactively when the user:
- Opens or edits a `.sql` file, `.py` file, or dbt model (files in `models/`)
- Mentions a table name, dataset, or dbt model by name
- Asks about data quality, freshness, row counts, or anomalies
- Is about to modify a model (rename/drop a column, change a join, add a filter)
- Adds new transformation logic and might need a validation monitor
- Wants to triage or respond to a data quality alert

## Available MCP tools

All tools are available via the `monte-carlo` MCP server.

| Tool | Purpose |
|---|---|
| `testConnection` | Verify auth and connectivity |
| `search` | Find tables/assets by name |
| `getTable` | Schema, stats, freshness, row counts, monitoring status |
| `getAssetLineage` | Upstream sources and downstream dependents |
| `getAlerts` | Active incidents and alerts (use snake_case params — see below) |
| `getMonitors` | List monitors on a table |
| `getQueriesForTable` | Recent query history |
| `getQueryData` | Full SQL for a specific query |
| `createValidationMonitorMac` | Generate monitors-as-code YAML for a validation rule |
| `getValidationPredicates` | List available validation rule types |
| `updateAlert` | Update alert status or severity |
| `setAlertOwner` | Assign alert ownership |
| `createOrUpdateAlertComment` | Add comments to alerts |
| `getDomains` | List MC domains |
| `getUser` | Current user info |
| `getCurrentTime` | ISO timestamp (useful for alert time windows) |

## Core workflows

### 1. Table health check — when opening or editing a model

When the user opens a dbt model or mentions a table, run this sequence automatically:

```
1. search(query="<table_name>") → get the full MCON/table identifier
2. getTable(mcon="<mcon>") → schema, freshness, row count, importance score, monitoring status
3. getAssetLineage(mcon="<mcon>") → upstream sources, downstream dependents
4. getAlerts(created_after="<7 days ago>", created_before="<now>", table_mcons=["<mcon>"]) → active alerts
```

Summarize for the user:
- **Health**: last updated, row count, is it monitored?
- **Lineage**: N upstream sources, M downstream consumers (name the important ones)
- **Alerts**: any active/unacknowledged incidents — lead with these if present
- **Risk signals** (lite): flag if importance score is high, if key assets are downstream, or if alerts are already firing — these indicate the table warrants extra care before modification

Example summary to offer unprompted when a dbt model file is opened:
> "The table `orders_status` was last updated 2 hours ago with 142K rows. It has 3 downstream dependents including `order_status_snapshot` (key asset). There are 2 active freshness alerts — this table warrants extra care before modification. Want me to run a full change impact assessment?"

### 2. Add a monitor — when new transformation logic is added

When the user adds a new column, filter, or business rule, suggest adding a validation monitor:

```
1. getValidationPredicates() → show what validation types are available
2. createValidationMonitorMac(
     mcon="<table_mcon>",
     description="<what the rule checks>",
     condition_sql="<the validation SQL>"
   ) → returns YAML
   ⚠ If this fails (e.g. column doesn't exist yet in the live table), fall back to:
   createCustomSqlMonitorMac(
     mcon="<table_mcon>",
     description="<what the rule checks>",
     sql="<your validation SQL that returns violating rows>"
   )
3. Save the YAML to <project>/monitors/<table_name>.yml
4. Run: montecarlo monitors apply --dry-run (to preview)
5. Run: montecarlo monitors apply --auto-yes (to apply)
```

**Important — YAML format for `monitors apply`:**
Both `createValidationMonitorMac` and `createCustomSqlMonitorMac` return YAML that is not directly compatible with `montecarlo monitors apply`. Reformat the output into a standalone monitor file with `montecarlo:` as the root key:

```yaml
# monitors/<table_name>.yml  ← monitor definitions only, NOT montecarlo.yml
montecarlo:
  custom_sql:
    - warehouse: <warehouse_name>
      name: <monitor_name>
      description: <description>
      schedule:
        interval_minutes: 720
        start_time: '<ISO timestamp>'
      sql: <your validation SQL>
      alert_conditions:
        - operator: GT
          threshold_value: 0.0
```

The `montecarlo.yml` project config is a **separate file** in the project root containing only:
```yaml
# montecarlo.yml  ← project config only, NOT monitor definitions
version: 1
namespace: <your-namespace>
default_resource: <warehouse_name>
```

Do NOT put `version:`, `namespace:`, or `default_resource:` inside monitor definition files.

### 3. Alert triage — when investigating an active incident

```
1. getAlerts(
     created_after="<start>",
     created_before="<end>",
     order_by="-createdTime",
     statuses=["NOT_ACKNOWLEDGED"]
   ) → list open alerts
2. getTable(mcon="<affected_table_mcon>") → check current table state
3. getAssetLineage(mcon="<mcon>") → identify upstream cause or downstream blast radius
4. getQueriesForTable(mcon="<mcon>") → recent queries that might explain the anomaly
```

To respond to an alert:
- `updateAlert(alert_id="<id>", status="ACKNOWLEDGED")` — acknowledge it
- `setAlertOwner(alert_id="<id>", owner="<email>")` — assign ownership
- `createOrUpdateAlertComment(alert_id="<id>", comment="<text>")` — add context

### 4. Change impact assessment — before modifying a model

When the user is about to rename or drop a column, change a join condition, alter a filter, or refactor a model's logic, run this sequence to surface the blast radius before any changes are committed:

```
1. search(query="<table_name>") + getTable(mcon="<mcon>")
   → importance score, query volume (reads/writes per day), key asset flag

2. getAssetLineage(mcon="<mcon>")
   → full list of downstream dependents; for each, note whether it is a key asset

3. getTable(mcon="<downstream_mcon>") for each key downstream asset
   → importance score, last updated, monitoring status

4. getAlerts(
     created_after="<7 days ago>",
     created_before="<now>",
     table_mcons=["<mcon>", "<downstream_mcon_1>", ...],
     statuses=["NOT_ACKNOWLEDGED"]
   )
   → any active incidents already affecting this table or its dependents

5. getQueriesForTable(mcon="<mcon>")
   → recent queries; scan for references to the specific columns being changed
   → use getQueryData(query_id="<id>") to fetch full SQL for ambiguous cases

6. getMonitors(mcon="<mcon>")
   → which monitors are watching columns or metrics affected by the change
```

Assess and report a **risk tier**:

| Tier | Conditions |
|---|---|
| 🔴 High | Key asset downstream, OR active alerts already firing, OR >50 reads/day |
| 🟡 Medium | Non-key assets downstream, OR monitors on affected columns, OR moderate query volume |
| 🟢 Low | No downstream dependents, no active alerts, low query volume |

Report format:
```
## Change Impact: <table_name>

Risk: 🔴 High / 🟡 Medium / 🟢 Low

Downstream blast radius:
  - <N> tables depend on this model
  - Key assets affected: <list or "none">

Active incidents:
  - <alert title, status> or "none"

Column exposure (for columns being changed):
  - Found in <N> recent queries (e.g. <query snippet>)

Monitor coverage:
  - <monitor name> watches <metric> — will be affected by this change

Recommendation:
  - <specific callout, e.g. "Notify owners of downstream_table before deploying",
     "Coordinate with the freshness alert owner", "Add a monitor for the new column">
```

If risk is 🔴 High, proactively suggest:
- Notifying owners of downstream key assets (`setAlertOwner` / `createOrUpdateAlertComment` on active alerts)
- Adding a monitor for the new logic before deploying (Workflow 2)
- Running `montecarlo monitors apply --dry-run` after changes to verify nothing breaks

## Important parameter notes

### `getAlerts` — use snake_case parameters
The MCP tool uses Python snake_case, **not** the camelCase params from the MC web UI:

```
✓ created_after    (not createdTime.after)
✓ created_before   (not createdTime.before)
✓ order_by         (not orderBy)
✓ table_mcons      (not tableMcons)
```

Always provide `created_after` and `created_before`. Max window is 60 days.
Use `getCurrentTime()` to get the current ISO timestamp when needed.

### `search` — finding the right table identifier
MC uses MCONs (Monte Carlo Object Names) as table identifiers. Always use `search` first to resolve a table name to its MCON before calling `getTable`, `getAssetLineage`, or `getAlerts`.

```
search(query="orders_status") → returns mcon, full_table_id, warehouse
```

## Demo scenario

A data engineer opens `models/orders/orders_status.sql` and is adding a new `order_value` column:

1. **Unprompted** (Workflow 1 — table health check):
   - Last updated, row count, existing monitors
   - Active freshness alert firing on `analytics:prod_detectors`
   - Downstream: `order_status_2024` → `order_status_snapshot` (key asset)
   - Lite risk signal: "This table has a key asset downstream and an active alert — want a full change impact assessment?"

2. **Before editing** (Workflow 4 — change impact):
   - Risk tier: 🔴 High — key asset downstream, active alert already firing
   - `order_status_snapshot` has 30+ downstream queries referencing `order_value`
   - Recommendation: notify snapshot owner before deploying, add monitor for new column

3. **After adding the column** (Workflow 2 — add monitor):
   - "Would you like me to add a monitor to ensure `order_value` is never null or negative?"
   - Generate YAML → save to `monitors/orders_status.yml` → dry-run → apply

4. **End result**: Risk surfaced before coding, new logic is live, monitor deployed — all from within Claude Code

## Troubleshooting

**MCP connection fails:**
```bash
# Verify the server is reachable
curl -s -o /dev/null -w "%{http_code}" https://integrations.getmontecarlo.com/mcp/
```
Check that `x-mcd-id` and `x-mcd-token` are set correctly in your MCP config. The key format is `<KEY_ID>:<KEY_SECRET>` — these are split across two separate headers.

**`montecarlo monitors apply` fails with "Unknown field":**
Monitor definition files must have `montecarlo:` as the root key — do not copy the `validation:` or `custom_sql:` output from the MCP tools directly. Reformat using the `montecarlo: > custom_sql:` structure shown in Workflow 2.

**`montecarlo monitors apply` fails with "Not a Monte Carlo project":**
Ensure `montecarlo.yml` (the project config) exists in the working directory. This file must contain only `version`, `namespace`, and `default_resource` — not monitor definitions.

**`createValidationMonitorMac` fails with a Snowflake error:**
This tool validates the condition SQL against the live table. If the column doesn't exist yet (e.g. you're writing the monitor before deploying the model change), fall back to `createCustomSqlMonitorMac` with an explicit SQL query instead.
