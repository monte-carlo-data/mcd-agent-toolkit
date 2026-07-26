# Backend: Customer Snowflake OTel Table (`customer_otel_trace_table`)

## What this backend is

A **customer-owned Snowflake table** holding raw OpenTelemetry export from a
code agent the customer instrumented themselves. Monte Carlo normalizes it to the same
standard span vocabulary as the managed OTel store, so the standard list/aggregate reads
(`get_agent_traces`, conversations, segments) all work the same way. The exception is
`get_agent_trace`: the single-trace span-tree read resolves only against the Monte
Carlo–managed OTel store, so it errors on this backend — span-grain depth comes from
`run_troubleshooting_agent` instead. Investigation shape is essentially the managed-OTel
playbook — what differs is where the data lives and who feeds it.

**CRITICAL: the trace table is the customer's — ingestion gaps on their side (a stalled
export job, missing hours, a frozen latest-timestamp) can masquerade as agent
regressions. Rule out a feed gap before calling anything an agent problem.**

## Signal available here

- **Full, real span tree** with parent/child structure, timing, and error detail
  (including exception type/message) — captured in the normalized data. There is no
  direct MCP span-tree read here (`get_agent_trace` is managed-store-only): span-grain
  drill-down goes through `run_troubleshooting_agent`, which queries the trace table
  server-side.
- **Model per span and token counts** — model-swap, cost, and context-overflow questions
  have answers.
- **Workflow / task / model segmentation** — `get_agent_segments`, `get_agent_traces`.
- **Conversations** — `get_agent_conversations` / `get_agent_conversation`; transcript
  content is consent-gated.
- **Change correlation** — this is a code agent: when the customer has GitHub connected,
  correlate the onset with merged PRs and deploys.

## Absent by design — do not chase

- **Nothing structural vs the managed OTel store in the data** — the normalized
  vocabulary is the same; the difference is the store, not the signal. (Tooling does
  differ in one way: `get_agent_trace` reads only the managed store — see above.)
- **Conversation-grain eval breaches and conversation clustering** exist only on the
  Monte Carlo–managed store and the Cortex/Genie platform backends — eval alerts here
  resolve at trace/span grain.
- **No built-in previous-period baseline** — construct your own before/after comparison
  window, exactly as on the managed store.

## Investigation approach

1. **Confirm the backend** — `get_alert_agent_classification` / `get_agent_metadata`.
2. **Check the feed before the agent.** Look at trace volume over time with
   `get_agent_traces`: does the data simply stop, gap, or go stale around the anomaly?
   A completeness/freshness problem in the customer's export pipeline explains a
   "regression" without any agent change — and is itself the finding.
3. **Follow the managed-OTel playbook** (see `agent-backend-clickhouse.md`): establish
   the trend dimensions over ~7 days before the onset to 1 day after, find the onset,
   decide step vs drift.
4. **Classify errors before hypothesizing** — provider rejection, timeout, fast-fail,
   parse failure, code exception, slow-but-healthy.
5. **On a known-bad trace**, get the failed-spans-in-order view from the automated run
   (`run_troubleshooting_agent` — `get_agent_trace` errors on this backend); the root
   cause is usually the earliest or innermost failure. Read the actual error text.
   Manual MCP reads stop at trace grain (`get_agent_traces` — per-trace status and
   error counts).
6. **Compare content across cohorts** when the account's data-sampling settings allow —
   breaching vs pre-onset.
7. **Correlate with changes** — PRs merged before the onset (wide margins for deploy
   lag), provider status pages, model changelogs.
8. For a full automated root-cause run, hand off to `run_troubleshooting_agent` and
   collect results with `get_troubleshooting_agent_results`.

## Gotchas

- **Anchor the window on the alert's own time, not on "now".** The customer table is
  historical data — investigating an older incident with a "recent window" assumption
  finds nothing. Build the window around the incident timestamp.
- **A sudden drop to zero traces is a feed problem until proven otherwise** — treat
  volume cliffs and frozen timestamps as ingestion candidates first.
- **Schema questions are answered from the normalized vocabulary.** The raw table's
  own columns are not the fields you read — never explore the raw table to discover
  fields; use the span-field reference below.
- **Consent gating is a fact to report, not a failure** — if transcript content is
  blocked by the account's data-sampling settings, say so and reason from structure.
- **PR evidence is valid and high-value here** — this is a code agent; do not switch to
  config-surface framing.
- All the managed-OTel gotchas apply: interrupts are not errors, exception text quoted
  in input context is not a real error, generic node names need tree-position
  disambiguation, and a PR merged after onset cannot be the root cause.

## Cross-links

- Span-field vocabulary: `../../monitoring-advisor/references/agent-span-fields.md`
- Managed-store playbook: `agent-backend-clickhouse.md`
- Alert-type playbooks: `agent-alert-*.md`
