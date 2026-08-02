# Tuning Agent Metric Monitors

This reference covers type-specific tuning guidance for agent metric monitors — monitors that
track a metric (row count, latency, error rate, token usage, ...) over an AI agent's trace
table. Read this file after determining the monitor type in Phase 1.5.

## Config fields to extract

Extract these from the `get_monitors` config response for your Phase 2 analysis:

- Agent name and **Agent reference** (from the report's `- Agent:` and `- Agent reference:` lines)
- Trace table (the warehouse table holding the agent's spans)
- Comparisons (metric + operator; `AUTO` means ML thresholds)
- Span filters (`agent_span_filters`: workflow / task / span name narrowing)
- Trace aggregation (`is_agent_trace_aggregation`: metric computed per whole trace vs per span)
- Time axis (`time_axis_field_name` + aggregation bucket)
- Schedule (`FIXED` interval or `MANUAL`)

---

## Threshold adjustment

For explicit-threshold comparisons (`GT`, `LT`, etc.), follow the same rules as metric monitors:
explain what the threshold means for the agent metric ("error rate GT 0.05 means alert when more
than 5% of spans error"), and never recommend a change without citing observed anomaly values
from the report. For `AUTO` (ML) comparisons, use the general sensitivity guidance in the skill.

---

## Span-filter narrowing

If anomalies concentrate in one workflow, task, or span name, narrowing `agent_span_filters`
scopes the metric to just that slice — or excludes a noisy slice by monitoring the rest.

**Write shape rules (strict — the API rejects violations):**

- At most **one** span filter entry.
- Each sub-field is a nested object: `{"workflow": {"value": "TTSA"}}` — never a bare string.
- Field names are camelCase in the wire shape (`spanName`), snake_case in the tool parameter
  (`agent_span_filters`).
- **NEVER include an `agent` entry inside `agent_span_filters`.** The agent is identified by the
  top-level `agent` parameter, not a span filter. An `agent` sub-field is rejected.

**Trade-off:** a narrower filter no longer sees anomalies outside the slice. Always state what
the monitor stops watching.

---

## Aggregation

`is_agent_trace_aggregation=True` computes the metric once per trace (e.g. total tokens per
conversation) instead of per span. Trace aggregation and span-level filters are mutually
exclusive — **do not** combine `is_agent_trace_aggregation=True` with `agent_span_filters`.

Recommend switching to trace aggregation when per-span values are inherently spiky but the
per-trace total is stable (and vice versa). Schedule intervals must be `fixed`/`manual`, at
least 60 minutes, and a multiple of 60.

---

## Applying changes

Use `create_or_update_agent_metric_monitor` to update the monitor in place. The general
preview-then-confirm rules from the metric monitor reference apply (always pass
`monitor_uuid=<uuid>`, always dry-run first, stale-uuid handling).

### Common mistakes

- **CRITICAL: the `agent` parameter takes the Agent reference, verbatim.** Copy the report's
  `- Agent reference:` value exactly (e.g. `analytics:prod_agents.rothbot`) — **never** the bare
  agent name and **never** the trace table's MCON. If the report shows no Agent reference, stop:
  the agent was likely deleted, renamed, or moved, and the monitor can't be updated until that's
  resolved.
- **NEVER** put an `agent` entry inside `agent_span_filters` (see above).
- **`trace_table` is conditional on the store.** For a non-ClickHouse OTel agent (e.g. a
  Snowflake trace table), pass the monitor's trace table (fullTableId form, e.g.
  `ingest:opentelemetry.traces`) as `trace_table` on **every** edit — the API rejects the edit
  without it. For an agent on the Monte Carlo-managed ClickHouse store
  (`...otel_traces:otel_traces.spans_normalized`), **never** pass `trace_table` — the API
  rejects an explicit reference to its own store (it resolves it from the agent automatically).
- **PUT semantics** — same as all monitor types: omitted fields revert to defaults. Re-pass
  everything you want to keep, and note two easy-to-miss fields:
  - `is_draft` — omitting it both un-drafts AND un-pauses a paused monitor.
  - `tags` — omitting them silently drops the monitor's tags (including the agent tags the
    platform uses for routing).
- Sensitivity and `aggregate_by` values are lowercase (`"low"`, `"day"`).
- **Cron-scheduled monitors can't be tuned via these tools** — the tools express only
  `interval_minutes`, so an edit would silently drop a cron expression. Stop and say so.
- **Diff the preview against the original** before `dry_run=False`, exactly as for metric
  monitors.
