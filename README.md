# Monte Carlo Skills

Public Claude Code skills by [Monte Carlo Data](https://www.montecarlodata.com/).

## Installation

**Option A (recommended) — Claude Code plugin marketplace:**

```
/plugin marketplace add monte-carlo-data/monte-carlo-claude-plugin
/plugin install monte-carlo@monte-carlo-data-monte-carlo-claude-plugin
```

Skills installed this way are namespaced and invoked as `/monte-carlo:<skill-name>`.

**Option B — Install script:**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/monte-carlo-data/monte-carlo-claude-plugin/main/install.sh)
```

**Option C — via [skills.sh](https://skills.sh) CLI:**

```bash
npx skilladd monte-carlo-data/mcd-skills
```

> **Note:** The `safe-change` skill requires the [Monte Carlo MCP Server](https://docs.getmontecarlo.com/docs/mcp-server) to be configured. See [setup instructions](safe-change/README.md#setup) before use.

## Available Skills

### safe-change
Automatically activates when a dbt model, SQL file, or table is referenced. Surfaces Monte Carlo context — table health, active alerts, lineage, blast radius — before any code is written, and uses those findings to shape code recommendations.

See [Introduction](safe-change/README.md), [Installation](safe-change/README.md#setup) and [Usage](safe-change/README.md#how-to-use-it). Requires the [Monte Carlo MCP Server](https://docs.getmontecarlo.com/docs/mcp-server).

### generate-validation-notebook

Generate SQL validation notebooks for dbt PR changes. Analyzes a GitHub PR or local dbt repo, classifies models as new or modified, and produces a notebook with validation queries.

```
/monte-carlo:generate-validation-notebook <PR_URL or local path>
```
