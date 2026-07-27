---
name: monte-carlo-reinforce-agent
description: |
  Reinforces an AI agent by turning Monte Carlo's reinforcement loop diagnosis into code fixes.
  Reads the daily reinforcement loop report for an agent's workflows, ranks the diagnosed issues, proposes
  what to fix, and — with the user's approval at each step — opens a pull request. Activates on
  "fix my agent", "improve my agent's health", "reinforce my agent", "what should I fix in my
  agent". Not for investigating a specific agent alert or trace (monte-carlo-troubleshoot-agent-traces),
  creating agent monitors (monte-carlo-monitoring-advisor), or instrumenting a new agent
  (monte-carlo-instrument-agent).
when_to_use: |
  Use when the user wants to act on an AI agent's diagnosed health problems and land fixes:
  "fix my agent", "reinforce my agent", "improve my agent's health", "what should I fix in
  <agent>", "open a PR for my agent's top issue". Expects the user to name the agent; if they
  don't, it lists available agents and asks. The flow is user-gated: it surfaces the reinforcement
  loop diagnosis and asks which workflow to dig into and which issue to fix before writing any code.
  Do NOT use for:
  - investigating a single agent alert or trace (eval drop, latency spike, one trace id) —
    use monte-carlo-troubleshoot-agent-traces
  - creating or tuning agent monitors — use monte-carlo-monitoring-advisor / tune-monitor
  - instrumenting a brand-new agent to emit traces — use monte-carlo-instrument-agent
bucket: Incident Response
---

# Monte Carlo Reinforce Agent Skill

This skill turns Monte Carlo's **reinforcement loop diagnosis** into landed code fixes. Monte Carlo runs a
daily reinforcement loop pipeline that analyzes an agent's traces and produces, per workflow, a report of
diagnosed issues — each with supporting evidence (trace deep-links, verifier checks) and recommended
fixes. This skill reads that diagnosis, ranks it, proposes what to fix, and follows through with a
pull request — pausing for the user's decision at each fan-out point.

> **Monte Carlo tool routing (required):** Always call Monte Carlo MCP tools through this plugin's
> bundled server, whose fully-qualified tool names are
> `mcp__plugin_mc-agent-toolkit_monte-carlo-mcp__<tool>` (e.g.
> `mcp__plugin_mc-agent-toolkit_monte-carlo-mcp__get_reinforcement_loop_report`). Bare tool names
> used in this skill (`get_agent_metadata`, `get_reinforcement_loop_summaries`,
> `get_reinforcement_loop_report`) refer to that bundled server. If the session also has a
> separately-configured `monte-carlo-mcp` server, do
> **not** route to it — it may point at a different endpoint or credentials.

## When to activate this skill

Activate when the user:

- Wants to fix or improve an AI agent based on its Monte Carlo reinforcement loop ("fix my agent",
  "reinforce my agent", "improve my agent's health").
- Asks what to fix in an agent ("what are my agent's top issues", "what should I fix in <agent>").
- Wants a PR that addresses an agent's diagnosed problems.

## When NOT to activate this skill

- Investigating one agent **alert** or **trace** (eval-score drop, latency/token spike, a specific
  trace id) → use `monte-carlo-troubleshoot-agent-traces`. That skill investigates a single
  incident; this one acts on the standing reinforcement loop diagnosis across a workflow and writes code.
- Creating or tuning agent **monitors** → `monte-carlo-monitoring-advisor` / `tune-monitor`.
- **Instrumenting** a new agent to emit traces → `monte-carlo-instrument-agent`.

## Prerequisites

- Monte Carlo MCP server configured and authenticated, with agent observability enabled for the
  account. If `get_reinforcement_loop_summaries` reports that the reinforcement loop is not enabled,
  tell the user the account isn't enrolled in the reinforcement loop pipeline and stop.
- A local checkout of the agent's codebase (this skill writes code and opens a PR against it). If
  the working directory isn't the agent's repo, ask the user for the path before Step 4.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `get_agent_metadata` | List AI agents with their canonical `agentName`, friendly `displayName`, `traceTableMcon`, source type, and warehouse. Used to **resolve the agent the user named** to the exact `agent_name` + `trace_table_mcon` the reinforcement loop tools require (match on canonical name *or* display name; disambiguate when several match) |
| `get_reinforcement_loop_summaries` | Per-workflow health rollups for one agent — `issue_count` + worst-severity `health` + `detection_time` per workflow. The cheap triage layer; rank on this before expanding anything |
| `get_reinforcement_loop_report` | The latest reinforcement loop report for **one** workflow, as a single actionable markdown brief — diagnosed issues with evidence (trace deep-links), recommended fixes, any existing Linear ticket, and any proposed monitor. The expensive call; fetch only for workflows the user chose |

## Workflow

The flow is **user-gated at every fan-out** — never expand or act autonomously. The number of
`get_reinforcement_loop_report` calls is bounded by what the user picks, not by how many workflows exist.

### Step 1: Resolve the agent

The user triggers this skill **with a specific agent in mind** — expect them to name it ("reinforce
the chat agent", "fix `ai-agent`"). This step's job is to turn that name into the exact identifiers
the reinforcement loop tools need.

Call `get_agent_metadata` and match the user's name against each entry's `agentName` **and**
`displayName` (users often use the friendly display name, not the canonical one). Use the matched
entry's `agentName` + `traceTableMcon` **together** for every later call — the trace table
disambiguates agents that share a name.

- **No agent named:** list the available agents (canonical name + display name) and ask which one.
- **Ambiguous match** (same name across trace tables, or a substring matching several): list the
  candidates with their trace tables / warehouses and ask the user to pick — never guess the
  `trace_table_mcon`.
- **No match:** tell the user and show the available agents.

### Step 2: Triage the workflows (reinforcement loop overview)

Call `get_reinforcement_loop_summaries(agent_name, trace_table_mcon)` — one cheap call covering every
workflow. Then:

- Drop workflows with `issue_count == 0` (clean reports).
- Rank the rest by `health` severity (CRITICAL → HIGH → MEDIUM → LOW), then by `issue_count`.
- Present the ranked list as a short table: workflow · health · issue count · last diagnosed.

**Gate — ask the user which workflow(s) to dig into.** Do NOT call `get_reinforcement_loop_report` for every
workflow. Default the suggestion to the single worst workflow; let the user pick one or a few. Only
the chosen workflows get expanded in Step 3.

### Step 3: Deep-dive the chosen workflow(s)

For each workflow the user chose, call `get_reinforcement_loop_report(agent_name, workflow_name, trace_table_mcon)`.
The response is a single markdown brief: a report header (health, coverage, window, and what changed
since the last report) followed by one section per issue. Each issue section is self-contained — the
summary, the evidence with clickable trace deep-links, and the recommended actions — so identifying
the **top issues** happens in-context from this one call. No per-issue tool calls are needed.

From the brief, pick the top issues by severity/priority. Prefer issues whose evidence includes a
concrete node/tool and code-referable checks (those are the most directly fixable in code).

### Step 4: Propose what to fix

Summarize the top issues for the user in plain language — for each: what's wrong (the issue
summary), the evidence, and the recommended fix. Call out signals that change the action:

- **Existing Linear ticket** on an issue → the problem is already tracked; plan to reference/update
  that ticket, not open a duplicate.
- **Proposed monitor** on an issue (`proposed_monitor_yaml` present in the brief) → the recommended
  remediation may be a monitor rather than a code change; surface that as an option.
- Issues whose root cause is **external** (e.g. client-cancellation, upstream timeouts) may not be
  code-fixable in this repo — say so rather than forcing a change.

**Gate — ask the user which issue(s) to fix now.** Fix one issue at a time. Confirm the target
before writing any code.

### Step 5: Follow through with a PR

For the chosen issue:

1. Use the issue's brief (its evidence and recommended actions) as the specification — it already
   contains the failing traces, the implicated node/tool, and the concrete steps to take. Locate the
   relevant code in the user's repo and implement the smallest change that addresses the recommended
   action.
2. Follow the repo's conventions (branch off the default branch, match surrounding code and commit
   style). One issue → one focused PR.
3. In the PR description, link the diagnosed issue and its evidence (trace deep-links from the brief)
   so a reviewer can trace the fix back to the signal. If the issue has an existing Linear ticket,
   reference it instead of describing the problem from scratch.

**Gate — confirm before pushing / opening the PR.** Show the diff and the PR body, and only push
after the user approves. Then, if the user wants, return to Step 4 for the next issue (or Step 2 for
the next workflow).

## Important rules

- **Never fan out eagerly.** `get_reinforcement_loop_summaries` is the triage layer; call `get_reinforcement_loop_report`
  only for user-chosen workflows. Expanding every workflow wastes context on reports no one will act
  on.
- **One issue → one PR.** Keep changes focused and reviewable; iterate rather than batch.
- **Human checkpoint before code and before push.** This skill writes and proposes code; it never
  commits or opens a PR without explicit approval.
- **Don't re-file tracked issues.** If an issue already carries a Linear ticket, reference/update it.
- **Read-only diagnosis.** The three MCP tools here are read-only and consume no Monte Carlo credits;
  the only side effects are the git branch/PR you create with the user's approval.
