# Monte Carlo Skills

Public Claude Code skills by [Monte Carlo Data](https://www.montecarlodata.com/).

## Installation

```
/plugin marketplace add monte-carlo-data/mcd-skills
/plugin install monte-carlo@mcd-skills
```

## Available Skills

### safe-change
Automatically activates when a dbt model, SQL file, or table is referenced. Surfaces Monte Carlo context — table health, active alerts, lineage, blast radius — before any code is written, and uses those findings to shape code recommendations.

See [Introduction](safe-change/README.md), [Installation](safe-change/README.md#setup) and [Usage](safe-change/README.md#how-to-use-it). Requires the [Monte Carlo MCP Server](https://docs.getmontecarlo.com/docs/mcp-server).

### generate-validation-notebook

Generate SQL validation notebooks for dbt PR changes. Analyzes a GitHub PR or local dbt repo, classifies models as new or modified, and produces a notebook with validation queries.

```
/monte-carlo:generate-validation-notebook <PR_URL or local path>
```
