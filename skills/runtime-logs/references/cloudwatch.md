# CloudWatch — MWAA (Airflow) and ECS

Covers `source: airflow` on MWAA, and ECS tasks running dbt or a custom job.

Everything here is read-only. Scope every call with `--start-time`/`--end-time` from the run window.

## Time format

CloudWatch wants epoch milliseconds; Monte Carlo returns ISO 8601. Convert, and pad the window —
the runtime failure precedes the run record.

```bash
# macOS
START=$(( $(date -j -f "%Y-%m-%dT%H:%M:%S" "2026-08-24T02:10:00" +%s) * 1000 ))
# GNU
START=$(( $(date -d "2026-08-24T02:10:00Z" +%s) * 1000 ))
```

## MWAA / Airflow task logs

MWAA publishes to log groups named after the environment:

```
airflow-<environment>-Task
airflow-<environment>-Scheduler
airflow-<environment>-Worker
```

Find the environment when you do not know it:

```bash
aws mwaa list-environments
aws logs describe-log-groups --log-group-name-prefix airflow- --query 'logGroups[].logGroupName'
```

Task log streams embed the run identity from Step 1 — `dag_id`, `task_id`, `run_id`, and the
attempt number:

```
<dag_id>/<task_id>/<run_id>/<attempt>.log
```

So the stream prefix is a direct lookup, not a search:

```bash
aws logs describe-log-streams \
  --log-group-name "airflow-prod-Task" \
  --log-stream-name-prefix "nightly_core/dbt_run/scheduled__2026-08-24T02:00:00+00:00/"

aws logs get-log-events \
  --log-group-name "airflow-prod-Task" \
  --log-stream-name "nightly_core/dbt_run/scheduled__2026-08-24T02:00:00+00:00/2.log" \
  --start-time "$START" --end-time "$END" --limit 200
```

Note the attempt number: `attempt_number` from `get_airflow_issues`. Attempt 1 failing and attempt
2 succeeding is a different story from both failing, and the stream name is where you see it.

**No matching stream is itself the finding** — the task never ran. Check the Scheduler log group
for the same `dag_id` in the window; that is where import errors, pool exhaustion, and
worker-unavailable failures land.

## ECS task logs

When the failing unit is an ECS task (the YET-2353 motivating case: dbt never ran because the task
could not read its Snowflake credential), work backwards from the cluster:

```bash
aws ecs list-clusters
aws ecs list-tasks --cluster <cluster> --desired-status STOPPED
aws ecs describe-tasks --cluster <cluster> --tasks <task-arn> \
  --query 'tasks[].{stopped:stoppedReason,code:stopCode,exit:containers[].exitCode,started:startedAt}'
```

`stoppedReason` frequently *is* the root cause and costs one call — resource-not-found on a secret,
image pull failure, OOM. Check it before pulling logs.

The log group comes from the task definition:

```bash
aws ecs describe-task-definition --task-definition <family:revision> \
  --query 'taskDefinition.containerDefinitions[].logConfiguration.options'
```

Then the stream is `<prefix>/<container>/<task-id>` where task-id is the last segment of the ARN:

```bash
aws logs get-log-events \
  --log-group-name "/ecs/dbt-runner" \
  --log-stream-name "ecs/dbt/1a2b3c4d5e6f7890" \
  --start-time "$START" --end-time "$END" --limit 200
```

## Searching when you lack the stream

`filter-log-events` searches a whole group. Slower and pricier — always bounded, always with a
pattern:

```bash
aws logs filter-log-events \
  --log-group-name "/ecs/dbt-runner" \
  --start-time "$START" --end-time "$END" \
  --filter-pattern '?ERROR ?Error ?error ?Traceback ?FATAL' \
  --max-items 100
```

## Reading the result

Common causes and what they look like:

| Cause | Signature |
|---|---|
| Secrets Manager denial | `AccessDeniedException` / `ResourceNotFoundException` naming a secret ARN, before any application output |
| Task never started | Empty log stream, or no stream at all; `stoppedReason` explains it |
| OOM | `exitCode: 137`, `OutOfMemoryError`, abrupt truncation mid-output |
| Warehouse credential expiry | Snowflake/BigQuery auth error early in the run |
| Upstream cascade | Task ran fine but produced nothing — check `upstream_failed_task_id` from `get_airflow_issues` instead |

If the earliest error is an auth or permission failure that precedes any application logging, that
is the root cause. Do not keep reading for a data-layer explanation that will not be there.
