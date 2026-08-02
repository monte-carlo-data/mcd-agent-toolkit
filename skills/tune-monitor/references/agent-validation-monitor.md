# Tuning Agent Validation Monitors

This reference covers type-specific tuning guidance for agent validation monitors — monitors
that check every span row (or per-trace aggregate row) in a lookback window against a predicate
rule. **Rows matching the rule are the invalid rows**, and any invalid row is a breach. Like
trajectory monitors there are **no thresholds, no sensitivity, and no time bucketing**. Read this
file after determining the monitor type in Phase 1.5.

## Config fields to extract

Extract these from the monitor report for your Phase 2 analysis:

- Agent name and **Agent reference** (from the report's `- Agent:` and `- Agent reference:` lines)
- **Alert condition** (the report's `Alert condition (definition ...)` block): a predicate tree
  over span fields (status_code, total_tokens, duration_sec, model_name, workflow, span_name, ...)
  — BINARY predicates (equal, in_set, greater_than, contains, matches_regex, ...), UNARY
  predicates (null, empty_string, is_zero, ...), raw-SQL conditions, and AND/OR GROUP nesting.
  Negation is a flag (`negated: true`); literals are always strings, including numbers (`"10000"`)
- **Trace aggregation** (`Trace aggregation: enabled` = one aggregate row per trace with fields
  like span_count, llm_call_count, total_tokens, duration_sec; span filter may pin only `agent`)
- **Span filter** scope (agent / workflow / task / span name — exact values, no exclusions)
- **Time filter** (`lookback_in_hrs`) and schedule interval
- **Noise controls**: `event_rollup_count`, `event_rollup_until_changed`, alert grouping

---

## Predicate edits

**Read the rule's intent before touching it.** The condition tree IS the business rule — restate
it in plain language and check the flagged rows against that intent. Rows that genuinely violate
the intent are signal: reach for rollup/grouping or a scope narrow, never a weaker predicate.

**Polarity discipline:** the condition describes the rows to ALERT ON — loosening means making it
match FEWER rows. Adding a check with OR widens the match (more alerts); with AND it narrows
(fewer). Spell out which direction every edit moves.

- **Step a numeric literal** — raise a token / latency / count ceiling the team keeps dismissing
  (literals stay strings: `"10000"` → `"15000"`). Derive the new value from observed row history
  with headroom and verify known-real violations still match.
- **Add a guard condition** — AND an extra predicate that carves the legitimate case out of the
  match (e.g. only alert on status_code = "2" when is_llm_call is true).
- **Toggle `negated` or swap a predicate** (equal → in_set, contains → matches_regex) when the
  current shape mis-states the rule's intent. There are no `not_*` predicate names, and ordering
  comparators can't be negated — use the inverse comparator.
- **Restructure GROUPs** when a nested AND/OR mixes independent rules — prefer splitting
  genuinely independent rules into separate monitors so each can be tuned alone.

---

## Span filter

Narrow the validated universe when the rule is correct but applies only to one scope (one
workflow's spans, one tool's calls). Exact-match only — narrowing means choosing the scope kept,
and excluded rows are unvalidated: say what monitoring is lost. Under trace aggregation only
trace-level fields exist and only `agent` can be filtered — if the fix needs span fields, the
monitor's grain (not its parameters) is the mismatch, and grain is not a lever.

---

## Lookback vs schedule

- Lookback **longer** than the run interval → re-alerts on the same rows every run; align down to
  the interval.
- Lookback **shorter** than the interval → a coverage bug (e.g. a 1-hour lookback on a daily
  schedule validates 1 of every 24 hours). Recommend closing the gap even though it is not a
  noise fix, and never create this gap while fixing noise.

---

## Notification rollup / grouping

When invalid rows are real but the team is paged per burst of the same failure, consolidate:
`event_rollup_count`, `event_rollup_until_changed`, or alert grouping. Detection and the breach
record stay intact — prefer these over weakening a correct rule.

---

## Applying changes

Use `create_or_update_agent_validation_monitor` to update the monitor in place. The general
preview-then-confirm rules apply (always pass `monitor_uuid=<uuid>`, always dry-run first).
Validation edits never reset anything — there is no learned baseline — but every update is a
**full re-specification**.

### Common mistakes

- **CRITICAL: the `agent` parameter takes the Agent reference, verbatim** (e.g.
  `analytics:prod_agents.rothbot`) — never the bare agent name or the trace-table MCON.
- **The alert condition MUST be re-passed in full** as `alert_condition` — the edit deletes
  anything you omit; re-pass every node verbatim except the one deliberately tuned. The report's
  YAML is MISSING the `type` discriminators the tool requires: add `"type": "GROUP"` on every
  node with `conditions`, `"type": "BINARY"` on predicate nodes with `left`/`right`,
  `"type": "UNARY"` on predicate nodes with `value`, and on every value entry
  `{"type": "FIELD", "field": ...}` / `{"type": "LITERAL", "literal": ...}`. Keep literal values
  exactly as rendered (the string `'2'` stays a string).
- **The time filter MUST be re-passed on every call** — copy the report's
  `Time filter (REQUIRED ...)` JSON verbatim as `time_filter`; omitting it on the
  full-replacement edit drops the window.
- Pass `warehouse` (the report's `Warehouse:` UUID) on every edit.
- When the report shows `Trace aggregation: enabled`, pass `is_agent_trace_aggregation=True` and
  no workflow / task / spanName span filters — the platform rejects span-level filters in that
  mode.
- **PUT semantics** — re-pass `is_draft` (omitting it un-drafts AND un-pauses) and `tags`
  (omitting them drops the platform's agent tags).
- `schedule_type` is `fixed` or `manual` only; `interval_minutes` at least 5 (sub-hourly
  allowed). Pair schedule changes with a matching lookback.
- **Cron-scheduled monitors can't be tuned via these tools** — the tools express only
  `interval_minutes`, so an edit would silently drop a cron expression. Stop and say so.
- **Diff the preview against the original** before `dry_run=False`.
