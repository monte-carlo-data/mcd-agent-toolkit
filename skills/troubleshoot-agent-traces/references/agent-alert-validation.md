# Agent Validation Alert

## How to recognize this alert

| Signal | Value |
|---|---|
| `alert_shape` from `get_alert_agent_classification` | `agent_validation` |
| `incident_type` | `custom_rule_anomalies` (shared with plain custom rules — not sufficient alone) |
| `event_type` | `agent_validation_anom` — the discriminator |
| `get_alerts` category (`alert_types`) | `"Agent validation"` |

Same custom-rule wire shape as trajectory alerts: the payload carries the rule
definition — there is no monitor aggregation bucket and **no list of offending trace
IDs**.

## What the alert means

A logical assertion over individual span fields matched one or more spans the monitor
considers INVALID. Typical assertions:

- **Numeric ceilings/floors:** total tokens per span must stay under N; duration under
  a limit.
- **Non-null / presence requirements:** a field the pipeline depends on must be
  populated.
- **Compliance / content conditions:** the output must (or must not) contain something.
- **Hard-failure conditions:** a given tool or LLM span must not error.

The alert fires when at least one span matches the rule in its run window — by default
the rule looks back **about one hour** from each run, not a whole day.

> **CRITICAL:** The rule's own selection logic — the query that identifies exactly which
> spans violated — is NOT retrievable through the toolkit tools. The exact violating
> rows live in the troubleshooting agent's results; otherwise you approximate them from
> the assertion described in the alert.

## Investigation playbook

1. **Classify and route.** `get_alert_agent_classification(alert_id)` → confirm
   `alert_shape` is `agent_validation` and read `agent.backend_class`. Open the matching
   backend reference.
2. **Read the assertion** from the alert title and description (via `get_alerts`): what
   condition marks a span invalid? Then classify it — it decides your drill-in:
   - a **hard failure** (a tool/LLM span erroring) → start from the failed spans;
   - a **content assertion** (output must/must not contain something) → you will need
     to read the breaching spans' content;
   - a **numeric ceiling** (tokens, duration) → treat like a targeted metric check.
3. **Prefer the exactly-resolved rows.** Call
   `get_troubleshooting_agent_results(incident_id)`: when the troubleshooting agent has run,
   its findings contain the exactly-resolved breaching traces/spans — merge with those
   rather than re-deriving. If it has not run, kick it off with
   `run_troubleshooting_agent(incident_id)` and continue manually in parallel.
4. **Otherwise find the offending traces/spans.** `get_agent_traces` filtered by the
   assertion's signal — error status, span name, workflow/task, token or duration
   thresholds — over the window ending at the alert's timestamp (default lookback about
   one hour). Anchor to the alert's own time, not to "now".
5. **Identify the span-level cause.** `get_agent_trace` per offending trace
   (managed-store (`ao_clickhouse_otel`) agents only — on other backends it errors;
   get span-grain detail from `run_troubleshooting_agent`, per the backend guide):
   - Hard failure: locate the failed spans in the tree; in a cascade of failures the
     root cause is usually the **earliest or innermost** failing span.
   - Content assertion: read what the breaching spans' outputs actually contain that
     trips the rule (raw content is gated on the account's data-sampling consent;
     without it, reason from structure and say so).
   - Numeric ceiling: find which span carries the excess and whether it grew over time.
6. **Commonality.** Which spans violated, and what do they share — same workflow, task,
   model, tool, time window, or input shape? A single tool failing everywhere is a
   different story than everything failing in one workflow.
7. **What changed.** Compare the violating spans against comparable spans from before
   the breach began: a code/tool regression, a prompt or configuration change, a model
   swap, or a provider-side failure. The assertion tells you WHAT is invalid; the
   before/after comparison tells you WHY it started.

## Reading the results

- **Failure signatures on LLM spans:** an error with no completion and no token counts
  usually means the provider rejected the call; a very short failing span is a fast
  fail (bad request, auth, config); an unusually long one is a timeout.
- **Error-like text inside a span's inputs is NOT a failure.** Prompts routinely quote
  exception text as context. Trust the span's status, never string-matching inside
  content — healthy spans often *mention* more errors than failing ones.
- **Cascades:** multiple failing spans in one trace generally share one root cause —
  work from the earliest/innermost failure outward.
- A content assertion that newly fails is itself a quality regression; the change that
  introduced it (prompt, config, model, code) is the separate causal finding.

## Common mistakes

| Mistake | Why it fails / what to do instead |
|---|---|
| Investigating whole-day windows | The rule looks back ~1 hour from each run; scope to `[alert time − lookback, alert time]` |
| Treating quoted error text in inputs as failures | Status decides; content routinely quotes exceptions as context |
| Re-deriving rows when troubleshooting-agent results exist | `get_troubleshooting_agent_results` has the exactly-resolved violating rows — merge with them |
| Using the wrong drill-in for the assertion kind | Hard failure → failed spans first; content assertion → span content; don't swap them |
| Expecting offending trace IDs in the alert | The payload carries only the rule; resolve rows via the troubleshooting agent or approximation |
| Stopping at "the assertion failed" | Pair the invalid spans with the before/after change that made them start failing |

## Related references

- How this monitor type is defined:
  `../../monitoring-advisor/references/agent-validation-monitor.md`
- Backend-specific signal and gotchas: the `agent-backend-*.md` file the router selected.
