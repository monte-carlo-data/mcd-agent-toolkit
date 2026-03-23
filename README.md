# mcd-agent-toolkit

Monte Carlo's official toolkit for AI coding agents. Contains skills and plugins that integrate Monte Carlo's data observability platform — lineage, monitoring, and alerting — into your development workflow.

## Prerequisites

- A [Monte Carlo](https://www.montecarlodata.com) account with API access
- Set environment variables:
  - `MC_API_KEY` — your Monte Carlo API key
  - `MC_API_URL` — your Monte Carlo API URL

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

```
mcd-agent-toolkit/
├── skills/                                        ← source of truth for all MC skills, registry-submittable
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
│   └── claude-code/                               ← Claude Code plugin wrappers
│       ├── safe-change/                           ← self-contained plugin with hooks
│       │   ├── .claude-plugin/plugin.json
│       │   ├── skills/safe-change → symlink       ← points to ../../../../skills/safe-change
│       │   └── hooks/mc_context_hook.py
│       └── generate-validation-notebook/          ← thin plugin (no hooks)
│           ├── .claude-plugin/plugin.json
│           └── skills/generate-validation-notebook → symlink
│
├── marketplace.json                               ← Claude Code marketplace manifest
├── README.md
├── LICENSE
└── SECURITY.md
```

Plugins reference skills via symlinks so that skills are authored once and shared across all plugin wrappers. When a user installs a plugin, Claude Code resolves the symlinks and copies the real files into its plugin cache.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding skills, creating plugins, and submitting pull requests.

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
