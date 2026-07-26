# Direct Trace Intake: No Alert

Use this when the user brings a `trace_id`, `span_id`, or `conversation_id` — or just a
plain description ("this trace failed", "the bot gave a wrong answer yesterday") —
without a Monte Carlo alert.

## Goal

Resolve **which agent**, **which backend**, and **whether an alert already covers
this** — and only then investigate the specific traces.

> **CRITICAL:** `run_troubleshooting_agent` requires a Monte Carlo alert/incident UUID.
> Without an alert, this path is manual-only — never pass a trace or conversation ID to
> it.

## Steps

### 1. Resolve the agent

Call `get_agent_metadata` and match the user's agent by name or reference. If more than
one agent plausibly matches, **ask the user which one** — do not pick.

> **NEVER** guess the backend from an agent's name. On this path the backend comes from
> the agent's `backend_class` in the `get_agent_metadata` response — the same server-side
> classification the alert path gets from `get_alert_agent_classification` (which is
> alert-scoped and cannot be used here). If `backend_class` is null (an agent the server
> could not classify, or an older Monte Carlo server), ask the user which backend applies
> rather than assuming.

### 2. Search for a matching agent alert

Call `get_alerts` over the relevant window (last 7–14 days, or around the trace's
timestamp), looking at the agent alert categories: `"Agent evaluation"`,
`"Agent metric"`, `"Agent trajectory"`, `"Agent validation"`. Match on the same agent,
timeframe, and symptom (a failing trace often sits inside a metric or validation
breach; a wrong answer often sits inside an evaluation breach).

**If a matching alert exists, treat the user as having provided that alert** and
re-enter the main `SKILL.md` flow at Step 1 — Step 1.5 there kicks off
`run_troubleshooting_agent`, and `get_alert_agent_classification` gives you the shape
and backend. The alert path gets you the resolved breaching set and automated
troubleshooting for free.

### 3. Investigate the supplied items directly

No matching alert — manual investigation, strictly scoped to what the user brought:

- **`trace_id`** → `get_agent_trace`: read the span tree. Failed spans first — in a
  cascade of failures the root cause is usually the earliest or innermost failing span.
  Then timing (where the duration goes), token counts per span, and the model on each
  LLM span. (Managed-store (`ao_clickhouse_otel`) agents only — on other backends
  `get_agent_trace` errors; work from `get_agent_traces` — per-trace status, error
  counts, tokens, duration — and the conversation reads. This path has no automated
  run to lean on.)
- **`conversation_id`** → `get_agent_conversation`: read the thread turn by turn, find
  the turn where things went wrong, then `get_agent_trace` on that turn's trace for the
  span-level view (managed-store agents only — see above).
- **Description only** → `get_agent_traces` filtered by the described symptom (errors,
  latency, the time window the user gives) to find candidate traces first, then drill
  in as above.

Raw content (prompts, completions, transcripts) is gated on the account's data-sampling
consent; without it, reason from structure (span taxonomy, status, tokens, durations)
and say so.

### 4. Widen to the cohort

A single trace is only interpretable against its population. Pull the surrounding
window — roughly 7 days before the trace to 1 day after — with `get_agent_traces` for
the same agent and workflow, and use `get_agent_segments` for workflow/task/model
breakdowns. Answer: is this failure unique, or part of a trend? If a trend, when did it
start, and what changed at the onset (prompt, model, config, deploy)?

### 5. Match depth to the question

- **Lookup questions** ("what model was used?", "list the spans in this trace") →
  answer directly from the trace read; no root-cause pipeline.
- **"Why" questions** ("why did this fail?", "what changed?") → the full treatment:
  cohort comparison, onset dating, change correlation.
- When in doubt, prefer the rigorous path — more rigor is always safe; a raw data dump
  in place of an answer is not.

## Reading the results

- **Stay scoped.** The user asked to troubleshoot *these* items — do not invent an
  incident or a breach framing around them.
- A trace that is anomalous against its cohort (only trace failing, 10× the usual
  tokens) points at something specific to its inputs; a trace that matches a degraded
  cohort points at a population-level change — investigate the onset, not the single
  trace.
- If the widened view reveals a population-level problem with no monitor watching it,
  suggest creating one (the monitoring-advisor skill) — next time there will be an
  alert, and the troubleshooting agent can run automatically.

## Common mistakes

| Mistake | Why it fails / what to do instead |
|---|---|
| Passing a trace/conversation ID to `run_troubleshooting_agent` | It requires an alert/incident UUID; this path is manual-only |
| Guessing the backend from the agent's name | Read `backend_class` from `get_agent_metadata` — never name heuristics |
| Skipping the `get_alerts` check | A matching alert gives you the resolved breaching set, classification, and automated troubleshooting |
| Judging a single trace in isolation | Always compare against its cohort before concluding |
| Running a full root-cause pipeline for a lookup | Match depth to the question |
| Inventing an incident framing | Report on the supplied traces; widen for context, not for drama |

## Related references

- Backend-specific signal and gotchas: the `agent-backend-*.md` file for the backend you
  resolved (the same files the router selects on the alert path).
