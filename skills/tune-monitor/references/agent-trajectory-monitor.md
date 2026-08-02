# Tuning Agent Trajectory Monitors

This reference covers type-specific tuning guidance for agent trajectory monitors — monitors
that flag **traces** whose span pattern matches a rule (a tool called too many times, a step
missing its required predecessor, two spans occurring together or failing to). There are **no
thresholds, no sensitivity, and no time bucketing**: every run scans the lookback window and
every matching trace is a breach. Read this file after determining the monitor type in Phase 1.5.

## Config fields to extract

Extract these from the monitor report for your Phase 2 analysis:

- Agent name and **Agent reference** (from the report's `- Agent:` and `- Agent reference:` lines)
- **Span alert condition** (the report's `Span alert condition (definition ...)` block): one or
  more conditions, **OR-combined** — a trace breaches if ANY condition matches. Two kinds:
  - `SPAN_OCCURRENCE` — how many times a span occurs, compared MORE_THAN / LESS_THAN / EXACTLY
    against a count. Counting is per (trace, parent span, span name) group, **not** per whole
    trace.
  - `SPAN_RELATION` — `occurs_with` / `occurs_before` / `occurs_after` between a primary span and
    related spans, each negatable (`occurs_with` + negated = "occurs without").
- **Time filter** (`lookback_in_hrs` — the window each run scans) and schedule interval
- **Noise controls**: `event_rollup_count`, `event_rollup_until_changed`, alert grouping

---

## Condition edits (per OR branch)

Because conditions are OR-combined, noise usually traces to ONE branch — attribute the alerts to
the branch that matched, tune it, and leave the others untouched. If every branch fires on
distinct legitimate behavior, the rule's premise (not its parameters) is wrong — say so rather
than loosening everything.

- **Occurrence counts**: raise a MORE_THAN count above the observed ceiling — derive from trace
  history (max observed + headroom), never a stock number, and verify known-bad traces stay on
  the firing side. Constraints: EXACTLY needs count ≥ 1, LESS_THAN ≥ 2, MORE_THAN ≥ 0. "Occurs
  zero times" is a negated SPAN_RELATION, not an occurrence.
- **Relation predicate**: switch among occurs_with / occurs_before / occurs_after or toggle
  `negated` when the rule's intent is directional and the current predicate fires on legitimate
  orderings.
- **Remove a branch** the team has repeatedly dismissed — state explicitly what stops being
  monitored.

**Selector retargeting:** span selectors are hierarchical exact-match literals (`workflow`
always; `task` requires `workflow`; `span_name` requires both — no wildcards). A MORE_THAN
condition that seems to miscount is often the per-parent grouping — pinning `task` / `workflow`
to the intended step is frequently the real fix. When alerts fire because the agent's behavior
legitimately changed (a new workflow path, a renamed span), retargeting is tracking reality, not
noise reduction — describe it that way.

---

## Lookback vs schedule

A first-class noise AND coverage axis:

- Lookback **longer** than the run interval → the same breach re-fires every run until it ages
  out. Shrink the lookback to at or just above the interval.
- Lookback **shorter** than the interval → a blind window no run ever scans. Flag the coverage
  gap and recommend closing it even when the user only asked about noise. Never "fix" noise by
  shrinking lookback below the interval.

---

## Notification rollup / grouping

When breaches are real but individually un-actionable (the same failure mode firing in bursts),
consolidate notifications instead of loosening a correct condition: `event_rollup_count` bundles
the next N events, `event_rollup_until_changed` suppresses repeats while the value is unchanged,
alert grouping bundles a time window. Detection and the breach record are unchanged — only
notification cadence changes; say so plainly.

---

## Applying changes

Use `create_or_update_agent_trajectory_monitor` to update the monitor in place. The general
preview-then-confirm rules apply (always pass `monitor_uuid=<uuid>`, always dry-run first).
Trajectory edits never reset anything — there is no learned baseline — but every update is a
**full re-specification**.

### Common mistakes

- **CRITICAL: the `agent` parameter takes the Agent reference, verbatim** (e.g.
  `analytics:prod_agents.rothbot`) — never the bare agent name or the trace-table MCON.
- **The span alert condition MUST be re-passed in full** as `agent_span_alert_condition` — the
  edit deletes anything you omit; re-pass every condition verbatim except the one deliberately
  tuned. The report's YAML is snake_case with NO `type` discriminators; the tool takes camelCase
  (`span_field` → `spanField`, `related_span_fields` → `relatedSpanFields`, `span_name` →
  `spanName`, `comparison_operator` → `comparisonOperator`) and REQUIRES `type` on every
  condition: `"SPAN_RELATION"` for occurs_with/occurs_before/occurs_after, `"SPAN_OCCURRENCE"`
  for occurs. Copy every span-selector level verbatim, including empty literals
  (e.g. `task: {"literal": ""}`).
- **The time filter MUST be re-passed on every call** — copy the report's
  `Time filter (REQUIRED ...)` JSON verbatim as `time_filter`; omitting it on the
  full-replacement edit drops the window.
- Pass `warehouse` (the report's `Warehouse:` UUID) whenever the report shows one.
- Span filters on trajectory monitors may carry ONLY an `agent` dimension
  (`{"agent": {"value": ...}}`) — workflow / task / span-name scoping belongs inside the span
  alert condition's selectors.
- **PUT semantics** — re-pass `is_draft` (omitting it un-drafts AND un-pauses) and `tags`
  (omitting them drops the platform's agent tags).
- `schedule_type` is `fixed` or `manual` only; `interval_minutes` at least 5 (sub-hourly
  allowed). Pair schedule changes with a matching lookback.
- **Cron-scheduled monitors can't be tuned via these tools** — the tools express only
  `interval_minutes`, so an edit would silently drop a cron expression. Stop and say so.
- **Diff the preview against the original** before `dry_run=False`.
