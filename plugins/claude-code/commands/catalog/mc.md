---
description: List all Monte Carlo data observability skills and workflows
---

List all available Monte Carlo skills and workflows. Present them grouped by category:

## Workflows

| Command | Description |
|---------|-------------|
| `/monte-carlo-incident-response` | Triage, investigate, fix, and prevent data incidents. Sequences automated-triage, root cause analysis, remediation, and monitor creation. |
| `/monte-carlo-proactive-monitoring` | Assess coverage gaps and create monitors. Sequences asset-health, coverage analysis, and monitor creation. |

## Skills

| Command | Description |
|---------|-------------|
| `/automated-triage` | Triage Monte Carlo alerts — score, classify, and investigate interactively or build an automated workflow |
| `/tune-monitor` | Analyze a Monte Carlo monitor and recommend config changes to reduce alert noise |
| `/monitoring-advisor` | Analyze data coverage, identify gaps, and create monitors for warehouse tables and AI agents |
| `/instrument-agent` | Instrument a new AI agent in a Python codebase for Monte Carlo Agent Observability — detect libraries, install the OpenTelemetry SDK, propose `mc.setup()` and decorator diffs |
| `/monte-carlo-troubleshoot-agent-traces` | Investigate AI agent alerts (evaluation, metric, trajectory, validation) and agent traces — kicks off the trace troubleshooting agent and guides a backend-aware manual investigation |
| `/monte-carlo-reinforce-agent` | Turn an AI agent's Monte Carlo health diagnosis into code fixes — rank the diagnosed issues per workflow, propose what to fix, and open a PR (user-gated at each step) |
| `/mc-validate` | Generate and run validation queries for dbt model changes |
| `/mc-build-*` | Push ingestion commands — build metadata, lineage, and query log collectors |

## Skills Available via Natural Language

These skills don't have dedicated commands but activate automatically when you ask about their topics:

| Skill | Triggers on |
|-------|------------|
| Asset Health | "check health of table X", "how is X doing?", "status of X" |
| Root Cause Analysis | "why is this table stale?", "investigate this alert", "debug this incident" |
| Automated Triage | "triage my alerts", "what alerts are firing?", "score and troubleshoot my open alerts" |
| Remediation | "fix this alert", "remediate this issue", "handle this incident" |
| Storage Cost Analysis | "unused tables", "storage costs", "zombie tables" |
| Performance Diagnosis | "slow pipeline", "expensive queries", "query performance" |
| Prevent | Auto-activates via hooks when you edit dbt models or SQL files |

**User provided input**: $ARGUMENTS
