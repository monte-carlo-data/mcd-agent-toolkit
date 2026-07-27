# MC Agent Toolkit

Monte Carlo's official toolkit for AI coding agents. Brings data observability — lineage, monitoring, validation, alerting, and metadata ingestion — directly into your development workflow. The toolkit bundles multiple skills into a single plugin that works across supported editors.

> Using Claude.ai (web or desktop) instead of a coding agent? Monte Carlo is a [verified connector](https://claude.com/connectors/monte-carlo) in the Claude directory — [install it directly](https://claude.ai/directory/connectors/monte-carlo).

## Features

The toolkit bundles the following capabilities as a single **mc-agent-toolkit** plugin. Each feature is a [skill](skills/) that can also be used standalone.

Skills are grouped by the job they help you do. Orchestrated workflows sequence individual skills into guided multi-step flows; atomic skills can be invoked directly by name. Both are loaded the same way.

### Trust — pre-query and pre-build checks

| Skill | Description | Details |
|---|---|---|
| **Asset Health** | Single-table health report: freshness, active alerts, monitor coverage, importance, and upstream issues. Run before building on a table. | [README](skills/asset-health/README.md) |

### Incident Response — triage, investigate, fix

| Skill | Description | Details |
|---|---|---|
| **Incident Response** _(workflow)_ | Orchestrates full incident lifecycle — triage → root cause → remediation → prevent recurrence. | [SKILL](skills/incident-response/SKILL.md) |
| **Automated Triage** | Scores and prioritizes active alerts; runs deep troubleshooting on high-signal ones. | [SKILL](skills/automated-triage/SKILL.md) |
| **Analyze Root Cause** | Investigates incidents via lineage tracing, ETL checks, query analysis, and data profiling. | [README](skills/analyze-root-cause/README.md) |
| **Remediation** | Proposes and executes fixes for data-quality alerts; assesses blast radius before acting, or escalates with full context. | [README](skills/remediation/README.md) |
| **Troubleshoot Agent Traces** | Investigates AI-agent alerts (evaluation, metric, trajectory, validation) and agent traces — kicks off the trace troubleshooting agent and guides a backend-aware manual investigation. | [README](skills/troubleshoot-agent-traces/README.md) |

### Monitoring — coverage gaps, monitor creation, noise reduction

| Skill | Description | Details |
|---|---|---|
| **Proactive Monitoring** _(workflow)_ | Sequences coverage analysis → gap identification → monitor creation into a guided flow. | [SKILL](skills/proactive-monitoring/SKILL.md) |
| **Monitoring Advisor** | Identifies coverage gaps and creates monitors for warehouse tables or AI agents — validates tables and fields against your live workspace, emits monitors-as-code YAML. | [README](skills/monitoring-advisor/README.md) |
| **Manage MaC** | Create, edit, validate, and import Monitors-as-Code YAML files — authors new monitors from scratch, modifies existing files, validates against the published JSON Schema, and exports live monitors to YAML. | [SKILL](skills/manage-mac/SKILL.md) |
| **Tune Monitor** | Recommends sensitivity, segment, and schedule changes to reduce alert noise on an existing metric monitor. | [SKILL](skills/tune-monitor/SKILL.md) |

### Prevent — catch issues before they ship

| Skill | Description | Details |
|---|---|---|
| **Prevent** | Edit-lifecycle safety net for dbt/SQL: surfaces blast radius and monitor gaps before edits, generates monitors-as-code for new logic. Auto-activates via hooks. | [README](skills/prevent/README.md) |
| **Generate Validation Notebook** | Generates targeted SQL validation queries for a dbt PR or local repo change. | [README](skills/generate-validation-notebook/README.md) |

### Optimize — cost and performance

| Skill | Description | Details |
|---|---|---|
| **Storage Cost Analysis** | Identifies storage waste (unread, zombie, dead-end tables); uses lineage to verify cleanup is safe and estimates savings. | [README](skills/storage-cost-analysis/README.md) |
| **Performance Diagnosis** | Diagnoses slow pipelines and expensive queries across Airflow, dbt, Databricks, and other platforms. | [README](skills/performance-diagnosis/README.md) |

### Evaluate — compare agent runs

| Skill | Description | Details |
|---|---|---|
| **Compare Trace** | A/B compares two existing agent traces (by ID) — graph path, latency/tokens, tool-call sequence, plus LLM-based semantic and entity-overlap diffs over the final answers. Emits an HTML report. | [README](skills/compare-trace/README.md) |

### Setup — ingestion and connections

| Skill | Description | Details |
|---|---|---|
| **Push Ingestion** | Generates collection scripts to push metadata, lineage, or query logs to Monte Carlo from any data source. | [README](skills/push-ingestion/README.md) |
| **Connection Auth Rules** | Builds Connection Auth Rules JSON for a Monte Carlo connection type using live connector schemas. | [SKILL](skills/connection-auth-rules/SKILL.md) |
| **Instrument Agent** | Instruments a Python AI agent for Monte Carlo Agent Observability — detects AI libraries, installs the Monte Carlo OpenTelemetry SDK, sets up tracing, and verifies traces in Monte Carlo. Asks before editing. | [SKILL](skills/instrument-agent/SKILL.md) |

## Installing the plugin (recommended)

**Monte Carlo recommends installing the mc-agent-toolkit plugin.** The plugin bundles all skills together with hooks, the Monte Carlo MCP server, and agent-specific capabilities — no separate MCP configuration or authentication setup needed. See the [plugins page](plugins/) for the full list of supported coding agents.

### Claude Code

1. Add the marketplace:
   ```
   /plugin marketplace add monte-carlo-data/mc-agent-toolkit
   ```
2. Install the plugin:
   ```
   /plugin install mc-agent-toolkit@mc-marketplace
   ```
3. Updates — `claude plugin update` pulls in the latest skill and hook changes.

See the [Claude Code plugin README](plugins/claude-code/README.md) for detailed setup and usage.

For other coding agents (Cursor, Copilot CLI, OpenCode, Codex, Cortex Code), see the [plugins page](plugins/) for installation guides.

## Using skills directly (advanced)

Skills can also be used standalone without the plugin. This is for users who want to install individual skills via registries or use them with agents not listed above.

### Prerequisites

- A [Monte Carlo](https://www.montecarlodata.com) account with Editor role or above
- Monte Carlo MCP server — configure with:
  ```
  claude mcp add --transport http monte-carlo-mcp https://mcp.getmontecarlo.com/mcp
  ```
  Then authenticate: run `/mcp` in your editor, select `monte-carlo-mcp`, and complete the OAuth flow.

  See [official docs](https://docs.getmontecarlo.com/docs/mcp-server#option-1-oauth-21-recommended-for-mcp-clients-that-support-http-transport) for other MCP clients and advanced options.

  <details>
  <summary>Legacy: header-based auth (for MCP clients without HTTP transport)</summary>

  If your MCP client doesn't support HTTP transport, use `.mcp.json.example` with `npx mcp-remote` and header-based authentication. See the [MCP server docs](https://docs.getmontecarlo.com/docs/mcp-server) for details.

  </details>

### Installation

```bash
npx skills add monte-carlo-data/mc-agent-toolkit --skill prevent
```

Or copy directly:

```bash
cp -r skills/prevent ~/.claude/skills/prevent
```

See the [skills directory](skills/) for the full list and individual READMEs.

## Telemetry

All six editor plugins send an anonymous **install beacon** — a `Toolkit Installed` event carrying an opaque per-install UUID, a per-session UUID, the toolkit version, and the editor name — once per machine per toolkit version (first install and after each version change), so we can count installations and version adoption. The Claude Code and Cortex Code plugins additionally send anonymous **skill-usage** telemetry (which skills are invoked, how often). As of v1.13.3, the same `install_id` and toolkit version also ride as HTTP headers on **authenticated** MCP requests to the Monte Carlo MCP server, so the otherwise-anonymous install can be correlated with the account's MCP tool usage server-side. No prompts, skill arguments, or code are ever sent, and telemetry is fail-open and non-blocking. To disable all of it, set `MC_AGENT_TOOLKIT_TELEMETRY_DISABLED=1`. See each plugin's README (e.g. [Claude Code](plugins/claude-code/README.md#telemetry), [Cortex Code](plugins/cortex-code/README.md#telemetry)) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding skills, creating plugins, and submitting pull requests. It also covers [plugin architecture](docs/plugin-architecture-guide.md) and [releasing new versions](CONTRIBUTING.md#releasing).

## License

This project is licensed under the Apache-2.0 license — see [LICENSE](LICENSE) for details.

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
