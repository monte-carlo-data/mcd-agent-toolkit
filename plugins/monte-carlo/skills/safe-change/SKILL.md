---
name: monte-carlo-safe-change
description: |
    Automatically activates when a dbt model, SQL file, or table is referenced.
    Surfaces Monte Carlo context — table health, active alerts, lineage, blast
    radius — before any code is written, and uses those findings to shape code
    recommendations. Generates and optionally deploys monitors for new transformation
    logic. Do not wait to be asked: run the appropriate workflow as soon as a relevant
    file or table is referenced.
version: 1.0.0
---

# Monte Carlo — AI Editor Skill

This skill brings Monte Carlo's data observability context directly into your editor. When you're modifying a dbt model or SQL pipeline, use it to surface table health, lineage, active alerts, and to generate monitors-as-code without leaving Claude Code.

## When to activate this skill

**Do not wait to be asked.** Run the appropriate workflow automatically whenever the user:
- References or opens a `.sql` file or dbt model (files in `models/`) → run Workflow 1
- Mentions a table name, dataset, or dbt model name in passing → run Workflow 1

- Describes a planned change to a model (new column, join update, filter change, refactor) → **STOP — run Workflow 4 before writing any code**
-
- Adds a new column, metric, or output expression to an existing
  model → run Workflow 4 first, then ALWAYS offer Workflow 2
  regardless of risk tier — do not skip the monitor offer
- Asks about data quality, freshness, row counts, or anomalies → run Workflow 1
- Wants to triage or respond to a data quality alert → run Workflow 3

Present the results as context the engineer needs before proceeding — not as a response to a question.

## When NOT to activate this skill

Do not invoke Monte Carlo tools for:
- Seed files (files in seeds/ directory)
- Analysis files (files in analyses/ directory)
- One-off or ad-hoc SQL scripts not part of a dbt project
- Macro files (files in macros/ directory)
- Configuration files (dbt_project.yml, profiles.yml, packages.yml)
- Test files unless the user is specifically asking about data quality

If uncertain whether a file is a dbt model, check for {{ ref() }} or {{ source() }}
Jinja references — if absent, do not activate.

---

## REQUIRED: Change impact assessment before any SQL edit

**Before editing or writing any SQL for a dbt model or pipeline, you MUST run Workflow 4.**

This applies whenever the user expresses intent to modify a model — including phrases like:
- "I want to add a column…"
- "Let me add / I'm adding…"
- "I'd like to change / update / rename…"
- "Can you add / modify / refactor…"
- "Let's add…" / "Add a `<column>` column"
- Any other description of a planned schema or logic change
- "Exclude / filter out / remove [records/customers/rows]…"
- "Adjust / increase / decrease [threshold/parameter/value]…"
- "Fix / bugfix / patch [issue/bug]…"
- "Revert / restore / undo [change/previous behavior]…"
- "Disable / enable [feature/logic/flag]…"
- "Clean up / remove [references/columns/code]…"
- "Implement [backend/feature] for…"
- "Create [models/dbt models] for…" (when modifying existing referenced tables)
- "Increase / decrease / change [max_tokens/threshold/date constant/numeric parameter]…"
- Any change to a hardcoded value, constant, or configuration parameter within SQL
- "Drop / remove / delete [column/field/table]"
- "Rename [column/field] to [new name]"
- "Add [column]" (short imperative form, e.g. "add a created_at column")
- Any single-verb imperative command targeting a column, table, or model
  (e.g. "drop X", "rename Y", "add Z", "remove W")

Parameter changes (threshold values, date constants, numeric limits) appear
safe but silently change model output. Treat them the same as logic changes
for impact assessment purposes.

**Do not write or edit any SQL until the change impact assessment (Workflow 4) has been presented to the user.** The assessment must come first — not after the edit, not in parallel.

---

## Pre-edit gate — check before modifying any file

**Before calling Edit, Write, or MultiEdit on any `.sql` or dbt model
file, you MUST check:**

1. Has the synthesis step been run for THIS SPECIFIC CHANGE in the
   current prompt?
2. **If YES** → proceed with the edit
3. **If NO** → stop immediately, run Workflow 4, present the full
   report with synthesis connected to this specific change, then ask:
   "Workflow 4 complete. Do you want to proceed with the change?"

**Important: "Workflow 4 already ran this session" is NOT sufficient
to proceed.** Each distinct change prompt requires its own synthesis
step connecting the MC findings to that specific change.

The synthesis must reference the specific columns, filters, or logic
being changed in the current prompt — not just general table health.

Example:
- ✅ "Given 34 downstream models depend on is_paying_workspace,
     adding 'MC Internal' to the exclusion list will exclude these
     workspaces from all downstream health scores and exports.
     Confirm?"
- ❌ "Workflow 4 already ran. Making the edit now."

The only exception: if the user explicitly acknowledges the risk
and confirms they want to skip (e.g. "I know the risks, just make
the change") — proceed but note the skipped assessment.

## Available MCP tools

All tools are available via the `monte-carlo` MCP server.

| Tool | Purpose |
|---|---|
| `testConnection` | Verify auth and connectivity |
| `search` | Find tables/assets by name |
| `getTable` | Schema, stats, metadata for a table |
| `getAssetLineage` | Upstream/downstream dependencies (call with mcons array + direction) |
| `getAlerts` | Active incidents and alerts |
| `getMonitors` | Monitor configs — filter by table using mcons array |
| `getQueriesForTable` | Recent query history |
| `getQueryData` | Full SQL for a specific query |
| `createValidationMonitorMac` | Generate validation monitors-as-code YAML |
| `createMetricMonitorMac` | Generate metric monitors-as-code YAML |
| `createComparisonMonitorMac` | Generate comparison monitors-as-code YAML |
| `createCustomSqlMonitorMac` | Generate custom SQL monitors-as-code YAML |
| `getValidationPredicates` | List available validation rule types |
| `updateAlert` | Update alert status/severity |
| `setAlertOwner` | Assign alert ownership |
| `createOrUpdateAlertComment` | Add comments to alerts |
| `getAudiences` | List notification audiences |
| `getDomains` | List MC domains |
| `getUser` | Current user info |
| `getCurrentTime` | ISO timestamp for API calls |

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

**Auto-escalation rule — after completing steps 1–4 above:**

First, check whether the user has expressed intent to modify the model
in this session (e.g. mentioned a change, asked to add/edit/fix something).

IF change intent has been expressed AND any of the following are true:
  - One or more active/unacknowledged alerts exist on the table
  - One or more downstream dependents are key assets
  - The table's importance score is above 0.8
→ Ask the user before running Workflow 4:
  "This is a high-importance table with [N active alerts / key asset
  dependents / importance score 0.989]. Do you want me to run a full
  change impact assessment before proceeding? (yes/no)"
→ Wait for confirmation. If yes → run Workflow 4.
  If no → proceed but note: "Skipping impact assessment at your request."

IF risk signals exist but NO change intent has been expressed:
→ Surface the health summary and note the risk signals only:
  "This is a high-importance table with key asset dependents. When
  you're ready to make changes, say 'run impact assessment' or just
  describe your change and I'll run it automatically."
→ Do NOT run Workflow 4. Do NOT ask about running Workflow 4.

### New model creation variant

When the user is creating a new .sql dbt model file (not editing an existing one):

1. Parse all {{ ref('...') }} and {{ source('...', '...') }} calls from the SQL
2. For each referenced table, run the standard Workflow 1 health check:
   search() → getTable() → getAlerts()
3. Surface a consolidated upstream health summary:
   "Your new model references N upstream tables. Here's their current health:"
   - List each with: last updated, active alerts (if any), key asset flag
4. Flag any upstream table with active alerts as a risk:
   "⚠️ <table_name> has <N> active alerts — your new model will inherit this data quality issue"

Skip getAssetLineage for new models — they have no downstream dependents yet.
Skip Workflow 4 for new models — there is no existing blast radius to assess.

### 2. Add a monitor — when new transformation logic is added

When the user adds a new column, filter, or business rule, suggest adding a monitor. First, choose the monitor type based on what the new logic does:

```
- New column with a row-level condition (null check, range, regex)
  → createValidationMonitorMac

- New aggregate metric (row count, sum, average, percentile over time)
  → createMetricMonitorMac

- Logic that should match another table or a prior time period
  → createComparisonMonitorMac

- Complex business rule that doesn't fit the above
  → createCustomSqlMonitorMac
```

Then run the appropriate sequence:

```
1. Read the SQL file being edited to extract the specific transformation logic:
   - Confirm the file path from conversation context (do not guess or assume)
   - If no file path is clear, ask the engineer: "Which file contains the new logic?"
   - Extract the specific new column definition, filter condition, or business rule
   - Use this logic directly when constructing the monitor condition in step 3

2. For validation monitors: getValidationPredicates() → show what validation types are available
   For all types: determine the right tool from the selection guide above
3. Call the selected create*MonitorMac tool:
   - createValidationMonitorMac(mcon, description, condition_sql) → returns YAML
   - createMetricMonitorMac(mcon, description, metric, operator) → returns YAML
   - createComparisonMonitorMac(source_table, target_table, metric) → returns YAML
   - createCustomSqlMonitorMac(mcon, description, sql) → returns YAML
   ⚠ If createValidationMonitorMac fails (e.g. column doesn't exist yet in the live table),
     fall back to createCustomSqlMonitorMac with an explicit SQL query instead.
3. Save the YAML to <project>/monitors/<table_name>.yml
4. Run: montecarlo monitors apply --dry-run (to preview)
5. Run: montecarlo monitors apply --auto-yes (to apply)
```

**Important — YAML format for `monitors apply`:**
All `create*MonitorMac` tools return YAML that is not directly compatible with `montecarlo monitors apply`. Reformat the output into a standalone monitor file with `montecarlo:` as the root key. The second-level key matches the monitor type: `custom_sql:`, `validation:`, `metric:`, or `comparison:`. The example below shows `custom_sql:` — substitute the appropriate key for other monitor types.

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

### 4. Change impact assessment — REQUIRED before modifying a model

**Trigger:** Any expressed intent to add, rename, drop, or change a column, join, filter, or model logic. Run this immediately — before writing any code — even if the user hasn't asked for it.

### Bugfixes and reverts require impact assessment too

When the user says "fix", "revert", "restore", or "undo", run this workflow
before writing any code — even if the change seems small or safe.

A revert that undoes a column addition or changes join logic has the same
blast radius as the original change. Downstream models may have already
adapted to the "incorrect" behavior, meaning the fix itself could break them.

Pay special attention to:
- Whether the revert removes a column other models now depend on
- Whether downstream models reference the specific logic being reverted
- Whether active alerts may be related to the change being reverted

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

5b. Supplementary local search for downstream dbt refs:
   - Search the local models/ directory for ref('<table_name>') (single-hop only)
   - Compare results against getAssetLineage output from step 2
   - If any local models reference this table but are NOT in MC's lineage results:
     "⚠️ Found N local model(s) referencing this table not yet in MC's lineage: [list]"
   - If no models/ directory exists in the current project, skip silently
   - MC lineage remains the authoritative source — local grep is supplementary only

6. getMonitors(mcon="<mcon>")
   → which monitors are watching columns or metrics affected by the change
```

Assess and report a **risk tier**:

| Tier | Conditions |
|---|---|
| 🔴 High | Key asset downstream, OR active alerts already firing, OR >50 reads/day |
| 🟡 Medium | Non-key assets downstream, OR monitors on affected columns, OR moderate query volume |
| 🟢 Low | No downstream dependents, no active alerts, low query volume |

### Multi-model changes

When the user is changing multiple models in the same session or same domain
(e.g., 3 timeseries models, 4 criticality_score models):

- Run a single consolidated impact assessment across all changed tables
- Deduplicate downstream dependents — if two changed tables share a downstream
  dependent, count it once and note that it's affected by multiple upstream changes
- Present a unified blast radius report rather than N separate reports
- Escalate risk tier if the combined blast radius is larger than any individual table

Example consolidated report header:
"## Change Impact: 3 models in timeseries domain
Combined downstream blast radius: 28 tables (deduplicated)
Highest risk table: timeseries_detector_routing (22 downstream refs)"

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
  - If zero custom monitors exist → append:
    "⚠️ No custom monitors on this table. After making your changes,
    I'll suggest a monitor for the new logic — or say 'add a monitor'
    to do it now."

Recommendation:
  - <specific callout, e.g. "Notify owners of downstream_table before deploying",
     "Coordinate with the freshness alert owner", "Add a monitor for the new column">
```

If risk is 🔴 High:
1. Call `getAudiences()` to retrieve configured notification audiences
2. Include in the recommendation: "Notify: <audience names / channels>"
3. Proactively suggest:
   - Notifying owners of downstream key assets (`setAlertOwner` / `createOrUpdateAlertComment` on active alerts)
   - Adding a monitor for the new logic before deploying (Workflow 2)
   - Running `montecarlo monitors apply --dry-run` after changes to verify nothing breaks

### Synthesis: translate findings into code recommendations

After presenting the impact report, use the findings to shape your code suggestion.
Do not present MC data and then write code as if the data wasn't there.
Explicitly connect each key finding to a specific recommendation:

- Active alerts firing on the table:
  → Recommend deferring or minimally scoping the change until alerts are resolved
  → Explain: "There are N active alerts on this table — making this change now
     risks compounding an existing data quality issue"

- Key assets downstream:
  → Recommend defensive coding patterns: null guards, backward-compatible changes,
     additive-only schema changes where possible
  → Explain: "X downstream key assets depend on this table — I'd recommend
     writing this as [specific pattern] to avoid breaking [specific dependent]"

- Monitors on affected columns:
  → Call out that the change will affect monitor coverage
  → Recommend updating monitors alongside the code change (offer Workflow 2)
  → Explain: "The existing monitor on [column] will need to be updated to
     account for this change"

- New output column or logic being added:
  → Always offer Workflow 2 after the impact assessment, regardless
    of existing monitor coverage
  → Do not skip this step even if risk tier is 🟢 Low
  → Say explicitly: "This adds new output logic — would you like me
    to generate a monitor for it? I can add a null check, range
    validation, or custom SQL rule."
  → Wait for the user's response before proceeding with the edit

- High read volume (>50 reads/day):
  → Recommend extra caution around column renames or removals
  → Suggest backward-compatible transition (add new column, deprecate old one)
  → Explain: "This table has [N] reads/day — a column rename without a
     transition period would break downstream consumers immediately"

- Column renames, even inside CTEs:
  → Never assume a CTE-internal rename is safe. Always check:
    1. Does this column appear in the final SELECT, directly or
       via a CTE that feeds into the final SELECT?
    2. If yes — treat as a breaking change. Recommend a
       backward-compatible transition: add the correctly-named
       column, keep the old one temporarily, remove in a
       follow-up PR.
    3. If truly internal and never surfaces in output — confirm
       this explicitly before proceeding.
  → Explain: "Even though this column is defined in a CTE, if it
    surfaces in the final SELECT it is a public output column —
    renaming it breaks any downstream model selecting it by name."

Always end the synthesis with one clear, specific recommendation in plain English:
"Given the above, I recommend: [specific action]"

Never write code that contradicts the findings without explicitly acknowledging
the risk and getting confirmation from the engineer.

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
