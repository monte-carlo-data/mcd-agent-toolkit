# Monte Carlo Claude Code Plugin

## Project Overview

This repository (`mcd-agent-toolkit`) is a monorepo containing Monte Carlo's AI editor skills and plugins. This CLAUDE.md covers the Claude Code plugin for the `safe-change` skill — Phase 1 of the editor plugin work.

The plugin is part of a broader shift-left pipeline at Monte Carlo:
- **Editor Plugin** (this work) — safe changes during active development
- **PR Review Agent** — validation at pull request time
- **CI Gate Agent** — enforcement at merge/deploy time

The PR and CI agents follow an adapter pattern isolating GitHub/dbt-specific code. This plugin follows the same convention where applicable — warehouse-specific execution logic and editor-specific hook implementations are isolated behind adapters.

---

## Repository Structure

```
mcd-agent-toolkit/
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── SECURITY.md
├── .claude-plugin/
│   └── marketplace.json               # Marketplace catalog — do not edit paths here
├── skills/
│   ├── safe-change/                   # Canonical skill source — all skill edits go here
│   │   ├── SKILL.md
│   │   ├── README.md
│   │   └── references/
│   │       └── TROUBLESHOOTING.md
│   └── generate-validation-notebook/  # Out of scope for this work
│       ├── SKILL.md
│       └── scripts/
└── plugins/
    ├── claude-code/
    │   ├── safe-change/               # THIS IS WHAT WE ARE BUILDING
    │   │   ├── hooks/
    │   │   │   ├── hooks.json         # Hook manifest — declares which hooks fire
    │   │   │   └── mc_context_hook.py # Hook scripts — currently empty placeholders
    │   │   └── skills/
    │   │       └── safe-change -> ../../../../skills/safe-change  # relative symlink
    │   └── generate-validation-notebook/  # Out of scope for this work
    │       └── skills/
    │           └── generate-validation-notebook -> ../../../../skills/generate-validation-notebook
    └── cursor/
        └── README.md                  # Out of scope — Cursor plugin is future work
```

**Key structural notes:**
- Skills live in `skills/` at the repo root — the single source of truth
- Plugin skill directories are **relative symlinks** into `skills/` — never copy or edit skill files inside plugin directories
- Symlinks are confirmed to work correctly through `git clone` and `plugin install` on Mac/Linux. Windows behavior is untested and should be verified when the repo goes public
- Do not edit `SKILL.md` from within the plugin directory — always edit `skills/safe-change/SKILL.md`

---

## Installation (for reference)

```bash
claude plugin marketplace add monte-carlo-data/mcd-agent-toolkit
claude plugin install mc-safe-change@mcd-agent-toolkit
```

Users set credentials once in their shell profile:
```bash
export MCD_ID=your-key-id
export MCD_TOKEN=your-key-secret
```

> If you previously installed the `safe-change` skill manually,
> remove it before installing the plugin:
> `rm -rf ~/.claude/skills/safe-change`

Updating:
```bash
claude plugin marketplace update mcd-agent-toolkit
```

---

## Phase 1 Scope

This CLAUDE.md covers Phase 1 only. Phase 2 (session tracing back into MC) is out of scope.

**Phase 1 deliverables:**
1. Hard proactivity via `PreToolUse` hook (`hooks.json` + `pre_edit_hook.py`)
2. Proactive validation prompting via `PostToolUse` hook (`post_edit_hook.py`)
3. Pre-commit prompting via `PreBash` hook (`pre_commit_hook.py`)
4. Double-trigger prevention via session marker
5. Validation query execution against Snowflake with result interpretation and feedback loop
6. Slash command `/mc-validate` as explicit fallback

---

## Component 1: Hook Manifest (`hooks/hooks.json`)

Declares all hooks the plugin registers with Claude Code. Create with the following content:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "command": "python3 hooks/pre_edit_hook.py"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "command": "python3 hooks/post_edit_hook.py"
      }
    ],
    "PreBash": [
      {
        "matcher": "git commit",
        "command": "python3 hooks/pre_commit_hook.py"
      }
    ]
  }
}
```

Reference this from `plugin.json` under the plugin's hook configuration.

---

## Component 2: Plugin Manifest

Create `plugins/claude-code/safe-change/.claude-plugin/plugin.json`:

```json
{
  "name": "mc-safe-change",
  "version": "1.0.0",
  "description": "Monte Carlo Safe Change — data observability context and safe change enforcement in your editor",
  "author": "Monte Carlo Data",
  "skills": ["skills/safe-change"],
  "hooks": "hooks/hooks.json",
  "mcpServers": {
    "monte-carlo": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://integrations.getmontecarlo.com/mcp/",
        "--header",
        "x-mcd-id: ${MCD_ID}",
        "--header",
        "x-mcd-token: ${MCD_TOKEN}"
      ]
    }
  }
}
```

**Note on MCP endpoint:** Currently using `/mcp/`. When the dedicated `/mcp/editor/claude/` endpoint is ready for instrumentation, this is the only place that needs updating.

---

## Component 3: Pre-Edit Hook (`hooks/pre_edit_hook.py`)

Fires **before** every file edit. Blocks the edit until Workflow 4 runs if it hasn't for this specific change.

**Why PreToolUse:** The synthesis step in Workflow 4 is designed to shape the code change before it is written. A PostToolUse hook would make synthesis commentary on a completed edit, defeating its purpose. PreToolUse intercepts before the edit happens.

**Critical constraint:** Any unhandled exception must exit cleanly with code 0 and allow the edit to proceed. A broken hook must never block the engineer's session.

### Behavior

1. Read tool input from stdin — extract `file_path`
2. Check if file is a relevant dbt/SQL model — exit silently if not
3. Check for `MC_WORKFLOW4_COMPLETE: <table_name>` marker in session context
4. If marker absent → inject mandatory Workflow 4 instruction
5. If marker present → exit silently, allow edit to proceed

### Relevant file detection

A file is relevant if ALL of the following are true:
- Extension is `.sql` or `.yml`
- Path contains `/models/` directory
- NOT in `seeds/`, `analyses/`, `macros/`, `snapshots/`
- Contains `{{ ref(` or `{{ source(` in first 50 lines (check only when extension matches)

### Double-trigger prevention

The SKILL.md outputs this marker after Workflow 4 completes:
```
<!-- MC_WORKFLOW4_COMPLETE: <table_name> -->
```

The hook scans recent session context for this marker before deciding whether to inject. Add the following instruction to `skills/safe-change/SKILL.md` at the end of the Workflow 4 synthesis step:

```
After presenting the full Workflow 4 impact report and synthesis,
output the following marker on its own line:
<!-- MC_WORKFLOW4_COMPLETE: <table_name> -->
This marker prevents the pre-edit hook from re-triggering Workflow 4
for the same table in the same session.
```

### Injection output format

```json
{
  "type": "result",
  "result": "MANDATORY: Before proceeding with this file edit, run Workflow 4 (change impact assessment) as defined in the Monte Carlo safe-change skill for the table in the file being edited. Present the full impact report and synthesis step before making any edits. Do not edit the file until Workflow 4 is complete."
}
```

---

## Component 4: Post-Edit Hook (`hooks/post_edit_hook.py`)

Fires **after** file edits. Prompts once per turn — never per file — when the engineer may want to validate their change.

### Turn-level accumulation (critical behavior)

The hook fires after each individual `Edit` call, but must only prompt **once per Claude turn** covering **all files edited in that turn**.

Use a turn-scoped accumulator (temp file keyed to current turn ID) to collect all dbt model files edited during the turn. Only emit the prompt after the final edit in the turn — when no further tool calls are pending.

- 1 file edited in a turn → 1 prompt referencing that file
- 3 files edited in a turn → 1 prompt referencing all 3, fired after the last edit
- Never 3 prompts for 3 files

Use Claude Code's `stop_reason` signal to detect the final edit in a turn. Fall back to a 500ms debounce only if that signal is unavailable.

### Trigger conditions

Only prompt if ALL are true:
- Edited file is a relevant dbt/SQL model
- Workflow 4 ran earlier in this session for at least one edited table
- This is the last edit in the current Claude turn

### Prompt behavior

```
You've made changes to <N> dbt model(s): <table_1>, <table_2>...
Would you like to run validation queries to verify these changes
behaved as intended?

→ Yes: I'll generate and run queries for all changed models
→ No: You can use /mc-validate anytime to validate changes
```

### If yes — parameter collection

Collect once per session, cache for subsequent validations:

| Parameter | Required | Default | Notes |
|---|---|---|---|
| `dev_database` | Yes | None | Cannot be inferred — must collect |
| `dev_schema` | No | Same as production | |
| `snowflake_role` | No | User default | |
| `snowflake_warehouse` | No | User default | |

Never collect: production database, schema, table name, warehouse type — all known from `getTable` result in Workflow 4 session context.

### Validation query scope

When yes is confirmed, generate queries covering **all tables edited in the turn** — not just the last file. Use multi-model consolidation context from Workflow 4 where available.

### If Snowflake MCP unavailable

Save queries to `validation/<table_name>_<timestamp>.sql` and display:
```
Validation queries saved to validation/<table_name>_<timestamp>.sql

💡 To run validation queries automatically and get inline analysis,
configure the Snowflake MCP server in your editor:
https://docs.snowflake.com/developer-guide/snowflake-mcp/overview
```

---

## Component 5: Pre-Commit Hook (`hooks/pre_commit_hook.py`)

Fires **before** `git commit`. Asks two distinct questions in one turn if conditions are met.

### Trigger conditions

Fire only if ALL are true:
- Command matches `git commit` (any flags)
- Staged files include at least one `.sql` file under `models/`
- Workflow 4 ran this session for at least one staged table

Exit silently if conditions not met.

### Two questions in one turn

Ask both questions in a single injection. Each waits for an independent response. Only ask a question if its condition is met — do not ask about monitors if no coverage gap exists, do not ask about validation if Workflow 4 never ran.

```
Before this commit, two things to check:

1. Validation: Changes to <models> detected. Run validation
   queries before committing? (yes / no)

2. Monitor coverage: Workflow 4 found new logic in <model>
   with no custom monitor coverage. Generate a monitor YAML
   file before committing? (yes / no)
```

### Question 1 — Validation

Same flow as post-edit hook: parameter collection if not cached, query generation, execution if Snowflake MCP available, result interpretation.

If validation reveals a problem:
```
Validation found an issue: <summary>
Proceed with commit anyway, or fix the issue first?
→ Proceed: commit will continue
→ Fix first: commit is blocked
```

If engineer says no to validation — commit proceeds immediately.

### Question 2 — Monitor coverage

**Trigger:** Workflow 4 found zero custom monitor coverage for new logic in a staged table.

Use Workflow 4 session context — do not make additional `getMonitors` calls.

If yes:
- Generate monitor YAML using appropriate `create*MonitorMac` tool
- Save to `monitors/<table_name>.yml`
- Do NOT run `montecarlo monitors apply` automatically
- Tell engineer:

```
Monitor YAML saved to monitors/<table_name>.yml

Review it, then deploy when ready:
  montecarlo monitors apply --dry-run    # preview
  montecarlo monitors apply --auto-yes   # apply
```

If no — commit proceeds.

---

## Component 6: Slash Command (`/mc-validate`)

Explicit on-demand fallback for engineers who prefer direct invocation.

Declare in `plugin.json` under `commands`:
```json
"commands": {
  "mc-validate": {
    "description": "Generate and run validation queries for the current change",
    "command": "python3 hooks/validate_command.py"
  }
}
```

Behavior identical to responding yes to the post-edit prompt. This is the fallback surface, not the primary mechanism.

---

## Component 7: Validation Query Execution (Snowflake)

Extends Workflow 5 from SKILL.md. Executes generated queries and feeds results back into Claude's analysis.

### Adapter pattern

All Snowflake-specific code lives in `hooks/adapters/warehouse/`. Define the interface first, then implement:

```
hooks/adapters/warehouse/
├── base.py        # Abstract WarehouseAdapter interface
└── snowflake.py   # Snowflake implementation
```

```python
class WarehouseAdapter:
    def execute_query(self, sql: str) -> QueryResult:
        raise NotImplementedError
    def get_sample(self, result: QueryResult, max_rows: int = 20) -> list[dict]:
        raise NotImplementedError

class QueryResult:
    rows: list[dict]
    row_count: int
    columns: list[str]
    error: str | None
    truncated: bool
```

### Detection and graceful degradation

Check for Snowflake MCP availability before attempting execution. If unavailable, save queries to file and show encouragement note. Never require Snowflake MCP as a hard dependency.

### Execution constraints

- Cap result sets at 100 rows — never pass large result sets to Claude
- Read-only queries only — never execute mutations

### Result feedback loop

After execution, Claude must:

**A — Interpret results in plain English**
Not "query returned 3 rows" but "3 workspaces named MC Internal were reclassified from paying to non-paying — this matches the intent of the change."

**B — Reassess change impact**
Compare results against Workflow 4 findings. Update risk assessment if results reveal something the impact assessment missed.

**C — Propose code changes if results indicate a problem**
- Unexpected null rate → suggest COALESCE or NOT NULL constraint
- Unintended reclassifications → suggest tightening filter condition
- Duplicate rows → suggest deduplication or join fix

**D — Present concise summary**
```
Validation complete for <table_name>

✅ Row count: prod 45,231 → dev 45,228 (3 rows reclassified as expected)
✅ MC Internal reclassification: 3 workspaces → is_paying_workspace = FALSE
✅ No collateral reclassification detected
⚠️  table_health_scores: 3 MC Internal workspaces will be removed
    → Confirm with team this is intended before merging

Given the above, I recommend: <specific action>
```

---

## Component 8: Install/Uninstall Scripts

### `plugins/claude-code/safe-change/scripts/install.sh`

```bash
#!/bin/bash
set -e

echo "Installing Monte Carlo Safe Change plugin..."

# Remove standalone safe-change skill if present
SKILL_PATH="$HOME/.claude/skills/safe-change"
if [ -d "$SKILL_PATH" ]; then
  echo "Backing up and removing standalone safe-change skill..."
  cp -r "$SKILL_PATH" "$SKILL_PATH.backup"
  rm -rf "$SKILL_PATH"
  echo "Backup saved to $SKILL_PATH.backup"
fi

echo "✓ Monte Carlo Safe Change plugin installed."
echo "  Ensure MCD_ID and MCD_TOKEN are set in your shell profile."
echo "  Restart Claude Code to activate."
```

### `plugins/claude-code/safe-change/scripts/uninstall.sh`

```bash
#!/bin/bash
set -e

SKILL_PATH="$HOME/.claude/skills/safe-change"
BACKUP_PATH="$SKILL_PATH.backup"
if [ -d "$BACKUP_PATH" ]; then
  echo "Restoring standalone safe-change skill..."
  mv "$BACKUP_PATH" "$SKILL_PATH"
  echo "✓ Standalone skill restored."
else
  echo "No backup found. Install standalone skill from mcd-agent-toolkit/skills/ if needed."
fi

echo "✓ Plugin uninstalled."
echo "  Remove MCD_ID and MCD_TOKEN from your shell profile manually."
```

---

## Development Sequence

Build and test in this order. Do not skip ahead.

1. **Hook manifest + plugin manifest** — wire `hooks.json` and `plugin.json`, confirm plugin loads via `claude --plugin-dir`
2. **Pre-edit hook (detection only)** — file detection and silent exits, no injection yet
3. **Pre-edit hook (injection)** — add Workflow 4 injection, test Scenario 1
4. **Double-trigger testing** — confirm marker detection, test Scenario 4
5. **Post-edit hook (prompt only)** — turn accumulation and yes/no prompt, no execution
6. **Pre-commit hook (prompt only)** — staged file detection and two-question flow
7. **Slash command** — wire `/mc-validate`
8. **Snowflake adapter** — interface first, then implementation
9. **Execution feedback loop** — result interpretation, reassessment, code recommendations
10. **End-to-end test** — all scenarios

---

## Test Scenarios

All scenarios use `analytics.prod_internal_bi.client_hub_master` from MC's internal dbt repo.

**Scenario 1 — Filter change (hard proactivity)**
```
Prompt: "exclude internal MC employees from client_hub_master —
         add 'MC Internal' to the is_paying_workspace exclusion list"
Pass: Pre-edit hook intercepts, Workflow 4 runs before any edit,
      synthesis references exact CASE conditions from diff
Fail: Edit made without Workflow 4 running first
```

**Scenario 2 — Column add (monitor offer + validation)**
```
Prompt: "add a days_since_contract_start column similar to
         days_since_first_warehouse_created"
Pass: Workflow 4 runs, Workflow 2 offers monitor, Workflow 5
      generates targeted null/range check queries on dev only
Fail: Monitor offer skipped, or validation queries are generic
```

**Scenario 3 — Typo fix (safe rename detection)**
```
Prompt: "fix the typo salesforce_primary_worksapce_id →
         salesforce_primary_workspace_id"
Pass: Workflow 4 traces column through CTE chain, correctly
      identifies as low risk (internal only, never in final SELECT)
Fail: Change blocked unnecessarily, or made without any check
```

**Scenario 4 — Double-trigger check**
```
Setup: Workflow 4 ran for client_hub_master
Action: Make a second edit to the same file
Pass: Pre-edit hook detects MC_WORKFLOW4_COMPLETE marker,
      exits silently — Workflow 4 does NOT run again
Fail: Workflow 4 runs twice
```

**Scenario 5 — Post-edit prompt: one prompt per turn**
```
Setup: Workflow 4 ran, Claude edits 3 files in one turn
Pass: Exactly one prompt fires after the turn completes,
      referencing all 3 tables
Fail: Three separate prompts, or prompt fires mid-turn
```

**Scenario 6 — Pre-commit: two questions**
```
Setup: Workflow 4 ran, new column added with no monitor coverage,
       file staged for commit
Action: git commit -m "add days_since_contract_start"
Pass: Both questions asked in one turn — validation and monitor
      coverage. If yes to monitor: YAML saved, no auto-apply.
Fail: Auto-apply triggered, or two separate prompt turns
```

**Scenario 7 — Snowflake MCP unavailable**
```
Action: Respond yes to validation prompt, no Snowflake MCP configured
Pass: Queries saved to validation/<table>_<timestamp>.sql,
      encouragement note shown with Snowflake MCP setup link
Fail: Error shown, session interrupted, no file saved
```

---

## Key Constraints

- **Never duplicate workflow logic in hook code.** Hooks inject instructions; SKILL.md executes them.
- **Never edit skill files inside plugin directories.** Always edit `skills/safe-change/SKILL.md`.
- **Hooks must be silent on failure.** Exit 0 on any unhandled exception.
- **Execution is enhancement, not requirement.** All workflows function without Snowflake MCP.
- **Adapter interfaces first.** Define `base.py` before implementing `snowflake.py`.
- **No auto-apply of monitors.** Generate YAML and save — never run `montecarlo monitors apply` automatically.
- **One prompt per turn.** Post-edit hook must accumulate all turn edits before prompting.
- **Phase 2 is out of scope.** Do not implement session tracing back to MC.
- **Windows symlink behavior untested.** Flag if testing reveals issues when repo goes public.
- **Cursor plugin is out of scope.** `plugins/cursor/` is a placeholder — do not touch it.
