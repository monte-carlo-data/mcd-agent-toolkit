# Monte Carlo Skills

Public Claude Code skills by [Monte Carlo Data](https://www.montecarlodata.com/).

## Installation

```
/plugin marketplace add monte-carlo-data/mcd-skills
```

## Available Skills

### generate-validation-notebook

Generate SQL validation notebooks for dbt PR changes. Analyzes a GitHub PR or local dbt repo, classifies models as new or modified, and produces a notebook with validation queries.

```
/monte-carlo:generate-validation-notebook <PR_URL or local path>
```
