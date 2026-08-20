# Analyze Root Cause Skill

Investigate data incidents and find root causes using Monte Carlo's observability data. Guides the agent through systematic investigation: alert lookup, lineage tracing, ETL checks, query analysis, and data profiling.

## What it does

- Investigates freshness delays, volume anomalies, schema changes, ETL failures (including Azure Data Factory), query regressions, and field metric drift
- Fetches alert-scoped normalized runtime logs before narrowing noisy results, then uses them as RCA evidence
- Maps blast radius using table and field-level lineage
- Traces bad data upstream to find the source
- Correlates changes (query modifications, volume shifts, ETL failures) with incident timeline
- Profiles actual data when a database MCP connector is available
- Matches findings against a catalog of known root cause patterns

## MCP Tools Required

Connect to Monte Carlo's MCP server (`integrations.getmontecarlo.com/mcp`). The skill uses these tools:

| Tool | Purpose |
|------|---------|
| `get_alerts` | Fetch incident/alert details |
| `fetch_logs` | Fetch normalized runtime logs for the alert resource and exact incident window |
| `search` | Find tables by name |
| `get_table` | Table metadata and fields |
| `get_asset_lineage` | Table-level lineage |
| `get_field_lineage` | Field-level lineage (trace to source column) |
| `get_table_freshness` | Update/freshness history |
| `get_table_size_history` | Row count and size history |
| `get_queries_for_table` | Read/write query history |
| `get_query_changes` | Detect SQL text modifications |
| `get_query_rca` | Failed/futile/missed query analysis |
| `get_change_timeline` | Unified change timeline |
| `get_etl_issues` | ETL pipeline issues (Airflow, dbt, Databricks) — pass `platform` param |
| `get_etl_jobs` | Find ETL jobs writing to tables (Airflow, dbt, Databricks) — pass `platform` param |
| `get_github_prs` | Recent GitHub PRs (via MC's GitHub integration) |
| `get_jobs_performance` | Job runtime stats, failure rates, trends |
| `alert_assessment` | Optional incident context/triage call; fallback source for exact missing log-window bounds |
| `run_troubleshooting_agent` | Starts the Troubleshooting Agent (TSA) on an incident; auto-invoked when an incident UUID is present |
| `get_troubleshooting_agent_results` | Polls TSA results for an incident |

> **Credits:** `alert_assessment` and `run_troubleshooting_agent` consume Monte Carlo credits the same way the Troubleshooting Agent does when launched from the Monte Carlo UI.

**Optional:** A database MCP server (Snowflake, BigQuery, Redshift) for direct SQL queries.

## Example prompts

- "Investigate alert 12345"
- "Why is the orders table stale?"
- "Row count dropped 50% on analytics.prod.revenue — what happened?"
- "Debug this freshness issue on our daily pipeline"
- "The dashboard shows yesterday's data — can you find out why?"

## Investigation flow

```
Intake (alert ID or user description)
    ↓
Auto-invoke TSA (if incident UUID + not opt-out + not narrow check)  ─┐
    ↓                                                                  │
Fetch runtime logs (alert-scoped ETL failures)                         │
    ↓                                                                  │
Map blast radius (upstream + downstream lineage)                       │ TSA runs
    ↓                                                                  │ async in
Investigate by issue type (freshness / volume / schema / ETL / query)  │ parallel
    ↓                                                                  │
Check upstream causes (walk lineage chain)  ── poll TSA #1 ────────────┤
    ↓                                                                  │
Profile data (if DB connector available)                               │
    ↓                                                                  │
Check code changes (GitHub MCP or MC query changes)                    │
    ↓                                                                  │
Synthesize: root cause + evidence + impact + fix  ── poll TSA #2 ─────┘
                                                    + merge findings
```

When intake has no incident UUID, when the user explicitly opts out, or when the request is a narrow scoped check (e.g. "is X stale right now?"), TSA is skipped and the manual flow runs alone.

## Reference files

| File | Description |
|------|-------------|
| `references/freshness-investigation.md` | Freshness delay playbook |
| `references/volume-investigation.md` | Volume anomaly playbook |
| `references/schema-investigation.md` | Schema change playbook |
| `references/etl-failure-investigation.md` | ETL failure playbook |
| `references/query-change-investigation.md` | Query modification playbook |
| `references/field-anomaly-investigation.md` | Field metric drift playbook |
| `references/data-exploration.md` | SQL patterns for data profiling |
| `references/intake-no-incident.md` | Intake flow when no incident ID |
| `references/common-root-causes.md` | Catalog of known root cause patterns |
