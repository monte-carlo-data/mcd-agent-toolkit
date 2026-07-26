# Agent Trajectory Alert

## How to recognize this alert

| Signal | Value |
|---|---|
| `alert_shape` from `get_alert_agent_classification` | `agent_trajectory` |
| `incident_type` | `custom_rule_anomalies` (shared with plain custom rules — not sufficient alone) |
| `event_type` | `agent_trajectory_anom` — the discriminator |
| `get_alerts` category (`alert_types`) | `"Agent trajectory"` |

Trajectory alerts arrive as **custom-rule alerts**: the payload carries the rule
definition and a hit *count* — there is no monitor aggregation bucket and, importantly,
**no list of offending trace IDs**.

## What the alert means

A rule asserted something about the *execution shape* of each trace, and one or more
traces matched the violating pattern. Rules combine two kinds of assertion (AND/OR):

- **Occurrence:** span X must occur more than / fewer than / exactly N times per trace —
  catches runaway loops, excessive LLM or tool calls, and missing steps.
- **Order/relation:** span A must occur before / after / together with (or never with)
  spans B, C — catches skipped steps, reordered flows, and forbidden combinations.

A trajectory violation is a *pattern*, not an error: the violating traces are often
status-healthy. It usually indicates a **control-flow regression** — the agent's
decision path changed.

> **CRITICAL:** The rule's own selection logic — the query that identifies exactly which
> traces violated — is NOT retrievable through the toolkit tools. You either take the
> exact set from the troubleshooting agent's results, or approximate it from the rule's
> described intent.

## Investigation playbook

1. **Classify and route.** `get_alert_agent_classification(alert_id)` → confirm
   `alert_shape` is `agent_trajectory` and read `agent.backend_class`. Open the matching
   backend reference.
2. **Read the rule's intent** from the alert title and description (via `get_alerts`):
   which span(s), which count or ordering assertion, over which window. Write it down as
   a plain sentence — "traces where `web_search` ran more than 15 times" — before
   querying anything.
3. **Prefer the exactly-resolved violating set.** Call
   `get_troubleshooting_agent_results(incident_id)`: when the troubleshooting agent has run
   on this alert, its findings contain the exactly-resolved violating trace IDs — the
   set the rule actually matched. Merge your investigation with those traces rather than
   re-deriving a cohort. If it has not run, kick it off with
   `run_troubleshooting_agent(incident_id)` and continue manually in parallel.
4. **Otherwise approximate candidates.** `get_agent_traces` over the alert window,
   filtered by whatever proxy signal the rule implies: LLM-call counts (runaway loops),
   trace duration, error counts, workflow/task. For "span X more than N times", find the
   traces with the highest call counts; for a missing-step rule, pull traces of the
   affected workflow and check their span trees.
5. **Anchor the window to the alert's own timestamp.**

   > **CRITICAL:** Trajectory rules typically evaluate "the last N hours *as of when the
   > rule runs*". Replaying the same logic later selects a different set of traces.
   > Search `[alert time − rule window, alert time]` — never "the last N hours from
   > now".

6. **Diff violating vs compliant.** `get_agent_trace` on candidate violating traces AND
   on a compliant trace from the same workflow (managed-store (`ao_clickhouse_otel`)
   agents only — on other backends it errors; get the span-shape view from
   `run_troubleshooting_agent`, per the backend guide). Answer concretely: WHICH
   expected span is missing, out of order, or repeated too many/few times?
7. **Commonality and onset.** What do the violating traces share (workflow, task, input
   kind, user) that compliant traces don't? Since WHEN do violations appear — compare
   against earlier traces of the same workflow to date the onset.
8. **Correlate with a change.** Trajectory violations are usually control-flow
   regressions, so weight code/deploy and prompt/routing changes heavily: a prompt edit
   that reordered or dropped a step, a new branch that skips a tool, a dependency or
   configuration change, or an exception that aborts the expected step (check for errors
   inside or just before the missing span).

## Reading the results

- **Healthy status ≠ compliant trajectory.** Do not filter candidates to errored traces;
  the violation lives in the span tree's shape.
- **Repeated spans often wrap a failure.** A loop violation is frequently a retry loop
  around a silently failing call — check the repeated span (and its children) for
  errors and identical inputs.
- **You see the spans the agent emitted, not the data it processed.** Diagnose the
  missing/reordered/repeated step from the span tree; the *reason* the agent took that
  path usually needs the prompt/routing change correlation from step 8.
- Describe the specific deviation in your finding ("the validation step stopped running
  after the router prompt change on the 14th"), not just "the rule fired".

## Common mistakes

| Mistake | Why it fails / what to do instead |
|---|---|
| Searching "recent" traces | The rule's window is anchored to run time; re-anchor to `[alert time − window, alert time]` |
| Expecting offending trace IDs in the alert | The payload carries only the rule and a hit count; resolve traces via the troubleshooting agent or approximation |
| Re-deriving the cohort when troubleshooting-agent results exist | `get_troubleshooting_agent_results` already has the exactly-resolved set — merge with it |
| Filtering candidates to errored traces | Trajectory violations are patterns; violating traces are often status-healthy |
| Concluding from one violating trace | Always diff against a compliant trace of the same workflow, and check several violators for commonality |
| Ignoring code/prompt/routing changes | Control-flow regressions almost always trace back to one; weight them heavily |

## Related references

- How this monitor type is defined:
  `../../monitoring-advisor/references/agent-trajectory-monitor.md`
- Backend-specific signal and gotchas: the `agent-backend-*.md` file the router selected.
