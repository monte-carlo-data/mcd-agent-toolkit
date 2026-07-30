# Agent Metric Monitor

## When to use

Track quantitative span-level metrics over time. Best for:

- **Latency monitoring** — `duration_sec` trending up
- **Token usage tracking** — `total_tokens`, `prompt_tokens`, `completion_tokens` per call
- **Volume monitoring** — number of spans per time window (`ROW_COUNT_CHANGE`)
- **Boolean rates** — e.g. tool-call rate via `is_tool_call`
- **Anomaly detection** on any of the above with automatic thresholds

Do NOT use this for LLM-evaluated quality (relevance, correctness, tone) — that's
`create_or_update_agent_evaluation_monitor`, which adds sampling + transforms.

## Constraints

> **CRITICAL:** The monitor's source is the `agent` reference. Pass the
> `agentReference` value from `get_agent_metadata` verbatim — a platform
> `{database}:{schema}.{name}` reference or an OTel `service_name`. Never modify,
> truncate, or reconstruct it, and never pass an MCON.

> **CRITICAL:** `warehouse` is REQUIRED. Pass the agent's `warehouse_uuid` from
> `get_agent_metadata`; use `get_warehouses` when it is null or to resolve by name.

> **IMPORTANT:** `schedule_type` is `fixed` (default) or `manual` — never dynamic.
> `interval_minutes` defaults to `60` and must be at least 60 **and** a multiple of 60.

> **IMPORTANT:** Use `duration_sec` (not `duration_ms`) for latency. The field is
> named `duration_sec` in the PARSED_SPANS layer — `duration_ms` does not exist.

> **IMPORTANT:** `ROW_COUNT_CHANGE` is table-level — do NOT include a `fields` array,
> and use only an anomaly operator (`AUTO`/`AUTO_HIGH`/`AUTO_LOW`) or `NOOP`. A manual
> comparison operator has no field to bind to and is rejected.

> **IMPORTANT:** Match the metric to the field type — numeric metrics need numeric
> fields, boolean metrics need boolean fields. A numeric metric on a non-numeric
> field is rejected at dry-run.

## Key characteristics

- Uses `alert_conditions` with metric + operator (no transforms, no sampling)
- Supports anomaly (`AUTO`) and threshold operators
- Optional `is_agent_trace_aggregation=True` aggregates per trace instead of per span
  (OTel agents only — see Trace aggregation)
- Optional `sensitivity` (`low`/`medium`/`high`) tunes AUTO operators

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `description` | string | Yes | Human-readable monitor description (shown as display name) |
| `agent` | string | Yes | Agent reference — `agentReference` from `get_agent_metadata` (`{db}:{schema}.{name}` or OTel `service_name`) |
| `warehouse` | string | Yes | Warehouse name or UUID holding the agent's traces |
| `alert_conditions` | array | Yes | List of alert condition objects (see below) |
| `trace_table` | string | No | Explicit trace table — only for non-ClickHouse OTel agents |
| `agent_span_filters` | array | No | Optional span-scope refinement; at most ONE filter object |
| `is_agent_trace_aggregation` | boolean | No | Aggregate per trace instead of per span (OTel only) |
| `aggregate_by` | string | No | Time-window bucketing (`hour`/`day`/`week`/`month`) |
| `sensitivity` | string | No | Anomaly detection sensitivity for AUTO operators |
| `schedule_type` | string | No | `fixed` (default) or `manual` |
| `interval_minutes` | int | No | Default `60`; at least 60 and a multiple of 60 |
| `tags` | array | No | Key-value tags, e.g. `[{"name": "agent", "value": "<AGENT_NAME>"}]`. Tag every monitor you create for an agent with its name so they're groupable (see Performance pillar) |
| `domain_uuids` | array | No | Domain UUIDs to assign this monitor to — the agent-onboarding playbook passes the footprint's single resolved domain on every create (see agent-monitor-creation.md conventions) |
| `monitor_uuid` | string | No | UUID of an existing monitor to update in place (PUT semantics) |
| `is_draft` | boolean | No | Save as a draft (not active). **On edit, omitting this un-drafts an existing draft** — re-pass `is_draft=True` when updating a draft that should stay a draft |
| `dry_run` | boolean | No | Default `True` — preview YAML; set `False` to deploy |

## Alert conditions

Each condition has:

| Field | Required | Description |
|-------|----------|-------------|
| `metric` | Yes | The metric to compute (see Metrics below). |
| `operator` | Yes | See Operators below. |
| `fields` | Depends | PARSED_SPANS field name(s). Required for every manual operator and range. Omit for `ROW_COUNT_CHANGE`. |
| `thresholdValue` | Depends | Required for single-value operators (`GT`/`GTE`/`LT`/`LTE`/`EQ`/`NEQ`). camelCase — NOT `threshold_value`. |
| `lowerThreshold` / `upperThreshold` | Depends | Both required for `INSIDE_RANGE` / `OUTSIDE_RANGE`; `lowerThreshold` ≤ `upperThreshold`. |
| `type` | No | `threshold` (default) or `noop` (collect without alerting; pair with `operator: "NOOP"`). |

### Operators

- **Anomaly detection:** `AUTO`, `AUTO_HIGH`, `AUTO_LOW` — learn thresholds
  automatically. Do NOT pass any threshold.
- **Single threshold:** `GT`, `GTE`, `LT`, `LTE`, `EQ`, `NEQ` — require
  `thresholdValue` **and** `fields`. (The not-equal operator is `NEQ`, not `NE`.)
- **Range:** `INSIDE_RANGE`, `OUTSIDE_RANGE` — require both `lowerThreshold` and
  `upperThreshold` (and `fields`).
- **Collect-only:** `NOOP` — record the metric without alerting; pair with
  `type: "noop"`.

### Metrics

**Table-level metric (no `fields`; anomaly / NOOP operators only):**

| Metric | Notes |
|--------|-------|
| `ROW_COUNT_CHANGE` | Anomalous span volume. `AUTO` / `AUTO_HIGH` / `AUTO_LOW` (or `NOOP`) only; no `fields`. |

**Field-level metrics (must specify `fields`), by field type:**

| Metric | Field type |
|--------|-----------|
| `NUMERIC_MEAN`, `NUMERIC_MEDIAN`, `NUMERIC_MIN`, `NUMERIC_MAX`, `NUMERIC_STDDEV`, `SUM` | numeric |
| `PERCENTILE_20`, `PERCENTILE_40`, `PERCENTILE_60`, `PERCENTILE_80`, `PERCENTILE_95`, `PERCENTILE_99` | numeric |
| `ZERO_RATE`, `ZERO_COUNT`, `NEGATIVE_RATE`, `NEGATIVE_COUNT` | numeric |
| `TRUE_RATE`, `TRUE_COUNT`, `FALSE_RATE`, `FALSE_COUNT` | boolean |
| `NULL_RATE`, `NULL_COUNT`, `NON_NULL_COUNT` | any |
| `UNIQUE_COUNT` | numeric / text / date |

Numeric metrics apply to `duration_sec` / `*_tokens` / `status_code`; boolean metrics
apply to `is_tool_call` / `is_llm_call` / `has_prompts` / `has_completions` (the last
three are OTel/ClickHouse only — platform/Cortex agents lack them); `NULL_RATE`
applies to any field. Duplicate `(metric, field)` pairs across conditions
are rejected.

Common numeric fields: `duration_sec`, `total_tokens`, `prompt_tokens`,
`completion_tokens`, `status_code` (span grain); `span_count`, `llm_call_count`,
token totals, `duration_sec` (trace grain). Do NOT use `duration_ms` or raw table
column names.

**Databricks Genie agents (`backend_class: databricks_genie`) emit no token or
model data** — token-usage metrics on them are permanently silent. Propose
latency (`duration_sec`), volume, and error/outcome metrics instead.

## Trace aggregation

`is_agent_trace_aggregation=True` rolls spans up per trace. Constraints:

- **OTel agents only.** Platform agent references (`{database}:{schema}.{name}`) are
  rejected — the per-trace query isn't built for them. Target an OTel `service_name`,
  or pass an explicit `trace_table`.
- **No span filters are supported** — remove `agent_span_filters` entirely (including
  `agent`). The monitor's agent is identified by the top-level `agent` parameter, not a
  span filter; the per-trace result has no columns a span filter could match against.
- Use the trace-aggregation field names (`span_count`, `llm_call_count`, trace-summed
  tokens, total `duration_sec`). See `agent-span-fields.md`.

## Performance pillar (baseline monitor set)

When the user asks for performance monitoring on a named agent — latency, token cost,
errors, or a latency SLO ("set up performance monitoring for X", "alert me when X gets
slow or expensive") — propose this exact monitor set rather than inventing one-offs.
Discover the agent first (`get_agent_metadata` → `agentReference`, `backend_class`,
`warehouse_uuid`), apply the backend gating below, then present the whole set with
`dry_run=True` previews.

Shared defaults for every monitor in the set:

- **Daily schedule** — `interval_minutes=1440`.
- **Tag the agent** — `tags=[{"name": "agent", "value": "<AGENT_NAME>"}]` on every
  monitor, so the pillar's monitors are groupable per agent.
- **Draft-first when the user wants review** — pass `is_draft=True` to stage the set
  without activating it (and remember the un-draft-on-edit footgun in Parameters).
- **Grain** — on OTel agents create monitors 1, 2, and 5 with
  `is_agent_trace_aggregation=True` so they track end-to-end interactions; other
  backends use the span-grain default. Monitors 3 and 4 stay span-grain everywhere
  (`SUM` of tokens is the same total either way, and `status_code` is not a
  trace-aggregation field).
- **Cap-constrained surfaces** — if the consuming surface limits how many monitors may be
  proposed, keep priority order 1 → 4 → 3 → 2 → 5 and say which monitors were cut for the cap.

The set:

| # | Monitor | `alert_conditions` | Notes |
|---|---------|--------------------|-------|
| 1 | Latency anomaly | `NUMERIC_MEDIAN` + `PERCENTILE_95` on `duration_sec`, both `AUTO` | ONE monitor, TWO conditions (do not split) — catches drift in the typical and the worst experience. Distinct metrics on the same field are fine; only duplicate metric+field pairs are rejected. p50 = `NUMERIC_MEDIAN`: there is no `PERCENTILE_50` metric — never substitute `PERCENTILE_40`. |
| 2 | Token anomaly | `NUMERIC_MEDIAN` + `PERCENTILE_95` on `total_tokens`, both `AUTO` | Per-interaction cost drift; same one-monitor-two-conditions shape. |
| 3 | Daily token spend | `SUM` on `total_tokens`, `AUTO`, with `aggregate_by="day"` | Aggregate cost creep. `aggregate_by` buckets the datapoints; `interval_minutes` only sets the run cadence — set both. |
| 4 | Error-level anomaly | `NUMERIC_MEAN` on `status_code`, `AUTO_HIGH` | Error-rate proxy — see rationale below. |
| 5 | Latency SLO | `PERCENTILE_95` on `duration_sec`, `GT`, `thresholdValue` = measured p95 × 1.2 | Separate monitor, measure-then-propose — see below. |

**Why monitor 4 is `NUMERIC_MEAN` on `status_code`:** `status_code` is the one error
signal available on every backend (OTel semantics: 0 = unset, 1 = ok, 2 = error).
Healthy spans sit at 0/1 and errored spans at 2, so the mean rises with the
errored-span share — `AUTO_HIGH` on the mean fires when errors spike. Say so in the
proposal: this is a *proxy* for error rate built from built-in metrics, not a true
rate. Do NOT use `TRUE_RATE` (no backend has a boolean error field) or
`exception_type` (not available on all backends). Monte Carlo may already have
auto-created a dedicated error-rate monitor for the agent — check `get_monitors`
first, and if one exists present it as the error coverage instead of duplicating it.

**Monitor 5 is measure-then-propose — never invent an SLO threshold:**

1. Sample recent traces: `get_agent_traces` for the agent (default 14-day lookback),
   `first=50`, paging with `after`/`end_cursor` up to ~3 pages (≤150 traces).
2. Compute the 95th percentile of the sampled `duration_seconds`.
3. Propose `thresholdValue` = p95 × 1.2 (20% headroom), rounded to a clean number.
4. Show the evidence: measured p95, sample size and window, and the proposed
   threshold — stating explicitly that the headroom and threshold are the user's to
   adjust.

Keep the SLO in its own monitor — adding a second `PERCENTILE_95` + `duration_sec`
condition to monitor 1 is rejected as a duplicate metric+field pair. Propose it for
OTel agents only (trace grain, so the trace-level measurement matches the monitored
metric); on other backends skip it — a span-grain p95 tracks individual steps, not
end-to-end latency, so a trace-based threshold would never fire — and note that
monitor 1's anomaly conditions cover latency drift.

**Backend gating** (from `backend_class`; explain each skip in one line in the
proposal):

| `backend_class` | Monitors | Adjustments |
|---|---|---|
| `ao_clickhouse_otel` / `customer_otel_trace_table` | 1–5 | 1, 2, 5 at trace grain |
| `databricks_mlflow_sdk` | 1–4 | span grain; no trace aggregation, so no SLO monitor |
| `platform_agent` (Cortex) | 1–4 | span grain; no trace aggregation, so no SLO monitor |
| `databricks_mlflow_ka` | 1, 4 | token fields are NULL — skip 2–3 |
| `databricks_genie` | 1 (median only), 4 | no token data — skip 2–3; latency percentiles are not meaningful on Genie's fabricated span tree, so drop the `PERCENTILE_95` condition from 1 and skip 5 |

## Examples

The `agent` value below comes from `get_agent_metadata`'s `agentReference` field —
a platform `{database}:{schema}.{name}` reference or an OTel `service_name`.

### Latency anomaly detection (platform agent reference)

```
create_or_update_agent_metric_monitor(
    description="Chat Agent latency monitor",
    agent="analytics:agents.support_bot",
    warehouse="Prod Warehouse",
    alert_conditions=[
        {"metric": "NUMERIC_MEAN", "operator": "AUTO", "fields": ["duration_sec"]}
    ],
    dry_run=True
)
```

### Span volume anomaly detection (OTel service_name, ROW_COUNT_CHANGE — no fields)

```
create_or_update_agent_metric_monitor(
    description="Chat Agent span volume monitor",
    agent="checkout-agent",
    warehouse="Prod Warehouse",
    alert_conditions=[
        {"metric": "ROW_COUNT_CHANGE", "operator": "AUTO"}
    ],
    agent_span_filters=[
        {"workflow": {"value": "Chat Agent"}}
    ],
    dry_run=True
)
```

### Token usage with threshold (span grain)

```
create_or_update_agent_metric_monitor(
    description="Alert when mean token usage exceeds 5000",
    agent="analytics:agents.support_bot",
    warehouse="Prod Warehouse",
    alert_conditions=[
        {"metric": "NUMERIC_MEAN", "operator": "GT", "fields": ["total_tokens"],
         "thresholdValue": 5000}
    ],
    dry_run=True
)
```

### Trace-level token rollup (OTel agent, trace aggregation)

```
create_or_update_agent_metric_monitor(
    description="Alert on anomalous per-trace token totals",
    agent="checkout-agent",
    warehouse="Prod Warehouse",
    alert_conditions=[
        {"metric": "NUMERIC_MEAN", "operator": "AUTO", "fields": ["total_tokens"]}
    ],
    is_agent_trace_aggregation=True,
    dry_run=True
)
```

### Tool-call rate (OTel agent, boolean field)

```
create_or_update_agent_metric_monitor(
    description="Alert when tool-call rate drops",
    agent="checkout-agent",
    warehouse="Prod Warehouse",
    alert_conditions=[
        {"metric": "TRUE_RATE", "operator": "LT", "fields": ["is_tool_call"],
         "thresholdValue": 0.1}
    ],
    dry_run=True
)
```

### Latency SLO threshold (Performance pillar monitor 5 — OTel agent, trace grain, draft)

```
create_or_update_agent_metric_monitor(
    description="checkout-agent latency SLO — trace p95 under 42s (measured p95 35s + 20% headroom)",
    agent="checkout-agent",
    warehouse="Prod Warehouse",
    alert_conditions=[
        {"metric": "PERCENTILE_95", "operator": "GT", "fields": ["duration_sec"],
         "thresholdValue": 42}
    ],
    is_agent_trace_aggregation=True,
    interval_minutes=1440,
    tags=[{"name": "agent", "value": "checkout-agent"}],
    is_draft=True,
    dry_run=True
)
```

## Common errors

| Error message | Cause | Fix |
|--------------|-------|-----|
| Warehouse not found | `warehouse` omitted or wrong | Pass the agent's `warehouse_uuid` from `get_agent_metadata`; if null, list warehouses via `get_warehouses` |
| invalid / unresolvable `agent` reference | The `agent` value wasn't taken from `get_agent_metadata` | Use the exact `agentReference` value — do not construct it by hand, and never pass an MCON |
| "Field X doesn't exist" | Field name not in the PARSED_SPANS schema | Check `agent-span-fields.md`; use `duration_sec` not `duration_ms` |
| metric/field-type mismatch | Numeric metric on a boolean field (or vice versa) | Numeric metrics on numeric fields, boolean metrics on boolean fields, `NULL_RATE` on any |
| `ROW_COUNT_CHANGE` rejected | Included `fields`, or used a manual operator | Drop `fields`; use `AUTO`/`AUTO_HIGH`/`AUTO_LOW` or `NOOP` |
