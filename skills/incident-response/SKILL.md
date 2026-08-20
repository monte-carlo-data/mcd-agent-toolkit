---
name: monte-carlo-incident-response
description: Orchestrate incident response — triage, root cause, remediate, prevent recurrence. USE WHEN active alerts, data broken, stale, pipeline failure, or investigate and fix a data incident.
when_to_use: |
  Invoke when the user has an active data incident to handle — alerts firing, a table looks stale or broken, a pipeline failed, or they want to investigate root cause on a named table.
  Example triggers: "my orders table is stale, figure out why", "I have an unresolved alert on X, help me investigate", "alerts are firing — what should I do?", "investigate the most critical alert".

  Covers the full workflow: triage (classify/prioritize alerts) → root cause analysis (lineage, freshness history, query changes) → remediation → prevent recurrence.

  Do NOT invoke for coverage or "what should I monitor" requests (use proactive-monitoring instead) or for creating a specific monitor on a known table (use monitoring-advisor).
bucket: Agent-routing
version: 1.0.0
---

# Monte Carlo Incident Response Workflow

This workflow orchestrates the full lifecycle of a data incident by sequencing
existing Monte Carlo skills. It does not contain investigation or remediation
logic itself — each step loads the relevant skill's SKILL.md which has the
actual instructions.

> **Monte Carlo tool routing (required):** Always call Monte Carlo MCP tools through this plugin's
> bundled server, whose fully-qualified tool names are
> `mcp__plugin_mc-agent-toolkit_monte-carlo-mcp__<tool>` (e.g.
> `mcp__plugin_mc-agent-toolkit_monte-carlo-mcp__get_alerts`). Bare tool names used in this skill
> (`get_alerts`, `search`, `get_table`, …) refer to that bundled server. If the session also has a
> separately-configured `monte-carlo-mcp` server, do **not** route to it — it may point at a
> different endpoint or credentials.

## When to activate this workflow

Activate when:

- Context detection routes here (active alerts detected + incident intent)
- User invokes `/mc-incident-response`
- User asks to "respond to an incident", "handle this alert", "triage and fix"
- User describes a data quality problem: "data is broken", "table is stale", "alert firing"

## When NOT to activate this workflow

- User wants to create monitors or check coverage without an active incident — use proactive monitoring workflow
- User is editing a dbt model — defer to `prevent` skill (auto-activates via hooks)
- User wants to check table health without an incident context — use `asset-health` directly
- A skill is already active and handling the user's request

---

## Workflow Steps

```
Step 1 (conditional): Triage — when user has multiple/unknown alerts
Step 2: Root Cause Analysis — the core investigation
Step 3: Remediation — fix or escalate
Step 4 (optional): Prevent Recurrence — add monitoring
```

### Determine entry point

Before starting, determine which step to enter based on the user's context:

- **User has no specific alert** ("I have alerts firing", "what's going on?") → Start at **Step 1: Triage**
- **User has a specific alert ID or table** ("alert ABC-123", "stg_payments is stale") → Skip to **Step 2: Root Cause Analysis**
- **User knows the root cause** ("the ETL job failed, help me fix it") → Skip to **Step 3: Remediation**
- **Alert is an agent-monitor alert** (`alert_types` starting with "Agent ", or the user's issue is about an AI agent) → for the investigation, read `../troubleshoot-agent-traces/SKILL.md` instead of `../analyze-root-cause/SKILL.md`; the remediation and monitoring steps still apply
- **Ambiguous** → Ask: "Do you have a specific alert or table you want to investigate, or should I check your recent alerts first?"

---

### Step 1: Triage (conditional)

**Skill:** Read and follow `../automated-triage/SKILL.md`

**Goal:** Fetch recent alerts, score them by confidence and impact, identify which ones need investigation.

**When to run:** Only when the user doesn't already have a specific alert or incident to investigate. This step helps narrow down "I have alerts" into "these specific alerts need attention."

**Scope MCP calls tightly.** On large accounts, broad queries return hundreds of results, overflow the tool-result token limit, spill to disk, and force chunk reads — burning user tokens and exhausting the turn budget. Minimum scoping for tools this workflow touches:

- `get_alerts` → time filter (`created_after`, default last 7 days) + at least one of `warehouse`, `table_names`, `severity`
- `search` → needed to resolve a table name to its MCON (`get_table` requires MCON). Always pass `limit` (e.g. 5), the table name as `query`, and filter by `warehouse_uuid` or `database`/`schema`. `warehouse_types` alone is too broad. If multiple matches return: (1) auto-pick the match whose `warehouse_display_name` matches the user's named warehouse — do NOT stop to ask; (2) failing that, prefer the `is_key_asset: true` match; (3) only ask the user when none of these resolve it
- `get_monitors` → filter by `mcons` or `warehouse_uuid`

If scope is missing, ask the user before calling: "Which warehouse?", "How far back — today, this week?", "Any specific severity?".

**Transition to Step 2:** Once high-priority alert(s) are identified, tell the user:

> "I've identified [N] high-priority alerts. Let me investigate the root cause of [specific alert/table]. Moving to root cause analysis."

Then proceed to Step 2 with the identified alert context.

---

### Step 2: Root Cause Analysis

**Skill:** Read and follow `../analyze-root-cause/SKILL.md`

**Goal:** Investigate why the issue occurred — trace lineage, check ETL changes, analyze query modifications, profile data.

**This is the core step.** Most workflow entries start here.

**Investigate linearly — do not re-call tools.** Walk through the investigation once: (1) find the asset, (2) fetch its alerts and health context, (3) check lineage when tables exist, (4) check recent queries/ETL. Call each tool at most once per asset. If a tool result is insufficient, move to the next signal rather than re-calling with different params — burning turns on redundant calls exhausts the budget before the root cause is reached. The one intentional exception is `fetch_logs`: follow the analyze-root-cause skill's unfiltered-first call with a narrower regex or severity call when the first page is noisy.

**Transition to Step 3:** When the root cause is identified (or the investigation reaches its limit), summarize findings and tell the user:

> "Root cause identified: [summary]. Would you like me to help remediate this, or is the investigation sufficient?"

If the user wants to proceed, move to Step 3. If they say "that's enough", stop.

---

### Step 3: Remediation

**Skill:** Read and follow `../remediation/SKILL.md`

**Goal:** Fix the issue using available tools, or escalate with full context if the fix requires actions outside the agent's capability.

**Transition to Step 4:** After remediation is complete (fix applied or escalation documented), offer prevention:

> "The issue has been [fixed/escalated]. The root cause was [X]. Want me to help add a monitor to detect this type of issue earlier next time?"

If the user says yes, move to Step 4. If no, the workflow is complete.

---

### Step 4: Prevent Recurrence (optional)

**Skill:** Read and follow `../monitoring-advisor/SKILL.md`

When loading monitoring-advisor for this step, frame the request as direct monitor creation — not coverage analysis. The user already knows what they want to monitor (the thing that just broke). Example framing:

> "Based on the incident, I recommend adding a [freshness/volume/validation] monitor on [table]. Let me create the monitor configuration."

**Goal:** Add or update a monitor to catch this class of issue in the future.

**Do not force this step.** It is optional — offer it after remediation, and respect if the user declines.

---

## Orchestration Rules

- **Users can enter at any step.** The entry point section above determines where to start.
- **Each step loads the actual skill's SKILL.md** via relative path. This workflow does not replicate skill logic — it sequences it.
- **Context carries forward** through conversation naturally. Alert IDs, table names, root cause findings from earlier steps are available to later steps without explicit state passing.
- **No state tracking or hooks.** This is purely prompt-driven sequencing.
- **User can exit anytime.** If they say "that's enough" or "stop", respect it immediately.
- **Do not skip back.** The workflow moves forward. If the user wants to re-investigate after remediation, they can start a new workflow or invoke a skill directly.
