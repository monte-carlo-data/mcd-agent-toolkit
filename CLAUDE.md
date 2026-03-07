# Monte Carlo AI Editor Plugin — Stage 1: Packaging

## Objective
Prepare the plugin for internal launch at Monte Carlo. Three deliverables:
1. `README.md` — manual setup instructions for a technical MC data engineer
2. Repo polish — clean structure, no dev artifacts, ready for internal eyes
3. Launch artifacts — Slack message + internal setup guide

Do not modify `skills/monte-carlo/SKILL.md` in this session.

---

## Context

### What has been built
- `skills/monte-carlo/SKILL.md` — the core skill file, fully tested
- `skills/monte-carlo/TROUBLESHOOTING.md` — common setup and runtime issues
- `analysis/` — PR analysis and test results (internal, keep but not featured)
- `demo/scenario.md` — demo script (internal reference)

### Target user
MC data engineers who use Claude Code, Cursor, or other AI editors with
MCP support. Technical users comfortable with terminal and config files.
They are NOT familiar with the Monte Carlo plugin — this is their first time
setting it up.

### Target stack
dbt + Snowflake + Airflow (MC's internal data stack)

### Repo visibility
Private. Internal launch only — do not add any public-facing language.

---

## Deliverable 1: README.md

Write `README.md` in the repo root. It must be clear enough that a data
engineer can go from zero to verified working in under 10 minutes.

### Structure

```
# Monte Carlo AI Editor Plugin

## What this does
[2-3 sentences: what the plugin is, what it does for a data engineer,
which editors it works with]

## Prerequisites
- Claude Code, Cursor, or VS Code with MCP support
- Node.js (LTS) + npm installed
- Monte Carlo account with Editor role or above
- MC CLI installed (for monitor deployment)

## Setup

### Step 1 — Create an MCP server key
[Instructions: MC UI → Settings → API Keys → Add → MCP Server type]
[Note: MCP keys are separate from standard API keys]

### Step 2 — Install the SKILL.md
[Single curl command to install the skill to ~/.claude/skills/monte-carlo/]

### Step 3 — Configure your MCP server
[Show the exact JSON snippet for Claude Code / Cursor / VS Code]
[Use x-mcd-id and x-mcd-token header format]
[MCP endpoint: https://integrations.getmontecarlo.com/mcp/]

### Step 4 — Verify the connection
[One test prompt to paste into Claude Code to confirm everything works]

## How to use it
[Brief description of the 4 workflows — what triggers them, what they do]
[Emphasize: do not ask for it — it activates automatically]

## Troubleshooting
[Link to TROUBLESHOOTING.md]
```

### Requirements for the README
- Every command must be copy-pasteable — no placeholders left unfilled except
  `<KEY_ID>` and `<KEY_SECRET>` which are user-specific
- The SKILL.md install step should be a single curl or cp command, not
  manual file creation
- Keep it under 150 lines — data engineers won't read a long README
- Tone: direct and technical, no marketing language
- Do not mention the hackathon, demo video, or internal project history

---

## Deliverable 2: Repo Polish

Review the repo and make the following changes:

### Folder structure — confirm or create
```
monte-carlo-claude-plugin/
├── CLAUDE.md                          # current session brief (keep)
├── README.md                          # create this session
├── skills/
│   └── monte-carlo/
│       ├── SKILL.md                   # core deliverable
│       └── TROUBLESHOOTING.md         # already exists
├── analysis/                          # internal — keep but add .gitkeep
│   ├── session_a_pr_analysis.md
│   └── session_b_test_results.md
├── demo/
│   └── scenario.md                    # internal reference
└── .mcp.json.example                  # create this session (see below)
```

### Create `.mcp.json.example`
A ready-to-use MCP config template that engineers can copy directly:
```json
{
  "mcpServers": {
    "monte-carlo": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://integrations.getmontecarlo.com/mcp/",
        "--header",
        "x-mcd-id: <KEY_ID>",
        "--header",
        "x-mcd-token: <KEY_SECRET>"
      ]
    }
  }
}
```

### Create `.gitignore` if not present
```
.env
*.key
.mcp.json         # actual config with real keys — never commit
node_modules/
.DS_Store
```

### Clean up
- Remove any temporary files, scratch notes, or dev artifacts not listed
  in the target folder structure above
- Ensure all markdown files have consistent heading styles
- Do not delete `analysis/` — it is useful internal history

---

## Deliverable 3: Launch Artifacts

### 3a — Slack message
Save as `launch/slack_message.md`

Write a Slack message for the MC data engineering team channel.
Tone: casual, collegial, internally focused. Not a press release.

It should include:
- One sentence on what this is
- Two concrete examples of what it does (pick from the test results:
  e.g. filter change on client_hub_master surfacing 315 downstream tables,
  or the timeseries_detector_routing rename being redirected to a safe
  transition strategy)
- Link to the repo and README for setup
- An ask: try it on a real model and share feedback in a thread

Keep it under 150 words. No headers, no bullet lists — write it as you
would actually send it in Slack.

### 3b — Internal setup guide
Save as `launch/setup_guide.md`

A slightly more detailed companion to the README, tailored specifically
for MC's internal stack. Differences from the README:
- References MC's actual dbt repo path conventions
- Includes a suggested first test: open a model from the
  `criticality_score` or `timeseries` domain (highest-impact models
  from PR analysis) and reference it in Claude Code
- Includes a note on the monitors workflow: this is a new practice for
  the team — Workflow 2 will offer to generate monitor YAML, which can
  then be applied with `montecarlo monitors apply`
- Includes a feedback section: where to share issues or suggestions
  (Slack channel or GitHub issues on the private repo)

Keep it under 200 lines.

---

## What NOT to do
- Do not modify SKILL.md
- Do not make the repo public
- Do not add any customer-facing or external-launch language
- Do not create a formal changelog or versioning system yet —
  that comes when we launch externally
