# Monte Carlo AI Editor Plugin — Hackathon Project

## Project Overview

This is a hackathon project to build a Claude Code plugin for Monte Carlo Data (MC), inspired by the Braintrust Claude Code integration. The goal is to bring MC's data observability context directly into AI code editors, so data engineers can get lineage, alerts, and monitor suggestions without leaving their editor.

This is **Idea 2, Direction 2**: MC context → AI code editor (read direction). Direction 1 (session tracing back into MC) is explicitly out of scope for this hackathon.

## The Demo Story

A data engineer is modifying a dbt model in Claude Code. Without leaving their editor, they:
1. Get immediate awareness of the table's health, active alerts, and downstream dependencies
2. Receive a suggestion to add a validation monitor for new logic they're adding
3. See the generated monitor YAML applied to MC via the CLI — all in one flow

## What We're Building

### Core Deliverable: `SKILL.md`
A markdown skill file (`~/.claude/skills/monte-carlo/SKILL.md`) that teaches Claude Code when and how to use Monte Carlo's existing MCP tools. This is the heart of the project. The format follows the open Agent Skills spec, making it compatible with Claude Code, Cursor, and other AI editors.

### Supporting Deliverables
- MCP server configuration snippet (for Claude Code, Cursor, VS Code)
- `README.md` with setup instructions
- Demo scenario: a scripted dbt model change against the dev environment

## Monte Carlo MCP Server

Already built and publicly available. No need to build MCP infrastructure.

**Endpoint:** `https://integrations.getmontecarlo.com/mcp/`

**Auth:** MCP-specific API key (not standard API key). Created via MC UI → Settings → API Keys → MCP Server type. Key format: `<KEY_ID>:<KEY_SECRET>`

**MCP config for Claude Code** (`~/.claude/claude.json` or `.mcp.json`):
```json
{
  "mcpServers": {
    "monte-carlo": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://integrations.getmontecarlo.com/mcp/",
        "--header",
        "x-mcd-id: <KEY_ID>",
        "--header",
        "x-mcd-token: <KEY_SECRET>"
      ]
    }
  }
}
```

**Available MCP Tools:**

| Tool | Purpose |
|---|---|
| `testConnection` | Verify auth and connectivity |
| `search` | Find tables/assets by name |
| `getTable` | Schema, stats, metadata for a table |
| `getTableLineage` | Upstream/downstream dependencies |
| `getAlerts` | Active incidents and alerts |
| `getQueriesForTable` | Recent query history |
| `getQueryData` | Full SQL for a specific query |
| `createValidationMonitorMac` | Generate monitors-as-code YAML |
| `getValidationPredicates` | List available validation rule types |
| `updateAlert` | Update alert status/severity |
| `setAlertOwner` | Assign alert ownership |
| `createOrUpdateAlertComment` | Add comments to alerts |
| `getDomains` | List MC domains |
| `getUser` | Current user info |
| `getCurrentTime` | ISO timestamp for API calls |

**Applying generated monitor YAML:**
```bash
montecarlo monitors apply --file <generated-yaml-file>
```

## Dev Environment

- **Stack:** dbt + Snowflake + Airflow
- **MC environment:** dev (not production)
- Data may be less rich than production but sufficient for demo

## Reference: Braintrust Claude Code Plugin
- Repo: https://github.com/braintrustdata/braintrust-claude-plugin
- Blog: https://www.braintrust.dev/blog/claude-code-braintrust-integration
- Their approach: two plugins — `trace-claude-code` (session tracing) + `braintrust` (SKILL.md bringing data into editor)
- We are building the equivalent of their `braintrust` skill (Direction 2 only)

## Repository Structure (target)
```
monte-carlo-claude-plugin/
├── CLAUDE.md                    # This file
├── README.md                    # Setup instructions for end users
├── skills/
│   └── monte-carlo/
│       └── SKILL.md             # Core deliverable
├── demo/
│   └── scenario.md              # Demo script and example prompts
└── .mcp.json.example            # MCP config template
```

## Time Budget (10 hours total)
1. **Hour 1** — Environment verification: MCP connectivity, dev data check, CLI apply test
2. **Hours 2–4** — Write and iterate on SKILL.md
3. **Hours 5–6** — Demo scenario setup and end-to-end testing
4. **Hour 7** — README + repo polish
5. **Hours 8–10** — Buffer: debugging, rehearsal, stretch goals

## Failure Risks (watch for these)
1. **Dev environment data too sparse** — verify lineage, alerts, and dbt models exist before writing SKILL.md
2. **Claude Code not triggering MC tools unprompted** — script demo prompts carefully; soft proactivity is fine
3. **`montecarlo monitors apply` CLI step failing** — test this early; have a YAML-display fallback
4. **`mcp-remote` connectivity issues** — test on the exact demo machine and network
5. **Scope creep on SKILL.md** — lock scope by hour 4

## Out of Scope (this hackathon)
- Direction 1: session tracing back into MC
- Claude Code lifecycle hooks (hard proactivity)
- Formal `.claude-plugin/` marketplace packaging
- Cursor/VS Code specific demos (SKILL.md works there but don't spend time on it)

## Strategic Context
This project maps to MC's "Call-0: Transitions and Validations" roadmap item. The goal is to expand WAUs beyond monitoring/troubleshooting by creating new entry points into MC through AI coding workflows. If successful, this POC is intended for production development — winning the hackathon is secondary to building a solid foundation.
