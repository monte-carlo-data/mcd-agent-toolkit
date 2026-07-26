# Backend: Databricks MLflow SDK / Agent Bricks (`databricks_mlflow_sdk`)

## What this backend is

A **customer-coded** Databricks agent built with the Mosaic AI Agent Framework (Agent
Bricks SDK). MLflow autologging captures a real OTel-shaped span tree — with model and
token data — into Unity Catalog tables that Monte Carlo reads through a normalized view.
Of all the Databricks-family backends this is the closest to the managed OTel store in
investigation shape: it is a code agent, and model/token/PR findings are all valid.

**CRITICAL: this agent is identified by its Databricks coordinates
(database/schema/agent name), not by a resolvable trace-table name. Take the agent
reference from `get_agent_metadata` verbatim — do not try to locate or name a trace
table yourself.**

## Signal available here

- **Real multi-span trace tree** with parent/child structure, per-span timing, and
  status — captured in the normalized data. There is no direct MCP span-tree read here
  (`get_agent_trace` is managed-store-only and errors on this backend): span-grain
  drill-down goes through `run_troubleshooting_agent`; manual reads work at trace
  grain via `get_agent_traces`.
- **Model and token counts per span** — model-swap, cost, and context-growth questions
  have answers here (unlike Genie and the Knowledge Assistant).
- **Workflow / task segmentation** — customer-set attributes broadcast trace-wide;
  enumerate values with `get_agent_segments`, aggregate with `get_agent_traces`.
- **Error status and error detail** per span.
- **Change correlation** — a code agent: when the customer has GitHub connected,
  correlate the onset with merged PRs and deploys.

## Absent by design — do not chase

- **No free-form attribute exploration** — attributes were flattened into the standard
  fields at normalization; the standard vocabulary is everything there is. Don't dig
  for extra attribute keys.
- **Eval scores are not in the spans** — quality scores are Monte Carlo–computed and
  live on the monitor/alert, not in trace data.
- **Conversation clustering and conversation-grain eval breaches** exist only on the
  Monte Carlo–managed OTel store and the Cortex/Genie platform backends.
- **Raw content is consent-gated** — without the account's data-sampling consent,
  reason from span taxonomy, status, token distribution, and per-node latency.

## Investigation approach

1. **Confirm the backend** — `get_alert_agent_classification` / `get_agent_metadata`
   (note the coordinate-style agent reference).
2. **Follow the managed-OTel playbook** (see `agent-backend-clickhouse.md`): establish
   latency / error-rate / throughput / token trends over ~7 days before the onset to
   1 day after via `get_agent_traces` aggregation; find the onset; decide step vs drift.
   There is no built-in previous-period baseline — build your own comparison window.
3. **Segment the regression** — break the moved metric down by workflow / task / model
   (`get_agent_segments`); a regression confined to one node or one model is a
   different root cause than a fleet-wide one.
4. **Classify errors before hypothesizing** — provider rejection, timeout, fast-fail,
   parse failure, code exception, slow-but-healthy — and get a known-bad trace's
   failed-spans-in-order view from the automated run (`run_troubleshooting_agent`;
   earliest/innermost failure first). `get_agent_trace` errors on this backend —
   manual MCP reads stop at trace grain.
5. **Compare content across cohorts** when consent allows — breaching vs pre-onset
   prompts and completions.
6. **Correlate with changes** — PRs merged before the onset, provider status pages,
   model changelogs. Model-switch and context-overflow plays from the managed-OTel
   playbook apply in full.
7. For a full automated root-cause run, hand off to `run_troubleshooting_agent` and
   collect results with `get_troubleshooting_agent_results`.

## Gotchas

- **LLM spans are marked by request type, not by span-name conventions.** On this
  backend an LLM call is identified as a "chat"-type span — do not pattern-match span
  names (the `.chat` suffix taxonomy belongs to the managed OTel store).
- **Schema questions are answered from the normalized vocabulary** — see the span-field
  reference below; never run exploratory queries against the underlying tables to
  discover fields.
- **Consent gating is a fact to report, not a failure** — if content reads are blocked
  by the account's data-sampling settings, say so and continue from structure and
  tokens.
- **PR, token, and model evidence are all valid here** — this is the Databricks backend
  where those questions DO have answers; don't import Genie/Knowledge-Assistant
  restrictions.
- Managed-OTel gotchas carry over: interrupt-style control-flow messages are not
  errors, exception text quoted in input context is not a real error, and a PR merged
  after onset cannot be the root cause.

## Cross-links

- Span-field vocabulary: `../../monitoring-advisor/references/agent-span-fields.md`
- Managed-store playbook: `agent-backend-clickhouse.md`
- Alert-type playbooks: `agent-alert-*.md`
