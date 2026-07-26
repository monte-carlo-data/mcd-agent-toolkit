# Troubleshoot Agent Traces Skill

Investigate Monte Carlo AI agent alerts and traces — evaluation score drops, latency and token spikes, trajectory violations, and validation breaches. Classifies the alert, routes to the right playbook for the agent's backend, and guides a systematic trace investigation while Monte Carlo's trace troubleshooting agent (TTSA) runs in parallel.

## What it does

- Classifies an alert server-side: is it an agent alert, which shape (evaluation / metric / trajectory / validation), and which backend the agent's traces live in
- Routes the investigation with two files: an alert-shape playbook (WHAT to investigate) plus a backend guide (HOW, and what signal exists there)
- Kicks off the trace troubleshooting agent (TTSA) automatically for agent alerts and merges its findings with the manual investigation
- Investigates traces, conversations, and segments — grounding the alert window against a baseline to find what changed and when
- Handles trace-first intake too: a trace ID, conversation ID, or plain problem description with no alert
- Hands off non-agent alerts to the analyze-root-cause skill
- Presents a findings timeline with per-item confidence levels and a recommended fix in the backend's fix language

## MCP Tools Required

Connect to Monte Carlo's MCP server (`integrations.getmontecarlo.com/mcp`). The skill uses these tools:

| Tool | Purpose |
|------|---------|
| `get_alerts` | Fetch alert details; list recent alerts (agent alert categories in `alert_types`) |
| `get_alert_agent_classification` | Classify one alert: agent or not, alert shape, and the agent's backend class |
| `alert_assessment` | Optional ~2-min triage of an alert (HIGH/MEDIUM/LOW confidence + impact) |
| `get_agent_metadata` | List AI agents — names, trace tables, backend classes, source types, warehouses |
| `get_agent_traces` | List traces with workflows, tasks, models, tokens, duration, error counts |
| `get_agent_trace` | Inspect one execution trace's full span tree (managed OTel store agents only — errors on other backends) |
| `get_agent_conversations` | List recent conversations for an agent (filterable) |
| `get_agent_conversation` | One conversation's full prompt/completion thread |
| `get_agent_segments` | Distinct workflow / task / model values for segment isolation |
| `run_troubleshooting_agent` | Starts the Troubleshooting Agent; for agent alerts it automatically runs the trace troubleshooting agent (TTSA). Auto-invoked when an incident UUID is present |
| `get_troubleshooting_agent_results` | Polls TTSA results for an alert |

> **Credits:** `alert_assessment` and `run_troubleshooting_agent` consume Monte Carlo credits the same way the Troubleshooting Agent does when launched from the Monte Carlo UI. Each fresh `run_troubleshooting_agent` call is a billable run; reuse via the built-in idempotency (don't pass `force_rerun=True` unless the user explicitly asks for a fresh analysis).

**Note:** this skill depends on the `get_alert_agent_classification` tool, which ships with ai-agent PR #1745. On Monte Carlo MCP servers that predate it, the skill says so and falls back to asking the user which alert type fired and which platform hosts the agent.

## Example prompts

- "Investigate this agent alert"
- "Why did my agent's eval score drop yesterday?"
- "Troubleshoot trace 3f2a91c0"
- "My agent is failing — what's going on?"
- "My agent got slow this week, can you look into it?"

## Investigation flow

```
Intake (alert UUID / alert URL, or trace ID / conversation ID / description)
    ↓
Auto-invoke TTSA (if incident UUID + not opt-out)                     ─┐
    ↓                                                                  │
Classify the alert (agent or not / alert shape / backend class)        │ TTSA runs
    ↓                                                                  │ async in
Route: alert-shape playbook + backend guide (ALWAYS both)              │ parallel
    ↓                                                                  │
Investigate: breaching traces → baseline →           ── poll TTSA #1 ──┤
onset → correlated change                                              │
    ↓                                                                  │
Synthesize: findings timeline + fix + verification   ── poll TTSA #2 ──┘
                                                       + merge findings
```

When intake has no incident UUID (a trace ID, conversation ID, or plain description), or the user explicitly opts out ("skip the troubleshooting agent", "manual only"), TTSA is skipped and the manual flow runs alone. Alerts that classify as non-agent hand off to the monte-carlo-analyze-root-cause skill.

## Reference files

| File | Description |
|------|-------------|
| `references/agent-alert-evaluation.md` | Agent evaluation breach playbook (LLM-judged quality scores) |
| `references/agent-alert-metric.md` | Agent metric breach playbook (latency, tokens, error rate) |
| `references/agent-alert-trajectory.md` | Agent trajectory breach playbook (execution-shape assertions) |
| `references/agent-alert-validation.md` | Agent validation breach playbook (span-level assertions) |
| `references/agent-direct-trace.md` | Intake without an alert — trace ID, conversation ID, or description |
| `references/agent-backend-clickhouse.md` | Monte Carlo-managed trace store (`ao_clickhouse_otel`) |
| `references/agent-backend-cortex.md` | Snowflake Cortex agents (`platform_agent`) |
| `references/agent-backend-genie.md` | Databricks Genie spaces (`databricks_genie`) |
| `references/agent-backend-customer-otel.md` | Customer-managed OpenTelemetry trace table (`customer_otel_trace_table`) |
| `references/agent-backend-mlflow-sdk.md` | Databricks MLflow SDK agents (`databricks_mlflow_sdk`) |
| `references/agent-backend-mlflow-ka.md` | Databricks Knowledge Assistants (`databricks_mlflow_ka`) |
