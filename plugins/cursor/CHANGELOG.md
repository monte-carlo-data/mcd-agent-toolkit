# Changelog

All notable changes to the Monte Carlo Agent Toolkit plugin for Cursor will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.22.3] - 2026-07-29

### Changed

- monitoring-advisor: judge model selection via `modelName` on LLM-based eval transforms; `modelConnectionId` is BigQuery-only (AI-771)

## [1.22.2] - 2026-07-27

### Changed

- reinforce-agent: renamed the Monte Carlo tools the skill calls to their reinforcement loop names — `get_agent_health_summaries` → `get_reinforcement_loop_summaries` and `get_agent_health` → `get_reinforcement_loop_report` — and rebranded the skill guidance from "agent-health" to "reinforcement loop" (ORB-444).

## [1.22.1] - 2026-07-26

### Fixed

- troubleshoot-agent-traces: document that `get_agent_trace` (single-trace span tree)
  reads only the Monte Carlo–managed OTel store (`ao_clickhouse_otel`) and errors on
  the Cortex, Genie, customer-OTel, and MLflow backends. Backend guides, alert
  playbooks, direct-trace intake, and the tool tables now route span-grain drill-down
  on those backends through `run_troubleshooting_agent` (AI-710).

## [1.22.0] - 2026-07-22

### Added

- reinforce-agent: new skill that turns an AI agent's Monte Carlo agent-health diagnosis into code fixes — ranks diagnosed issues per workflow via `get_agent_health_summaries`, deep-dives a user-chosen workflow via `get_agent_health`, proposes fixes, and opens a PR. User-gated at each fan-out (which workflow, which issue, and before pushing).

## [1.21.0] - 2026-07-22

### Changed

- monitoring-advisor: conversation evals can now see tool calls — `includeToolCalls` (default ON at conversation grain) documented across the eval reference: TOOL entries in the judged `{{conversation}}`, action-aware checks (right tool, right config, did it error; query-before-answer), template library and Output-pillar packs updated, span-grain rejection noted

## [1.20.3] - 2026-07-22

### Changed

- troubleshoot-agent-traces: platform-agent conversation clustering (AI-677) — backend references updated for the server's Cortex/Genie clustering coverage: ClickHouse "only backend with conversation-grain eval monitors" drift fixed, clustering signal bullets + cluster-first localization steps added to Cortex/Genie, customer-OTel/MLflow-SDK "managed-store-only" claims rescoped, eval-alert grain rules now name Cortex/Genie as conversation-grain capable

## [1.20.2] - 2026-07-22

### Changed

- troubleshoot-agent-traces: follow-up to the AI-629 breaching-side guidance — the flag-eval side-resolution rule is now symmetric across `true_*`/`false_*` metrics and both breach directions (a rising `false_rate`, e.g. `content_safe`, breaches at the BOTTOM of the score range), quality scores breaching high are enumerated explicitly, and the Cortex backend reference defers to the shared side resolution instead of "worst-first" sampling.

## [1.20.1] - 2026-07-22

### Changed

- troubleshoot-agent-traces: the agent-alert-evaluation reference is now breaching-side aware (AI-629) — the breaching set follows the monitor's metric polarity + breach direction (flag evals breaching on a true-count sit at the TOP scores), replacing the direction-blind "worst-scoring / bottom 10" guidance; step-4 verification and a new common-mistakes row call out the wrong-side sampling trap.

## [1.20.0] - 2026-07-22

### Changed

- monitoring-advisor: Context pillar upgraded from a recommendation to an executable flow — user-named upstream tables → tagged freshness/schema/volume table monitors → optional `Context for {AGENT_NAME}` data product wrapper (dry-run footprint preview first; Data Mesh rejection keeps the monitors) → field-level depth via the data-monitor references; `create_or_update_data_product` added to the skill tool tables (AI-650)

## [1.19.0] - 2026-07-21

### Changed

- monitoring-advisor: agent-onboarding monitor conventions (AI-651) — every
  monitor in the POBC playbook (agent monitors and Context-pillar data-quality
  monitors) carries the `agent:{AGENT_NAME}` footprint tag; audiences are asked
  once and applied to every create (with `failure_audiences` defaulting to the
  same selection); one domain across the footprint; audit/teardown via
  `get_monitors(monitor_tags=["agent:<AGENT_NAME>"])`
- agent-validation-monitor reference: documented the `tags` parameter
- data-monitor-creation reference: agent-onboarding conditional for tagging
  warehouse DQ monitors created for an agent

## [1.18.1] - 2026-07-21

### Added

- monitoring-advisor: Behavior pillar (AI-648) — agent-understanding investigation summary before proposing monitors (purpose, dominant tool span, healthy trajectory shape, intents, failure modes); runaway-loop trajectory playbook with thresholds derived from observed trace history (max observed + headroom; zero historical matches by design — a regression guardrail, proven with a pre-create breach preview); ungrounded-in-data pattern created as a draft with a breach preview and an LLM-judge upgrade path; `preview` / `is_draft` documented on the trajectory reference with the `agent:<AGENT_NAME>` tag convention

## [1.18.0] - 2026-07-21

### Added

- monitoring-advisor: custom-prompt template library (`frustration_free_score`, `answer_attempt_score`, `user_correction`) and Output-pillar eval packs — baseline pack for every agent, analytics pack for Snowflake Cortex / Databricks Genie — in `agent-evaluation-monitor.md`, with pack routing in `agent-monitor-creation.md` and a starting-packs pointer in the POBC walkthrough's Output row (AI-647)
- monitoring-advisor: documented the `tags` parameter on `create_or_update_agent_evaluation_monitor` (name/value shape) and the tag-every-monitor `agent:<AGENT_NAME>` default (AI-647)

## [1.17.0] - 2026-07-21

### Added

- monitoring-advisor: Performance pillar baseline monitor set in the agent-metric-monitor reference — p50+p95 latency anomaly, p50+p95 token anomaly, daily token SUM, status_code error-level anomaly, and a measured-p95 latency SLO threshold, with per-backend gating and shared defaults (daily schedule, agent tag, draft-capable) (AI-646)
- monitoring-advisor: documented `tags` and `is_draft` (un-draft-on-edit footgun) on create_or_update_agent_metric_monitor; routing rows for performance-coverage asks

## [1.16.0] - 2026-07-21

### Changed

- monitoring-advisor: POBC proposal walkthrough in the agent monitor creation
  reference — open with the Performance/Output/Behavior/Context framing, walk
  the user through the plan pillar by pillar (evidence → proposed monitors →
  confirm), Context as a recommendation-only pillar until lineage wiring
  lands. Global defaults: daily schedules (`interval_minutes=1440`) and
  count-based eval sampling (`{"count": 100}`). (AI-645)

## [1.15.2] - 2026-07-20

### Changed

- monitoring-advisor: conversation-grain evaluation guidance updated for the AI-636 backend change — Snowflake Cortex and Databricks Genie agents now support `is_agent_conversation_aggregation` (Databricks MLflow agents remain span-only); added Genie no-token/model caveats to the metric guidance and a `backend_class` capability note to agent-monitor-creation

## [1.15.1] - 2026-07-20

### Changed

- troubleshoot-agent-traces: the direct (no-alert) path resolves the exact backend from `get_agent_metadata`'s new `backend_class` field instead of asking the user / splitting on `sourceType` (AI-635; a null `backend_class` — older server or unclassifiable agent — still falls back to asking)
- monitoring-advisor, troubleshoot-agent-traces, instrument-agent: `get_agent_metadata` field docs gain `backend_class`

## [1.15.0] - 2026-07-19

### Added

- New `troubleshoot-agent-traces` skill: investigates AI-agent alerts (evaluation, metric, trajectory, validation) and agent traces/conversations. Kicks off the trace troubleshooting agent in parallel (`run_troubleshooting_agent`), identifies the agent's backend exclusively from the new `get_alert_agent_classification` tool (server-side classification — never name/MCON heuristics), and routes to per-alert-type and per-backend investigation playbooks (ClickHouse OTel, Snowflake Cortex, Databricks Genie, customer OTel trace table, Databricks MLflow SDK, MLflow Knowledge Assistant).

### Changed

- analyze-root-cause, incident-response, and context-detection route agent-monitor alerts to the new skill; monitoring-advisor's "investigating agent traces" trigger moved there (it keeps monitor creation).

## [1.14.0] - 2026-07-03

### Changed

- Refresh agent monitor references to match the current tool contract: single `agent` reference source (no `dw_id`/`data_source`), required `warehouse` for metric/evaluation/validation, `schedule_type` limited to `fixed`/`manual` with per-type interval floors, and `agent_span_filters` capped at one filter object.
- Agent monitor warehouse is now sourced from `get_agent_metadata`'s `warehouse_uuid`/`warehouse_name` (show the name, pass the uuid; fall back to `get_warehouses` only when both are null).
- Evaluation reference: correct predefined transform functions (`output_length`, `json_validity`, `keywords`), typed custom transforms (`custom_prompt`/`custom_sql` with camelCase `outputType`/`sqlExpression`), boolean-output alerting via `TRUE_RATE`/`FALSE_RATE`, and removal of unsupported `classification`/`sentiment`.
- Metric reference: full agent metric catalog, `NEQ` operator, operator/threshold rules, `ROW_COUNT_CHANGE` and trace-aggregation constraints.
- Validation reference: `negated`-flag negation (no `not_equal`/`not_null`), UNARY `value` vs BINARY `left`/`right`, numeric `status_code`.
- Trajectory reference: `SPAN_OCCURRENCE` and `SPAN_RELATION` conditions, OR-only combination, occurrence count floors, `spanField` hierarchy, and the negated-relation pattern for a missing step.
- Span-field reference: add `parent_span_id`, `model_name`, `status_code`, `is_tool_call`, `is_llm_call`, `has_prompts`, `has_completions` and the platform-vs-OpenTelemetry availability caveat.

## [1.13.3] - 2026-06-23

### Changed

- Authenticated Monte Carlo MCP requests now carry the toolkit's anonymous install id (`x-mcd-toolkit-install-id`) and version (`x-mcd-toolkit-version`) as HTTP headers, so the anonymous usage-beacon stream can be joined to authenticated MCP activity server-side — no new user- or account-level identifier is introduced. Headers are injected by whatever mechanism each editor supports: a runtime headers helper in Claude Code and Cortex Code (which also send a per-session `x-mcd-toolkit-session-id`), and install-time MCP registration for Cursor, Codex, Copilot, and OpenCode. Fail-open and honors `MC_AGENT_TOOLKIT_TELEMETRY_DISABLED=1`.

## [1.13.2] - 2026-06-19

### Changed

- Skills now route Monte Carlo MCP tool calls explicitly to the plugin-bundled server. Every skill that uses Monte Carlo MCP tools carries a standard routing rule directing the model to the fully-qualified `mcp__plugin_mc-agent-toolkit_monte-carlo-mcp__<tool>` names, so a separately-configured server of the same name can no longer shadow the bundled one. Soft (model-compliance) enforcement, with the canonical rule documented as the single source of truth in `.claude/rules/skills.md`.

### Fixed

- Replaced obsolete Monte Carlo tool-namespace examples (`mcp__monte_carlo__getAlerts`, `mcp__mc__search`) in the remediation skill's tool-discovery reference with current plugin-bundled, snake_case names.

## [1.13.1] - 2026-06-18

### Added

- `Toolkit Installed` telemetry beacon, fired once per machine+editor **per toolkit version** — on first install and after each version change — independent of skill usage, closing the gap where an install that never invoked a skill was invisible and adding version-adoption signal. Deduped by a per-editor `beacon_sent_version` marker. Wired across all six editor plugins (Claude Code, Cortex Code, Cursor, Codex, Copilot, OpenCode). Fail-open and non-blocking; honors `MC_AGENT_TOOLKIT_TELEMETRY_DISABLED=1` and the `MCD_TOOLKIT_BEACON_URL` override.

### Changed

- Shared hook logic now also covers telemetry: the canonical install beacon lives in `plugins/shared/telemetry/lib/` and is synced into each editor plugin by `./scripts/bump-version.sh --sync-only`, with a CI check enforcing it stays in sync — mirroring the existing `prevent/lib` convention.

## [1.13.0] - 2026-06-15

### Added

- Snowflake Cortex Code plugin (`plugins/cortex-code/`) — the 6th supported editor. Cortex Code wraps Claude Code, so it ships all 17 skills, the full prevent hook lifecycle, slash commands, and the Monte Carlo MCP server; install via `plugins/cortex-code/scripts/install.sh`.

### Changed

- Hardened the prevent impact-check gate: the pre-edit deny reason no longer contains a string that satisfies its own marker scanner, closing a latent self-unlock on harnesses that persist hook output back into the scanned transcript. Added `table_name` path sanitization for the `/tmp` cache, an unknown-transcript-format fail-closed guard, and tolerance for stray bytes when scanning Cortex's `.history.jsonl`. These shared-lib changes apply to all editor plugins.

## [1.12.1] - 2026-06-17

### Changed

- monitoring-advisor: align coverage and data-monitor-creation guidance with the internal Monte Carlo coverage agent — default to HIGH+MEDIUM scope (don't ask) with action-bias batching, "create a use case" handling, importance-score-is-not-business-criticality caveat, dedup + no-fabricated-credit-cost guidance, description(title)/notes(reasoning) split, a profiling-before-thresholds matrix, the field-monitor-requires-a-live-table-monitor prerequisite, and view fixed-schedule rule.

## [1.12.0] - 2026-05-20

### Added

- New `/manage-mac` skill: create, edit, validate, and import Monitors-as-Code YAML files — CLI-first: uses `montecarlo monitors compile` to validate and `apply` to deploy; falls back to MC MCP tools then manual validation
- Schema validation gates injected into `monitoring-advisor` and `tune-monitor` — agents now validate generated YAML against the published schema before presenting it to the user

## [1.11.1] - 2026-05-13

### Added

- Add `MC_PREVENT_HOOKS_DISABLED=1` env var to disable prevent hooks (block-edit, pre-commit, turn-end) for users who want the skills without the gating behavior.

### Changed

- Clarify telemetry disclosure in plugin README: explicit opt-out instructions and confirmation that no prompts/arguments/code are sent.
- Polish `plugin.json` metadata for Anthropic plugin directory submission (expanded description, `author.email`, `homepage`).
- Add `"category": "monitoring"` to the marketplace.json entry.

## [1.11.0] - 2026-05-07

### Added

- **Instrument Agent skill** — walks Monte Carlo Agent Observability customers through instrumenting a new Python AI agent for Monte Carlo. Detects AI libraries in the codebase, proposes the Monte Carlo OpenTelemetry SDK install with matching instrumentors, generates tracing setup tailored to serverless or long-running runtimes, suggests where workflow and task decorators belong, and verifies traces appear in Monte Carlo. Always asks before editing any file. Trigger by asking to "instrument my agent" or "set up Monte Carlo tracing".

## [1.10.5] - 2026-05-11

### Changed

- 1b2f114 fix(hooks): replace lib symlinks with real file copies (#82)
- 39c4dd6 AI-256: analyze-root-cause runs TSA first when an incident UUID is present (#79)

## [1.10.3] - 2026-05-06

### Changed

- Internal tracking only: MCP route updated to `/mcp/toolkit`.

## [1.10.2] - 2026-05-05

### Changed

- Correct `alert_assessment` output field descriptions in automated-triage skill: replace the stale "natural-language summary" reference with explicit `alert_description` (what happened) and `triage_summary` (scoring reasoning) fields, and clarify that `alert_description` is used in triage comments for untroubleshot alerts.

## [1.10.1] - 2026-04-30

### Changed

- Version sync with claude-code (welcome-hook removal). No functional changes here.

## [1.10.0] - 2026-04-28

### Added

- **`/mc-validate run` subcommand** — extends the Monte Carlo Prevent skill's validation workflow to actually execute the generated queries. `/mc-validate` alone still generates the validation SQL as before; `/mc-validate run` additionally builds the changed model into your dev database (`dbt build --select <model>`) and runs the validation queries through the Snowflake MCP, reporting per-query verdicts against each query's "What to look for" guidance.
- **Workflow 4 (sandbox build)** in the Prevent skill — parses `profiles.yml`, classifies the active database as personal/dev/shared-dev/prod/unknown, detects hard-coded `database:` kwargs in model `{{ config() }}` blocks, and runs `dbt build --select <model>`. Hard-stops against shared prod. Skipped automatically for YAML-only diffs.
- **Workflow 5 (execute validation)** in the Prevent skill — substitutes `<YOUR_DEV_DATABASE>` with the user-confirmed value, shows the full execution plan (including any literal prod databases referenced for parity checks), enforces read-only before execution, runs each query via Snowflake MCP, and produces ✅/⚠️/🔴 per-query verdicts plus a consolidated summary. All execution-time scratch output lives under `validation/run/`.
- **Five new sandbox helper scripts** under `skills/prevent/scripts/sandbox/`: `parse_profiles.py`, `classify_sandbox.py`, `detect_hardcoded_db.py`, `substitute_placeholders.py`, `readonly_check.py`. All independently tested and composable via CLI-emitted JSON.
- **Session markers** `MC_BUILD_RAN` and `MC_VALIDATE_RAN` for hook coordination across the new workflows.

### Changed

- Workflow 3 (generate validation queries) now always ends by offering `/mc-validate run` as the next step, regardless of how it was triggered.

## [1.9.0] - 2026-04-27

### Changed

- Slim the prevent skill: delegate Workflow 1 (table health check) to `monte-carlo-asset-health` and Workflow 6 (add monitor) to `monte-carlo-monitoring-advisor`. Remove the alert-triage workflow entirely.
- Renumber the impact-assessment and validation-query workflows to W2 and W3. Workflow numbers 4 and 5 are reserved for sandbox-build and execute-validation steps from the in-flight `mc-validate run` work.
- Single-line `description` field in `skills/prevent/SKILL.md` per the ≤250-char authoring rule.
- Drop alert-mutation tools (`updateAlert`, `setAlertOwner`, `createOrUpdateAlertComment`) from the prevent skill's MCP tool table — those belong to the incident-response peer skill.

### Fixed

- Clear the `MC_MONITOR_GAP` cache marker after the post-edit / pre-commit prompt has been delivered, so subsequent prompts don't re-nag for the same gap (Python hooks and OpenCode TS hooks).

## [1.8.2] - 2026-04-23

### Changed

- `monitoring-advisor`: hardened the `create_*_monitor_mac` guidance against the top failure modes seen in production over the last 7 days (70 events across 14 categories). Changes span `data-monitor-creation.md` (domain-uuid resolution, warehouse-UUID requirement, column-verification gate, enum discipline, table existence check) and the per-type references (`alert_condition` shape constraints in `data-validation-monitor`, metric-name and operator-enum corrections in `data-metric-monitor` / `data-custom-sql-monitor`, `change`-threshold documentation in `data-custom-sql-monitor`, datetime-type requirement for `aggregate_time_field`, arg-shape constraints in `data-table-monitor` and `data-validation-monitor`, predicate/field-type semantics in `data-validation-monitor`, `threshold_value` requirement clarification in `data-comparison-monitor`). See [PR #66](https://github.com/monte-carlo-data/mc-agent-toolkit/pull/66) for the full error → fix mapping.

### Fixed

- `scripts/bump-version.sh` normalizes drifted plugin versions. Before this release, claude-code was at 1.8.1 while codex/copilot/cursor/opencode were stuck at 1.7.0 because the script's sed only matched the claude-code version. The non-monotonic 1.7.0 → 1.8.2 jump on those four plugins is intentional — they caught up to the canonical version in this PR. Future bumps stay in sync automatically.

## [1.7.1] - 2026-04-17

### Changed

- feat(automated-triage): add mark_event_as_normal guidance and scope interactive triage by domain/audience

## [1.7.0] - 2026-04-17

### Changed

- Add tune-monitor skill for monitor noise reduction analysis

## [1.6.1] - 2026-04-16

### Changed

- Add connection-auth-rules skill for building Connection Auth Rules configs

## [1.6.0] - 2026-04-16

### Changed

- Consolidate `monitor-creation`, `agent-monitoring`, and `monitoring-advisor` into a single `monitoring-advisor` skill
- Add `data-monitor-creation.md` and `agent-monitor-creation.md` mid-level creation procedures
- Move per-type references with `data-`/`agent-` prefixes and distribute constraints
- Fix MCP tool names to snake_case across all skill docs
- Update trigger evals: direct monitor creation and agent monitoring now trigger this skill

## [1.5.0] - 2026-04-15

### Changed

- Add asset-health skill (#33)
- Add AI agent monitoring to monitoring-advisor skill (#48)

## [1.4.0] - 2026-04-14

### Changed

- c4842c4 fix: add missing skill registrations — READMEs, symlinks, and sync rules (#46)
- 647669a feat: add automated-triage skill (#40)
- 9477ae1 feat: add analyze-root-cause skill for incident investigation (#37)

## [1.3.0] - 2026-04-14

### Changed

- f46cdfb Add remediation skill for investigating and fixing data quality alerts (#39)
- c5dd6a5 feat: add agent-monitoring skill and plugin (AI-167) (#35)
- 9884442 feat: add storage cost analysis and performance diagnosis skills (#36)

## [1.2.0] - 2026-04-13

### Changed

- f40f262 fix: add --force flag to release script to skip branch check
- 9155214 fix: release script PR flow + awk multiline bug
- ad388c7 fix: register monitoring-advisor as plugin command + add trigger evals (#38)
- 9147282 K2-287: add monitoring-advisor skill (#34)
- 930a745 feat: add prevent trigger evals and shared eval runner (#29)
- cf09cb8 fix: add missing name field to generate-validation-notebook SKILL.md (#32)
- 44f85ab Add monitor-creation skill and wire into all editor plugins (#31)
- 6bc245d fix: correct marketplace add command to use repo name (#30)
- e8597c9 fix: improve release script post-run message (#28)

## [1.0.0] - 2026-04-06

### Changed

- Restructure from per-skill `mc-prevent` plugin to unified `mc-agent-toolkit` plugin
- Plugin directory is now `plugins/cursor/` (was `plugins/cursor/prevent/`)
- Hooks namespaced under `hooks/prevent/` for multi-skill support
- Shared hook logic moved to `plugins/shared/prevent/lib/`

### Upgrade instructions

Existing users should re-run the install script to pick up the new structure:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/monte-carlo-data/mc-agent-toolkit/main/plugins/cursor/scripts/install.sh)
```

---

_History prior to the unified toolkit restructure (when this was the `mc-prevent` plugin):_

## [1.0.0-prevent] - 2026-04-02

### Added

- Initial Cursor adapter for Monte Carlo Prevent
- Hook-based enforcement for dbt model edits (pre-edit gate, post-edit accumulator, turn-end validation prompt, commit gate)
- `/mc-validate` command for explicit validation
- Monte Carlo MCP server wiring
- Shared platform-agnostic hook logic via `hooks/prevent/lib/`
