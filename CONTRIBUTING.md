# Contributing to mcd-agent-toolkit

Welcome! We appreciate contributions from both Monte Carlo engineers and the community.

**Repo layout:** `skills/` is the single source of truth for skill content. `plugins/claude-code/` contains editor-specific plugin wrappers that reference skills via symlinks.

## Repository structure

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

Plugins reference skills via symlinks so that skills are authored once and shared across the corresponding plugins. When a user installs a plugin, Claude Code resolves the symlinks and copies the real files into its plugin cache.

## Adding a new skill

1. Create a new directory under `skills/` with a kebab-case name (e.g., `skills/my-new-skill/`).
2. Add a `SKILL.md` with valid YAML frontmatter (`name` and `description` are required). Follow the [Agent Skills specification](https://agentskills.io).
3. Optionally add supporting directories: `scripts/`, `references/`, `assets/`.
4. Test the skill locally by copying it to `~/.claude/skills/my-new-skill/` and verifying Claude discovers and activates it correctly.

## Adding a new Claude Code plugin for a skill

1. Create the plugin directory: `plugins/claude-code/<skill-name>/`.
2. Create `.claude-plugin/plugin.json` with at minimum `name`, `version`, `description`, `skills`. Use existing plugins as a template.
3. Create `skills/` inside the plugin directory and add a symlink to the shared skill:
   ```bash
   cd plugins/claude-code/<skill-name>/skills
   ln -s ../../../../skills/<skill-name> <skill-name>
   ```
4. If the plugin needs hooks, create a `hooks/` directory at the plugin root and add hook files there.
5. Add the plugin to `marketplace.json` at the repo root.
6. Test locally with `claude --plugin-dir ./plugins/claude-code/<skill-name>`.

## Updating an existing skill

1. Edit files directly under `skills/<skill-name>/`. The corresponding plugin picks up changes automatically via the symlink — no additional steps needed.
2. If the change is user-facing, bump the `version` in the corresponding plugin's `plugin.json`. Claude Code uses the version field to determine whether to update an installed plugin.

## Fixing a bug

1. For skill content bugs: fix in `skills/<skill-name>/` and bump the plugin version.
2. For plugin-level bugs (hooks, plugin.json config): fix in `plugins/claude-code/<skill-name>/` and bump the plugin version.

## Pull request guidelines

- One skill or plugin per PR unless changes are tightly coupled.
- Include a clear description of what the skill/plugin does and when it should activate.
- For new skills: include example prompts that should trigger the skill.
- For bug fixes: describe the incorrect behavior and how to reproduce.
- Ensure symlinks are relative and resolve correctly (CI will verify this).
- Run `git log --follow` on any moved files to confirm history is preserved.

## Version bumping

- **Patch** (`1.0.0` → `1.0.1`): bug fixes and minor content improvements.
- **Minor** (`1.0.0` → `1.1.0`): new features, new scripts, or significant skill content changes.
- **Major** (`1.0.0` → `2.0.0`): breaking changes to skill behavior or hook interfaces.

## Adding support for a new editor

1. Create a new directory under `plugins/` (e.g., `plugins/cursor/`).
2. Inside it, create per-skill directories that follow the target editor's convention (e.g., `.cursor/rules/` for Cursor).
3. Reference or inline content from `skills/` — the shared skill directory remains the source of truth.
4. Document the installation steps in the plugin's own README and in the repo's main README.
