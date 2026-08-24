# Datadog

Covers any `source` where the customer ships runtime logs to Datadog rather than reading them from
the cloud provider. Common in shops that centralize observability — and the case where federated
retrieval is most obviously right, since the Datadog MCP server is often already configured and
authorized in the session.

## Prefer the MCP server

If `mcp__datadog__search_datadog_logs` is available, use it. It is scoped, structured, and already
authorized — no credential handling, no shelling out.

```
search_datadog_logs(
  query="service:airflow @dag_id:nightly_core @task_id:dbt_run status:error",
  from="2026-08-24T02:10:00Z",
  to="2026-08-24T02:25:00Z"
)
```

Fall back to the API only if the MCP server is absent and `DD_API_KEY` / `DD_APP_KEY` are set.

## Building the query

Map the Step 1 identifiers onto Datadog's search syntax. The exact attribute names depend on how the
customer tags — check what comes back from a loose query before narrowing.

| From Monte Carlo | Datadog |
|---|---|
| `source` | `service:airflow`, `service:databricks`, `source:ecs` |
| `job_name` / `dag_id` | `@dag_id:<name>` or free text `"<job_name>"` |
| `task_name` / `task_id` | `@task_id:<name>` |
| `run_id` | `@run_id:<id>` — the highest-precision filter when the customer tags it |
| `started_at` / `end_time` | `from` / `to`, padded |

Order of attempts:

1. **Narrow** — `@run_id` plus `status:error`. If the customer tags run ids, this is exact.
2. **Widen** — drop to `service` + `@dag_id` + `status:error` over the window.
3. **Widest** — `service` + `status:error` over the window, then filter by eye. Useful when the
   failure is infrastructure-level and carries no job tags at all.

Do not skip straight to step 3. An unfiltered error query over a busy service returns noise that
buries the run you care about.

## Correlating

Datadog's value here is what sits *next to* the log line. Once you have the failing line:

- Pull the surrounding lines for that same `host`/`container_id`, unfiltered by severity — the
  error is often the second symptom, not the first.
- Check whether the same error appears across other services in the window. A Secrets Manager
  outage looks like one dbt failure and is actually twenty services failing.

That cross-service view is the strongest argument for the federated shape: the customer's Datadog
holds context Monte Carlo will never have.

## Reading the result

| Pattern | Means |
|---|---|
| Errors across many services in the same minute | Shared dependency — secrets, network, IAM. Not a data problem. |
| A single service, single task, repeated across days | Chronic job-level bug. Worth a monitor. |
| No logs at all in the window | Either the service never ran, or it does not ship to Datadog. Distinguish before concluding — query the window with no filters to check the service reports at all. |

That last row matters. An empty Datadog result is ambiguous, and reporting it as "no errors" when
the real answer is "this service was never instrumented" is exactly the silent-wrong-guess failure
mode the skill is meant to avoid.
