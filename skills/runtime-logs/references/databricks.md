# Databricks

Covers `source: databricks` from `get_etl_unified_issues`.

Databricks is the case where the Monte Carlo pointer maps most cleanly: `run_id` from the run
record is the Databricks run id, so no search is needed.

## The run record

One call resolves the failure, the cluster, and the log destination:

```bash
databricks jobs get-run <run_id> --output json
```

Read from it:

| Field | Use |
|---|---|
| `state.result_state`, `state.state_message` | Frequently the whole answer — a library install failure or a driver crash is stated here |
| `tasks[].run_id` | Per-task run ids; a multi-task job fails at one of them |
| `cluster_instance.cluster_id` | The cluster to pull driver logs from |
| `cluster_spec.new_cluster.cluster_log_conf` | Where logs were shipped: `dbfs.destination` or `s3.destination` |
| `run_page_url` | Matches `run_url` from Monte Carlo — hand this to the user if access fails |

Per-task output, including the error and truncated stack trace:

```bash
databricks jobs get-run-output <task_run_id> --output json
```

For a notebook task the traceback lands in `error` and `error_trace`. For a dbt task, `dbt_output`
carries the artifacts.

## Driver and executor logs

`get-run-output` truncates. The full driver log is where OOMs and JVM-level failures live.

If `cluster_log_conf` is set, logs are shipped to a durable path:

```bash
# DBFS
databricks fs ls "dbfs:/cluster-logs/<cluster_id>/driver"
databricks fs cat "dbfs:/cluster-logs/<cluster_id>/driver/stderr" | tail -200

# S3 — needs AWS access; see cloudwatch.md for credential checks
aws s3 ls "s3://<bucket>/cluster-logs/<cluster_id>/driver/"
```

`stderr` before `stdout` — Spark stack traces and OOM kills go to stderr.

If `cluster_log_conf` is absent, logs live only in the cluster UI and expire with the cluster.
Say so and hand back `run_page_url`; that is a real limitation, not a retrieval failure.

## Cluster events

For a job that died without producing application logs, the cluster event log explains it — spot
instance reclaimed, autoscaling failure, init script error:

```bash
databricks clusters events <cluster_id> --output json | head -60
```

## Reading the result

| Cause | Signature |
|---|---|
| Driver OOM | `state_message` mentions driver, or stderr ends with `java.lang.OutOfMemoryError` |
| Spot reclamation | Cluster event `SPOT_INSTANCE_TERMINATION`; the run dies mid-stage with no application error |
| Init script failure | Cluster never reaches RUNNING; `INIT_SCRIPT_FAILURE` in cluster events |
| Missing library | `ModuleNotFoundError` early in the driver log, before any job output |
| Warehouse permission | Unity Catalog or external-location denial naming the exact object — this maps straight to the affected table |

A Unity Catalog permission error is worth calling out explicitly in the report: it names the object,
which ties the runtime failure to the Monte Carlo asset directly.
