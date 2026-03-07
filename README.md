# Monte Carlo AI Editor Plugin

Bring Monte Carlo data observability context directly into Claude Code. When you modify a dbt model or SQL pipeline, get table health, lineage, active alerts, and change impact assessments — and deploy validation monitors — without leaving your editor.

## What this does

When you open a dbt model, Claude automatically surfaces table health, upstream/downstream lineage, active alerts, and a change impact assessment — and uses that context to shape the code it writes. If you try to rename a column with 500 downstream dependents, Claude won't just warn you — it will recommend a safe transition strategy and explain why, citing the specific MC data it found. When you add new logic, it generates and deploys monitors-as-code. It works with Claude Code, Cursor, and any AI editor with MCP support.

## Prerequisites

- Claude Code, Cursor, or VS Code with MCP support
- Node.js (LTS) + npm installed
- Monte Carlo account with Editor role or above
- MC CLI installed for monitor deployment (`pip install montecarlodata`)

## Setup

### Step 1 — Create an MCP server key

1. Go to **Monte Carlo → Settings → API Keys**
2. Click **Add** and select type **MCP Server**
3. Copy the key — it has two parts: `KEY_ID` and `KEY_SECRET`

MCP keys are separate from standard API keys. Standard keys work for the CLI; MCP keys work for the editor integration.

### Step 2 — Install the skill

Copy the skill file to Claude Code's skills directory:

```bash
mkdir -p ~/.claude/skills/monte-carlo
curl -fsSL https://raw.githubusercontent.com/monte-carlo-data/mc-claude-plugin/master/skills/monte-carlo/SKILL.md \
  -o ~/.claude/skills/monte-carlo/SKILL.md
```

Or from a local clone:

```bash
mkdir -p ~/.claude/skills/monte-carlo
cp skills/monte-carlo/SKILL.md ~/.claude/skills/monte-carlo/SKILL.md
```

### Step 3 — Configure your MCP server

Add the Monte Carlo MCP server to your project `.mcp.json` or global `~/.claude/claude.json`:

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

Replace `<KEY_ID>` and `<KEY_SECRET>` with your MCP key values. See `.mcp.json.example` for a copy-paste template.

### Step 4 — Verify the connection

In Claude Code, paste:

> "Test my Monte Carlo connection"

Claude will call `testConnection` and confirm your credentials are working.

## How to use it

You don't need to ask for it — the skill activates automatically.

**Workflow 1 — Table health check:** Opens when you reference a `.sql` file, dbt model, or table name. Surfaces freshness, row count, importance, lineage, and active alerts. Auto-escalates to a full impact assessment if the table has active alerts, key asset dependents, or high importance.

**Workflow 2 — Monitor generation:** After you add new transformation logic (a column, filter, or business rule), suggests and deploys a validation, metric, comparison, or custom SQL monitor as code.

**Workflow 3 — Alert triage:** When you ask about data quality issues. Lists open alerts, checks table state, traces lineage to find the root cause or blast radius.

**Workflow 4 — Change impact assessment: Fires automatically before any SQL edit — including filter changes, bugfixes, reverts, and parameter tweaks, not just schema changes. Surfaces downstream blast radius, active incidents, column exposure in recent queries, and monitor coverage. Reports a risk tier (High / Medium / Low) and translates the findings into a specific code recommendation. If the MC data suggests your planned approach is risky, Claude will recommend a safer alternative and explain why — citing the specific tables, alert counts, and read volumes it found.

### Deploying generated monitors

When Claude generates a monitor, it saves the YAML to `monitors/<table>.yml`. Deploy with:

```bash
montecarlo monitors apply --dry-run    # preview
montecarlo monitors apply --auto-yes   # apply
```

Your project needs a `montecarlo.yml` config in the working directory:

```yaml
version: 1
namespace: <your-namespace>
default_resource: <your-warehouse-name>
```

## Troubleshooting

See [TROUBLESHOOTING.md](skills/monte-carlo/TROUBLESHOOTING.md) for common setup and runtime issues.
