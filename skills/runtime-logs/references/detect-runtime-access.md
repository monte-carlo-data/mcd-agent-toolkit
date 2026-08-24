# Detecting runtime access

Work down this list before fetching anything. Detect what is actually present — do not infer from
the stack the customer *probably* runs.

Order matters: an MCP server is the best surface (structured, scoped, already authorized), a CLI is
next, and a bare config file only tells you a tool is installed, not that its credentials work.

## 1. MCP servers in this session

Cheapest and highest-signal check: look at the tools available to you right now.

| Tool prefix visible | Provider | Playbook |
|---|---|---|
| `mcp__datadog__*` (e.g. `search_datadog_logs`) | Datadog | `datadog.md` |
| `mcp__*aws*`, `mcp__*cloudwatch*` | CloudWatch | `cloudwatch.md` |
| `mcp__*databricks*` | Databricks | `databricks.md` |
| `mcp__*splunk*`, `mcp__*grafana*`, `mcp__*loki*` | out of POC scope | — |

A configured MCP server is authorization the user already granted. Prefer it over shelling out.

## 2. CLIs on PATH, with working credentials

Installed is not the same as authorized. Check both:

```bash
command -v aws && aws sts get-caller-identity 2>&1 | head -5
command -v databricks && databricks current-user me 2>&1 | head -5
command -v gcloud && gcloud auth list 2>&1 | head -5
```

`aws sts get-caller-identity` failing on an expired SSO session is the common case. Report it as
"AWS CLI present, credentials expired — run `aws sso login`" rather than as no access.

Note which profile you are on and whether it is the right account. `AWS_PROFILE` pointing at a dev
account will silently return an empty result set for a prod incident — an empty result is
indistinguishable from "no errors found" unless you checked.

## 3. Workspace configuration

Weaker evidence, but it tells you which provider to try and which names to use.

| Signal | Means |
|---|---|
| `provider "datadog"` in `*.tf` | Datadog is the log destination |
| `aws_cloudwatch_log_group` in `*.tf` | CloudWatch, and the resource block names the log group |
| `~/.databrickscfg`, `DATABRICKS_HOST` | Databricks workspace configured |
| `.mcp.json` / `~/.claude.json` | MCP servers configured but perhaps not loaded this session |
| `profiles.yml`, `dbt_project.yml` | dbt target, useful for matching the failing model to its run |
| `airflow.cfg`, `dags/` | Self-hosted Airflow — out of POC scope, but its remote logging config names the real log store |

Terraform is the most useful of these: it frequently contains the exact log group name, which saves
a guess in the CloudWatch playbook.

## 4. Report before proceeding

Say what you found and what you did not. Then either proceed to the playbook or stop.

```
Detected: AWS CLI (profile data-prod, valid), Datadog MCP server.
Not found: Databricks CLI, gcloud.
Proceeding with CloudWatch for the MWAA task log.
```

If nothing is found, stop and say so. Give the user the `run_url` from Step 1 so they can open the
run in their orchestrator's UI, and name the single most likely thing to configure based on the
`source` field — Datadog MCP for `source: airflow` in a Datadog shop, the AWS CLI for MWAA.
