# mcd-agent-toolkit

Monte Carlo's official toolkit for AI coding agents. Contains skills and plugins that integrate Monte Carlo's data observability platform — lineage, monitoring, and alerting — into your development workflow.

## Prerequisites

- A [Monte Carlo](https://www.montecarlodata.com) account with Editor role or above
- The **Monte Carlo MCP server** configured (required by the `safe-change` plugin/skill)

### Setting up the MCP server

1. **Obtain an MCP server key** — Go to **Monte Carlo → Settings → API Keys**, click **Add**, and select type **MCP Server**. Copy the `KEY_ID` and `KEY_SECRET`.

   > MCP keys are separate from standard API keys. Standard keys work for the CLI; MCP keys work for the editor integration.

2. **Configure the MCP server** — run `cp .mcp.json.example <mcp-configuration-path>/.mcp.json` to either:
   - **Project-level:** `.mcp.json` at your project root (recommended — keeps config scoped to the project)
   - **Global:** `~/.claude/claude.json` (applies to all projects)


   Replace `<KEY_ID>` and `<KEY_SECRET>` with your MCP key values.

3. **Verify** — In Claude Code, ask: *"Test my Monte Carlo connection"*. Claude will call `testConnection` and confirm your credentials are working.

## Installing plugins (recommended)

**Monte Carlo recommends installing skills via their corresponding plugins.** Plugins bundle the skill together with hooks and configuration that provide a richer experience (e.g., automatic context enrichment from MC lineage data).

### Claude Code

1. Add the marketplace:
   ```
   /plugin marketplace add monte-carlo-data/mcd-agent-toolkit
   ```
2. Install a plugin:
   ```
   /plugin install mc-safe-change@monte-carlo-mcd
   /plugin install mc-generate-validation-notebook@monte-carlo-mcd
   ```
3. Updates — `claude plugin update` pulls in the latest skill and hook changes.

## Available plugins

| Plugin | Description |
|---|---|
| `mc-safe-change` | Detects and prevents breaking schema changes using Monte Carlo lineage and monitoring data. Includes a context hook that automatically enriches your session with MC metadata. |
| `mc-generate-validation-notebook` | Generates Monte Carlo validation notebooks for data pipeline testing. |

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
| `safe-change` | Detect and prevent breaking schema changes using MC lineage and monitoring. |
| `generate-validation-notebook` | Generate validation notebooks for data pipeline testing. |

## Repository structure
<details>
<summary>Click to expand</summary>
```
mcd-agent-toolkit/
├── skills/
│   ├── safe-change/
│   │   ├── SKILL.md
│   │   ├── README.md
│   │   └── references/
│   │       └── TROUBLESHOOTING.md
│   └── generate-validation-notebook/
│       ├── SKILL.md
│       └── scripts/
│           ├── generate_notebook_url.py
│           └── resolve_dbt_schema.py
│
├── plugins/
│   └── claude-code/
│       ├── safe-change/
│       │   ├── .claude-plugin/plugin.json
│       │   ├── skills/safe-change → symlink
│       │   └── hooks/mc_context_hook.py
│       └── generate-validation-notebook/
│           ├── .claude-plugin/plugin.json
│           └── skills/generate-validation-notebook → symlink
│
├── marketplace.json
├── README.md
├── LICENSE
└── SECURITY.md
```
</details>

Plugins reference skills via symlinks so that skills are authored once and shared across the corresponding plugins. When a user installs a plugin, Claude Code resolves the symlinks and copies the real files into its plugin cache.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding skills, creating plugins, and submitting pull requests.

## License

This project is licensed under the Apache-2.0 license — see [LICENSE](LICENSE) for details.

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
