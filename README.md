# mcd-agent-toolkit

Monte Carlo's official toolkit for AI coding agents. Contains skills and plugins that integrate Monte Carlo's data observability platform — lineage, monitoring, validation and alerting — into your development workflow.

## Prerequisites

- An [Monte Carlo](https://www.montecarlodata.com) account with Editor role or above
- [Monte Carlo MCP server](https://docs.getmontecarlo.com/docs/mcp-server) configured (required by the `safe-change` plugin/skill)
      <details>
      <summary>Click to expand - Configure Monte Carlo MCP Server</summary>
      
      1. Obtain an MCP server key:
         — Go to Monte Carlo → Settings → API Keys, click Add.
         - Select type MCP Server. Copy the `KEY_ID` and `KEY_SECRET`.
      
      2. Configure the MCP server 
         — Run `cp .mcp.json.example <mcp-config-path>/.mcp.json` to either:
            - Project-level: `.mcp.json` at your project root (recommended — keeps config scoped to the project)
            - Global: `~/.claude/claude.json` (path depends on your coding agent; applies to all projects)
         - Replace `<KEY_ID>` and `<KEY_SECRET>` with your MCP key values.
  
      3. Verify — In Claude Code, ask: "Test my Monte Carlo connection". Claude will call `testConnection` and confirm
         your credentials are working.
      </details>


## Installing plugins (recommended)

**Monte Carlo recommends installing skills via their corresponding plugins.** Plugins bundle the skill together with hooks, configuration and additional capabilities that provide a richer experience (e.g., automatic context enrichment from MC lineage data, executing validation queries and synthesizing results in your coding sessions).

### Claude Code

1. Add the marketplace:
   ```
   /plugin marketplace add monte-carlo-data/mcd-agent-toolkit
   ```
2. Install a plugin:
   ```
   /plugin install mc-safe-change@mcd-agent-toolkit
   /plugin install mc-generate-validation-notebook@mcd-agent-toolkit
   ```
3. Updates — `claude plugin update` pulls in the latest skill and hook changes.

## Available plugins

| Plugin | Description |
|---|---|
| `mc-safe-change` | Analyzes schema changes using MC lineage, monitoring, alerts, queries, and table metadata. Generates Monte Carlo monitors and validation queries for safe deployments. |
| `mc-generate-validation-notebook` | Generates executable validation queries from a pull request and packages them into Monte Carlo notebooks for direct testing. |

## Using skills directly (advanced)

Skills can also be used standalone without the plugin wrapper. This section is for users who want to submit skills to registries or use them with non-Claude-Code agents. Monte Carlo recommends the plugin approach above for the best experience.

### skills.sh (Vercel CLI)

```bash
npx skills add monte-carlo-data/mcd-agent-toolkit --skill safe-change
```

### Manual installation

Copy to `~/.claude/skills/` or `.agents/skills/`:

```bash
cp -r skills/safe-change ~/.claude/skills/safe-change
```

## Available skills

| Skill | Description |
|---|---|
| `safe-change` | Analyzes schema changes using MC lineage, monitoring, alerts, queries, and table metadata. Generates monitors and validation queries for safe deployments. |
| `generate-validation-notebook` | Generates executable validation queries from a pull request and packages them into Monte Carlo notebooks for direct testing. |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding skills, creating plugins, and submitting pull requests.

## License

This project is licensed under the Apache-2.0 license — see [LICENSE](LICENSE) for details.

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
