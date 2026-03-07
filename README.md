# Monte Carlo AI Editor Skill

Bring Monte Carlo data observability into your editor — automatically, before you write a single line of code.

## What this does

When you reference a dbt model or table, Monte Carlo context comes to you: table health, active alerts, lineage, and downstream blast radius. Your AI editor uses that context to shape the code it writes — not just surface it. If you try to rename a column with 500 downstream dependents, the editor recommends a safe transition strategy and explains why, citing the specific MC data it found. When you add new logic, it generates and deploys the right monitor for your logic — validation, metric, comparison, or custom SQL — before you merge.

## Editor & Stack Compatibility

The skill works with any AI editor that supports MCP and the Agent Skills format — including Claude Code, Cursor, and VS Code.

For data stacks, compatibility varies by how you work:

| Stack | Support | Notes |
|---|---|---|
| dbt + any MC-supported warehouse | ✅ Full | Optimized and tested |
| SQL-first, no dbt | 🟡 Partial | Core workflows work via explicit prompting; auto-triggers on file open coming soon |
| Databricks notebooks | 🟡 Partial | Health check, impact assessment, and alert triage work; file-based triggers coming soon |
| SQLMesh | 🟡 Partial | Core workflows work; native SQLMesh project structure support coming soon |
| PySpark / non-SQL pipelines | 🟠 Limited | Manual prompting only; broader support on the roadmap |

**Coming shortly:** Generic SQL file triggers, Databricks notebook support, and SQLMesh project structure support — so auto-activation works regardless of your transformation tool.

Core workflows — table health check, change impact assessment, alert triage, and monitor generation — work for any warehouse supported by Monte Carlo.


## Prerequisites

- Claude Code, Cursor, VS Code or any editors with MCP support
- Monte Carlo account with Editor role or above
- [MC CLI](https://docs.getmontecarlo.com/docs/using-the-cli) installed for monitor deployment (`pip install montecarlodata`)

## Setup

### Step 1 — Obtain an MCP server key

1. Go to **Monte Carlo → Settings → API Keys**
2. Click **Add** and select type **MCP Server**
3. Copy the key — it has two parts: `KEY_ID` and `KEY_SECRET`

MCP keys are separate from standard API keys. Standard keys work for the CLI; MCP keys work for the editor integration.

### Step 2 — Install the skill

(Will update once this repo is made public) Copy the skill file to your editor's skills directory. For Claude Code:

```bash
git@github.com:monte-carlo-data/monte-carlo-editor-skill.git
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

Open your dbt project (or any data engineering codebase) in your editor. From there, you can either reference a few models or tables you plan to work on — or just prompt the editor with the change you want to make. The skill activates automatically based on what you're doing; no special commands needed.

**Workflow 1 — Table health check:** Opens when you reference a `.sql` file, dbt model, or table name. Surfaces freshness, row count, importance, lineage, and active alerts. Auto-escalates to a full impact assessment if the table has active alerts, key asset dependents, or high importance.

**Workflow 2 — Monitor generation:** After you add new transformation logic (a column, filter, or business rule), suggests and deploys a validation, metric, comparison, or custom SQL monitor as code.

**Workflow 3 — Alert triage:** When you ask about data quality issues. Lists open alerts, checks table state, traces lineage to find the root cause or blast radius.

**Workflow 4 — Change impact assessment:** Fires automatically before any SQL edit — including filter changes, bugfixes, reverts, and parameter tweaks, not just schema changes. Surfaces downstream blast radius, active incidents, column exposure in recent queries, and monitor coverage. Reports a risk tier (High / Medium / Low) and translates the findings into a specific code recommendation. If the MC data suggests your planned approach is risky, Claude will recommend a safer alternative and explain why — citing the specific tables, alert counts, and read volumes it found.

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
