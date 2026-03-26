# Monte Carlo Push Ingestion Plugin

This plugin gives Claude expert knowledge of Monte Carlo's push ingestion model and the
ability to **generate ready-to-run collection scripts** for your specific data warehouse.

## What it does

### Skill (auto-triggered)
When you discuss push ingestion in conversation, Claude automatically loads this skill and
guides you through:
- Setting up the required API keys
- Generating collection scripts tailored to your warehouse
- Pushing metadata, lineage, and query logs to Monte Carlo
- Validating that pushed data is visible in the platform
- Managing custom lineage nodes and edges
- Deleting push-ingested tables when needed

### Slash commands (explicit)

| Command | Description |
|---|---|
| `/mc-build-metadata-collector` | Generate a metadata collection script for your warehouse |
| `/mc-build-lineage-collector` | Generate a lineage collection script for your warehouse |
| `/mc-build-query-log-collector` | Generate a query log collection script for your warehouse |
| `/mc-validate-metadata` | Verify pushed metadata via the Monte Carlo GraphQL API |
| `/mc-validate-lineage` | Verify pushed lineage via the Monte Carlo GraphQL API |
| `/mc-validate-query-logs` | Verify pushed query logs via the Monte Carlo GraphQL API |
| `/mc-create-lineage-node` | Create a custom lineage node via GraphQL |
| `/mc-create-lineage-edge` | Create a custom lineage edge via GraphQL |
| `/mc-delete-lineage-node` | Delete a custom lineage node via GraphQL |
| `/mc-delete-push-tables` | Delete push-ingested tables via GraphQL |

## Prerequisites

You need two separate Monte Carlo API keys:

1. **Ingestion key** — for pushing data
   ```bash
   montecarlo integrations create-key --scope Ingestion --description "Push ingestion"
   ```

2. **GraphQL API key** — for verification queries
   Create at: https://getmontecarlo.com/settings/api

See [`prerequisites.md`](../../../skills/push-ingestion/references/prerequisites.md) for full setup instructions.

## Installation

### Claude Code — via Marketplace (recommended)

```
/plugin marketplace add monte-carlo-data/mcd-agent-toolkit
/plugin install mc-push-ingestion@mcd-agent-toolkit
```

### Manual install

Clone the repo and run the install script:

```bash
git clone https://github.com/monte-carlo-data/mcd-agent-toolkit.git
cd mcd-agent-toolkit
bash plugins/claude-code/push-ingestion/install.sh
```

Restart Claude Code after running. The script symlinks the skill and all `/mc-*` commands
into your `~/.claude/` directory so that `git pull` updates take effect immediately.
