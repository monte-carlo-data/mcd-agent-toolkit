# Skills

Skills are platform-agnostic instruction sets that tell an AI coding agent what to do. Each skill lives in its own directory with a `SKILL.md` definition and optional supporting files (scripts, references, assets). Skills can be used standalone with any MCP-capable editor, or bundled into the [mc-agent-toolkit plugin](../plugins/) for a richer experience with hooks and enforcement.

## Available Skills

| Skill | Description |
|---|---|
| **[Incident Response](incident-response/)** | Orchestrates incident response — triage alerts, investigate root causes, remediate issues, and add monitoring to prevent recurrence. Sequences existing skills into a guided workflow. |
| **[Asset Health](asset-health/)** | Checks the health of a data table — surfaces last activity, alerts, monitoring coverage, importance, and upstream dependency health from Monte Carlo. |
| **[Monitoring Advisor](monitoring-advisor/)** | Analyzes data coverage, creates monitors for warehouse tables and AI agents — covers coverage gaps, use-case analysis, data monitor creation, and agent observability. |
| **[Proactive Monitoring](proactive-monitoring/)** | Guides users from coverage analysis to monitor creation. Sequences asset-health assessment, gap identification via monitoring-advisor, and monitor creation into a guided workflow. |
| **[Prevent](prevent/)** | Edit-lifecycle safety net for dbt/SQL: runs change impact assessment before edits, generates validation queries after, and delegates health context (asset-health) and monitor generation (monitoring-advisor). |
| **[Generate Validation Notebook](generate-validation-notebook/)** | Generates SQL validation notebooks for dbt model changes, with targeted queries comparing baseline and development data. |
| **[Push Ingestion](push-ingestion/)** | Generates warehouse-specific collection scripts for pushing metadata, lineage, and query logs to Monte Carlo. |
| **[Automated Triage](automated-triage/)** | Guides you through designing, testing, and deploying automated alert triage for your Monte Carlo environment — covering the triage stages, customisation options, and a working example to start from. |
| **[Analyze Root Cause](analyze-root-cause/)** | Investigates data incidents — freshness, volume, schema, ETL, query changes — with systematic root cause analysis using lineage and observability data. |
| **[Troubleshoot Agent Traces](troubleshoot-agent-traces/)** | Investigates AI-agent alerts (evaluation, metric, trajectory, validation) and agent traces — kicks off the trace troubleshooting agent and guides a backend-aware manual investigation. |
| **[Storage Cost Analysis](storage-cost-analysis/)** | Identifies storage waste patterns (unread, zombie, dead-end tables) and recommends safe cleanup with cost estimates. |
| **[Performance Diagnosis](performance-diagnosis/)** | Diagnoses slow pipelines and expensive queries across Airflow, dbt, and Databricks with tiered investigation. |
| **[Remediation](remediation/)** | Investigates and remediates data quality alerts — runs TSA root cause analysis, discovers available tools, executes fixes (or escalates), and documents the resolution. |
| **[Manage MaC](manage-mac/)** | Create, edit, validate, and import Monitors-as-Code YAML files — authors new monitors from scratch, modifies existing files, validates against the published JSON Schema, and exports live monitors to YAML. |
| **[Tune Monitor](tune-monitor/)** | Analyzes a Monte Carlo metric monitor's alert history and recommends configuration changes to reduce noise — sensitivity, WHERE conditions, segment exclusions, schedule, and aggregation. |
| **[Connection Auth Rules](connection-auth-rules/)** | Build a Connection Auth Rules configuration for a Monte Carlo connection type. Fetches live connector schemas and transform steps from the apollo-agent repo. |
| **[Instrument Agent](instrument-agent/)** | Instruments a Python AI agent for Monte Carlo Agent Observability — detects AI libraries, installs the Monte Carlo OpenTelemetry SDK, sets up tracing, and verifies traces in Monte Carlo. Asks before editing. |
| **[Compare Trace](compare-trace/)** | A/B compares two Monte Carlo agent traces by ID — runs graph-path, latency/token, and tool-call diffs plus LLM-based semantic and entity-overlap evals over the final answers, and opens an HTML report. |

## Standalone Installation

Skills can be installed without the plugin via skill registries:

```bash
npx skills add monte-carlo-data/mc-agent-toolkit --skill prevent
```

Or by copying directly:

```bash
cp -r skills/prevent ~/.claude/skills/prevent
```

See individual skill READMEs for prerequisites and setup details.
