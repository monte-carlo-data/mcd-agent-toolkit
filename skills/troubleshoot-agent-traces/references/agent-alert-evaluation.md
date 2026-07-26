# Agent Evaluation Alert

## How to recognize this alert

| Signal | Value |
|---|---|
| `alert_shape` from `get_alert_agent_classification` | `agent_evaluation` |
| `incident_type` | `agent_evaluation_anomalies` |
| `event_type` | metric-shaped (e.g. `custom_metric_anom`) — NOT the discriminator for this type |
| `get_alerts` category (`alert_types`) | `"Agent evaluation"` |

`get_alert_agent_classification(alert_id)` is the authoritative check — it returns the
shape and the agent's `backend_class` in one call.

## What the alert means

An LLM judge scores the agent's outputs on a quality dimension, and the score fell below
(or spiked above) expected levels. Common judge fields: `helpfulness_score`,
`relevance_score`, `adherence_score`, `clarity_score`, `completion_score`,
`similarity_score`, `match_score`, `custom_eval_score`, plus boolean checks
(`content_safe`, custom pass/fail prompts) read as true/false rates, and rule-based
fields like `word_count`. Most numeric scores are on a 1–5 (or 0–1) scale.
`mismatch_score` is inverted — higher is worse.

The alert carries the breached metric and the breached field; the field names the judge
dimension you are investigating (e.g. `helpfulness_score`).

### Two grains — trace vs conversation

- **Trace/span grain (default):** each span or trace is judged individually. The
  breaching set is the traces of this agent, inside the alert's anomalous time
  bucket(s), matching the monitor's segment filter (e.g. a specific workflow or task).
- **Conversation grain:** the judge scores a whole multi-turn conversation as one unit.
  The alert payload does not carry conversation IDs — the breaching conversations are
  the evaluation-run samples on the BREACHING side of the score. Which side that is
  depends on the metric and breach direction (step 3) — it is NOT always the lowest
  scores.

> **CRITICAL:** Conversation-grain evaluation exists for agents on Monte Carlo's managed
> trace store (backend class `ao_clickhouse_otel`) and on the Snowflake Cortex /
> Databricks Genie platform backends. On the other backends (MLflow SDK/KA, customer
> OTel tables), evaluation alerts are span/trace grain — do not go looking for breaching
> conversations there.

To tell the grains apart: the monitor definition uses `*_conversation` judge variants
and conversation aggregation at conversation grain, and the monitor description usually
says so. If the backend is MLflow SDK/KA or a customer OTel table, it is span/trace
grain.

## Investigation playbook

1. **Classify and route.** `get_alert_agent_classification(alert_id)` → confirm
   `alert_shape` is `agent_evaluation` and read `agent.backend_class`. Open the matching
   backend reference before touching trace data.
2. **Pull the alert details** via `get_alerts`: the judge dimension, the threshold and
   direction, the anomalous time bucket(s), and any segment condition. The segment
   condition scopes everything that follows.
3. **Identify the breaching set** — the items on the BREACHING side of the score inside
   the breach window. Resolve the side from the metric + breach direction first:
   - Quality scores breaching low (the common case): the lowest-scoring items.
   - Quality scores breaching high (the score spiked above expected levels): the
     highest-scoring items.
   - Boolean/flag evals (`true_*`/`false_*` aggregations): the breaching items carry
     the value whose share ROSE — the metric's tracked value when breaching high, its
     complement when breaching low. `true` items sit at the TOP of the score range
     (score 1.0), `false` items at the BOTTOM (score 0.0). So `escalation_suggested`
     rising on a `true_count`/`true_rate` breaches at the TOP, while `content_safe`
     breaching on a rising `false_rate` breaches at the BOTTOM — "worst-scoring /
     bottom 10" selects exactly the wrong side for the former.
   - Inverted numerics (`mismatch_score`-style, breaching high): the highest scores.

   Then pull the items:

   - Trace grain: `get_agent_traces` filtered to the agent plus the alert's segment,
     within each anomalous bucket window.
   - Conversation grain: `get_agent_conversations` for the agent over the breach
     window; work from the ~10 most extreme conversations on the breaching side.
4. **Verify the items actually breach.**

   > **CRITICAL:** Sampling seams can hand you non-breaching items. Check every item's
   > score against the alert's threshold before treating it as evidence. A known failure
   > mode: a flag eval breaching HIGH on a true-count, sampled score-ascending
   > "worst-first" — its flagged rows sat at the TOP scores, so the page's limit cut
   > them off and seeded the investigation with perfectly-scoring conversations; the
   > investigator then "confirmed normal behavior" while reading the wrong conversations
   > entirely. Any sample sorted toward the non-breaching side (step 3) fails the same
   > way.

5. **Read the judge's scores and stored reasoning first.** The persisted judgment is the
   truth for this alert. The stored reasoning (often a paragraph per item) frequently
   names the failure mode outright — when it already explains the regression, capture it
   and stop drilling.
6. **Read the actual items.** `get_agent_conversation` per conversation (conversation
   grain) or `get_agent_trace` per trace (trace grain; managed-store (`ao_clickhouse_otel`)
   agents only — on other backends it errors, see the backend guide). Read the breaching items AND a
   few healthy items from before the breach began — the comparison is what isolates what
   changed. Note: raw content (prompts, completions, transcripts) is gated on the
   account's data-sampling consent; without it, reason from structure (span taxonomy,
   status, tokens, durations) and say so.
7. **Cluster the failure modes before concluding.** Group the breaching items by shared
   pattern — same workflow/task, same model, same kind of question, same failure shape
   (empty outputs, off-topic answers, refusals). One cluster with one cause is a
   different finding than three unrelated failures.

   > **NEVER** generalize from a single conversation or trace. A conclusion needs
   > multiple breaching items showing the same failure mode.

8. **Correlate with a change.** Evaluation breaches track the agent's *responses* — you
   do not see the data the agent ran on. Focus on prompt changes, model swaps,
   input-distribution shifts (a new kind of ask), and workflow adherence, comparing
   breaching items against pre-onset items. Record negative findings explicitly ("no
   prompt change detected").

The troubleshooting agent can run this alert end-to-end in parallel:
`run_troubleshooting_agent(incident_id)`, then `get_troubleshooting_agent_results` for its
evidence timeline. Merge rather than duplicate.

## Reading the results

- **Score direction matters.** Most judges: lower = worse. `mismatch_score`: higher =
  worse. Boolean checks read as rates (e.g. a rising false rate on `content_safe`).
- **Platform backends (Databricks Genie, MLflow-based agents):** the evaluation score is
  computed by Monte Carlo and lives on the alert/monitor — it is NOT a column in the
  trace data. The traces tell you what the agent *did*; the monitor tells you what
  *scored* low. Do not hunt for a score field in span data.
- **Snowflake Cortex:** evaluations run inside the customer's warehouse, so a quality
  movement correlates with an agent-configuration change or a source-data shift — not
  with a Monte Carlo scoring change.
- A quality drop is the symptom (`quality regression`); the finding is complete only
  when paired with the causal change (prompt edit, model swap, config change, new input
  mix) or an explicit "no correlated change found".

## Common mistakes

| Mistake | Why it fails / what to do instead |
|---|---|
| Assuming breaching = lowest scores | The breaching side follows metric + direction (step 3): a flag eval breaching high on a true-count breaches at the TOP scores; a rising `false_rate` (e.g. `content_safe`) breaches at the BOTTOM — resolve the side before sampling |
| Concluding from one conversation | Cluster several breaching items; one item proves nothing about the population |
| Treating sampled items as breaching without checking scores | Sampling seams return non-breaching items; verify each score against the threshold |
| Expecting conversation grain on MLflow or customer-OTel backends | Conversation-grain evaluation runs on the managed store and Cortex/Genie only — elsewhere alerts are span/trace grain |
| Selecting an eval score from trace data on Genie/MLflow | The score lives on the alert/monitor, not in the spans |
| Misreading `mismatch_score` | It is inverted — higher is worse |
| Only reading breaching items | Always compare against pre-onset healthy items to isolate what changed |
| Silent dead ends | Record negative findings ("no model change in window") — they narrow the cause |

## Related references

- How this monitor type is defined:
  `../../monitoring-advisor/references/agent-evaluation-monitor.md`
- Backend-specific signal and gotchas: the `agent-backend-*.md` file the router selected.
