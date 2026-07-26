# Agent Metric Alert

## How to recognize this alert

| Signal | Value |
|---|---|
| `alert_shape` from `get_alert_agent_classification` | `agent_metric` |
| `incident_type` | `agent_metric_anomalies` — NOT the generic (non-agent) metric anomaly type |
| `event_type` | metric-shaped — NOT the discriminator for this type |
| `get_alerts` category (`alert_types`) | `"Agent metric"` |

`get_alert_agent_classification(alert_id)` is the authoritative check — it returns the
shape and the agent's `backend_class` in one call.

## What the alert means

A built-in quantitative span metric moved outside its expected range — no LLM judging
involved. The metrics: latency (`duration_sec`), token counts (`prompt_tokens`,
`completion_tokens`, `total_tokens`), LLM-call counts, error rate (span status), and
trace volume. A breach signals a **performance or cost regression** — a latency spike,
a token explosion, an elevated error rate, a volume cliff — not a quality degradation.

The alert names the monitor, the breached metric, the anomalous time bucket(s), and any
segment condition (e.g. `task = 'summarize'`). The segment condition is part of the
alert's meaning: the regression was detected *inside that segment*, and the
investigation should start scoped to it.

## Investigation playbook

1. **Classify and route.** `get_alert_agent_classification(alert_id)` → confirm
   `alert_shape` is `agent_metric` and read `agent.backend_class`. Open the matching
   backend reference — it decides which of these signals even exist (see step 6's token
   caveat).
2. **Pin down what breached.** From the alert details (`get_alerts`): which monitor,
   which metric, which direction, which segment, which time bucket(s).
3. **Trend vs baseline.** `get_agent_traces` over the breach window AND over a
   comparable prior window (equal length immediately before; a 7-day lookback works
   well). Establish the metric's day-by-day shape and find the **onset date** — and
   whether it is a *step* (discrete change landed that day) or a *drift* (gradual
   growth).

   > **CRITICAL:** An anomaly is defined by what CHANGED, not by the state of the bad
   > window alone. Never describe only the bad window — always ground it against the
   > baseline.

4. **Segment isolation — find WHERE before asking why.** `get_agent_segments` to
   enumerate the agent's workflows, tasks, and models, then filtered `get_agent_traces`
   per candidate segment. A regression confined to one workflow, one task node, or one
   model is a different root cause than a fleet-wide one. Also check the complement of
   the alert's segment: is the rest of the agent healthy?
5. **Error correlation.** Did error counts move together with the metric? Distinguish
   provider rejections (LLM span fails fast with no output and no tokens), timeouts
   (unusually long failing spans), and code errors (exception text). An error spike that
   coincides with a latency spike usually shares its cause.
6. **Correlate with changes.** The usual suspects, checked against the onset date:
   - a **model swap** (a new model appearing on a node at the onset — different context
     window, throughput, or pricing behavior);
   - **prompt size growth** or per-trace context accumulation (message arrays growing
     turn over turn until token counts blow up);
   - a **configuration or prompt change** landing at the onset;
   - a **code change / deploy** — for code agents only, and only changes that landed
     BEFORE the onset (a change merged after the issue started cannot be its cause;
     allow margin for deploy lag);
   - a **provider-side incident** — a sharply time-bounded spike across many traces
     points at the provider; check its public status history for the onset date.
7. **Drill into exemplar traces.** `get_agent_trace` on two or three of the worst
   traces from the breach window and one or two healthy traces from before the onset.
   Compare span by span: where does the time go, where do the tokens go, which span
   grew or started failing. (`get_agent_trace` reads managed-store (`ao_clickhouse_otel`)
   agents only — on other backends it errors; get span-grain depth from
   `run_troubleshooting_agent`, per the backend guide.)

## Reading the results

- **Step vs drift is the first fork.** A step change points at a discrete change on
  that date (model, prompt, config, deploy). A drift points at accumulation — growing
  inputs, growing context, growing data volume.
- **Segment-confined vs fleet-wide.** Confined to one node/model → look at that
  component's change history. Fleet-wide → look at shared infrastructure, the provider,
  or a global config change.
- **Token blowups:** find the span where accumulation begins — a late-stage overflow is
  often caused by earlier stages growing the context.
- **Slow but healthy is a risk, not an error.** Keep latency outliers separate from
  failures in your evidence.
- **Tokens do not exist on every backend.** Databricks Genie and Knowledge Assistant
  agents record no model and no token counts — token, cost, and model-swap findings are
  invalid there. The backend reference states what exists.

## Common mistakes

| Mistake | Why it fails / what to do instead |
|---|---|
| Describing only the bad window | Always compare against a baseline window; the finding is the *change* |
| Skipping segment isolation | A one-node regression blamed on the whole fleet (or vice versa) misdirects the fix |
| Blaming a change that landed after the onset | Only changes before the onset can be causal; allow deploy-lag margin |
| Token/cost/model findings on Genie or Knowledge Assistant | Those backends have no tokens or model data — the finding is fabricated |
| Counting slow-but-successful traces as errors | Latency risk and failures are different evidence; keep them separate |
| Ignoring the alert's segment condition | The breach was detected inside that segment; investigate there first, then check the complement |

## Related references

- How this monitor type is defined:
  `../../monitoring-advisor/references/agent-metric-monitor.md`
- Backend-specific signal and gotchas: the `agent-backend-*.md` file the router selected.
