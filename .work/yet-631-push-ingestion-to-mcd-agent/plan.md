---
skill: start-work
ticket: YET-631
branch: fbenitez/yet-631-push-ingestion-to-mcd-agent
status: pr-open
pr: https://github.com/monte-carlo-data/mcd-agent-toolkit/pull/7
---

# Plan: Ship Pandora Push Model — Migrate plugin+skills to mcd-agent-toolkit

> Finalize the migration of the push-ingestion plugin and skills from the private `mcd-public-claude-skills` repo to the public `mcd-agent-toolkit` repo. Nearly all content is already on the branch. The only code fix needed is a wrong directory name in `run_evals.py`. After fixing that, stage everything, verify, and open a PR.

## Context

- **Ticket:** [YET-631](https://linear.app/montecarlodata/issue/YET-631/ship-pandora-push-model-migrate-pluginskills-to-mcd-agent-toolkit) — Ship Pandora Push Model: Migrate plugin+skills to mcd-agent-toolkit
- **Goal:** The push-ingestion plugin and skills are installable from `mcd-agent-toolkit`, all `/mc-*` slash commands work, marketplace and manual install both succeed.
- **Scope:** Fix `run_evals.py` path, verify install and commands end-to-end, commit all files.

## Current State

All content files are already on the branch (untracked):
- `plugins/claude-code/push-ingestion/` — plugin manifest, `skills/push-ingestion` symlink, 10 slash commands, evals, `install.sh`, README
- `skills/push-ingestion/` — `SKILL.md`, 8 reference docs, 45 Python warehouse templates
- `.claude-plugin/marketplace.json` — updated to include `mc-push-ingestion` entry
- `README.md` — updated to list the new plugin and skill

**`install.sh` is correct** — line 8 `SKILL_SRC="$PLUGIN_DIR/skills/push-ingestion"` resolves through the symlink `plugins/claude-code/push-ingestion/skills/push-ingestion -> ../../../../skills/push-ingestion`. No change needed.

## Relevant Files

| File | Role |
|------|------|
| `plugins/claude-code/push-ingestion/evals/run_evals.py` | Evals runner — **bug on line 28**: wrong skill dir name |
| `plugins/claude-code/push-ingestion/install.sh` | Manual install script — correct, no change needed |
| `plugins/claude-code/push-ingestion/.claude-plugin/plugin.json` | Plugin manifest |
| `plugins/claude-code/push-ingestion/skills/push-ingestion` | Symlink → `../../../../skills/push-ingestion` |
| `plugins/claude-code/push-ingestion/commands/*.md` | 10 slash command definitions |
| `skills/push-ingestion/SKILL.md` | Skill definition (210 lines) |
| `.claude-plugin/marketplace.json` | Root marketplace registry |
| `README.md` | Root docs |

## Phases

### ~~Phase 1: Fix run_evals.py and commit everything~~ ✓

**Goal:** Fix the one broken file, verify install and commands, and batch-commit all changes.

**Tasks:**
- [ ] `fix: correct SKILL_DIR path in run_evals.py` — `plugins/claude-code/push-ingestion/evals/run_evals.py` line 28: change `"montecarlo-push-ingestion"` → `"push-ingestion"`. The `SKILL_DIR` path resolves to `plugins/claude-code/push-ingestion/skills/montecarlo-push-ingestion` which doesn't exist; the symlink is named `push-ingestion`.
- [ ] Add a `[[ -d "$SKILL_SRC" ]] || { echo "ERROR: skill source not found: $SKILL_SRC"; exit 1; }` guard to `install.sh` before the `ln -s` block (line 22), to make path regressions immediately visible
- [ ] `feat: add mc-push-ingestion plugin and skills to mcd-agent-toolkit` — stage and commit all untracked files after reviewing `git status` to confirm file list

**Verify (after all tasks):**
- [ ] `python -m json.tool .claude-plugin/marketplace.json` exits 0 (valid JSON)
- [ ] Run `bash plugins/claude-code/push-ingestion/install.sh` — exits 0, creates `~/.claude/skills/push-ingestion` symlink
- [ ] `readlink -f ~/.claude/skills/push-ingestion` resolves to `<repo>/skills/push-ingestion` (not inside plugin dir)
- [ ] `ls ~/.claude/commands/mc-*.md | wc -l` outputs `10`
- [ ] Run install.sh a second time — exits 0, prints "already exists — skipping" for every artifact (idempotency)
- [ ] `pip install anthropic && ANTHROPIC_API_KEY=<key> python plugins/claude-code/push-ingestion/evals/run_evals.py` — pass rate ≥ 85% across 25 cases (requires API key)
- [ ] Restart Claude Code: `/mc-build-metadata-collector`, `/mc-validate-metadata`, `/mc-delete-push-tables`, `/mc-build-lineage-collector`, `/mc-build-query-log-collector`, `/mc-validate-lineage`, `/mc-validate-query-logs`, `/mc-create-lineage-node`, `/mc-create-lineage-edge`, `/mc-delete-lineage-node` all appear

---

## Verification Commands

- `python -m json.tool .claude-plugin/marketplace.json` — validate JSON
- `bash plugins/claude-code/push-ingestion/install.sh` — manual install smoke test
- `readlink -f ~/.claude/skills/push-ingestion` — confirm symlink target
- `ls ~/.claude/commands/mc-*.md | wc -l` — confirm 10 commands installed

## Open Questions

- **Notion doc updates**: Ticket requires updating internal Notion docs and developer guide to point to `mcd-agent-toolkit`. These are external to the codebase — this PR ships the code; Notion updates are a separate step.
- **Evals API key**: Running `run_evals.py` requires an `ANTHROPIC_API_KEY`. This is a manual verify step; CI execution depends on whether the key is available in the CI environment.

## Out of Scope

- Updating Notion / internal developer guide docs (external)
- Changes to other plugins or skills

## Changes from Initial Draft

- **Removed `install.sh` path fix** (architecture reviewer): `SKILL_SRC="$PLUGIN_DIR/skills/push-ingestion"` is correct — the `skills/push-ingestion` symlink inside the plugin dir resolves to `../../../../skills/push-ingestion`. No bug exists.
- **Added `run_evals.py` fix** (testing-strategy reviewer): line 28 references `montecarlo-push-ingestion` but the actual symlink is named `push-ingestion`.
- **Added `install.sh` pre-flight guard** (testing-strategy reviewer): `[[ -d "$SKILL_SRC" ]] || exit 1` to make future path regressions immediately visible.
- **Improved verify steps** (completeness reviewer): check all 10 commands (not 3), verify symlink target with `readlink -f`, run install.sh twice for idempotency, validate marketplace.json JSON.
- **Collapsed to single phase** (architecture reviewer): the scope is small enough for one phase.

## Alternatives Considered

- **`git rev-parse --show-toplevel` for repo root in install.sh** (completeness reviewer): instead of counting `..` levels. Current relative-symlink approach is consistent with the established pattern in this repo and is unambiguous given the fixed directory depth. Not adopting — consistent with existing plugins is more important than marginal robustness here.
- **Copy-on-install vs. symlink** (security reviewer): copying files at install time vs. symlinks that track the live working tree. Symlinks are the established pattern in this toolkit and give users automatic updates via `git pull`. Documented in README as expected behavior. Not changing.

## Lessons

<!-- Populated during the work by /hack and /learn. Each entry: what happened, what was learned, where it should go. -->
