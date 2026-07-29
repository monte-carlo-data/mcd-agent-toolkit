# Agent Evaluation Monitor

## When to use

Run LLM-evaluated quality checks on agent outputs. Best for:

- **Answer relevance scoring** — is the response relevant to the question?
- **Helpfulness and clarity** — is the response useful and well-structured?
- **Task completion** — did the agent complete what was asked?
- **Banned-keyword check** — does the output avoid specific banned keywords (e.g. password, ssn, api secret)?
- **Custom evaluation criteria** — a custom LLM check (`custom_prompt`) or SQL check (`custom_sql`) over span text

Do NOT use this for a raw numeric metric like latency or token count (use
`create_or_update_agent_metric_monitor`) — evaluation monitors add sampling and
transforms, which those don't need.

## Constraints

> **CRITICAL:** The monitor's source is the `agent` reference. Pass the
> `agentReference` value from `get_agent_metadata` verbatim — a platform
> `{database}:{schema}.{name}` reference or an OTel `service_name`. Never modify,
> truncate, or reconstruct it, and never pass an MCON.

> **CRITICAL:** `warehouse` is REQUIRED. Pass the agent's `warehouse_uuid` from
> `get_agent_metadata`; omitting it fails with "Warehouse not found". Use
> `get_warehouses` when `warehouse_uuid` is null or to resolve a warehouse by name.

> **CRITICAL:** `sampling_config` is REQUIRED. Provide `percentage`, `count`, or
> both. Per-span monitors cap `count` at 10,000; conversation-level monitors cap it
> at 500 (a percentage-only conversation config is capped at 500 per run).

> **IMPORTANT:** `transforms` is a TOP-LEVEL parameter. Each transform produces an
> output field that `alert_conditions.fields` references.

> **IMPORTANT:** `schedule_type` is `fixed` (default) or `manual` — never dynamic.
> `interval_minutes` defaults to `60` and must be at least 60 **and** a multiple of 60.

> **NEVER** set a `field` parameter on any transform. Predefined judges pull their
> inputs automatically; `custom_prompt` reads from its prompt's template variables;
> `custom_sql` reads from the columns in its expression. There is no `field` param,
> and no `context` param either.

> **NEVER** use `classification` or `sentiment` as a transform function. Their output
> column is not added to the evaluated schema, so no `alert_conditions` field can
> reference it — the monitor can't alert on the result (you get "Field `<alias>`
> doesn't exist"). To bucket or pass/fail a response, use a `custom_prompt` with
> `outputType: "boolean"` (a check) or `"string"`.

## Key characteristics

- Requires `sampling_config` — controls how many spans/conversations are sampled
- Supports a top-level `transforms` array — the evaluation logic
- Transform output field names are what `alert_conditions.fields` reference
- Optional `is_agent_conversation_aggregation=True` aggregates per conversation
  (see the conversation-grain section — OTel/ClickHouse, Snowflake Cortex, and
  Databricks Genie agents; Databricks MLflow agents are span-only)

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `description` | string | Yes | Human-readable monitor description (shown as display name) |
| `agent` | string | Yes | Agent reference — `agentReference` from `get_agent_metadata` (`{db}:{schema}.{name}` or OTel `service_name`) |
| `warehouse` | string | Yes | Warehouse name or UUID where the agent's traces live |
| `alert_conditions` | array | Yes | Alert conditions using transform output field names |
| `sampling_config` | object | Yes | `{"percentage": 10.0}`, `{"count": 100}`, or both |
| `transforms` | array | No | Evaluation transforms (predefined or custom); top-level |
| `is_agent_conversation_aggregation` | boolean | No | Aggregate evaluation per conversation (OTel/ClickHouse, Cortex, and Genie agents; MLflow agents are span-only) |
| `trace_table` | string | No | Explicit trace table — only for non-ClickHouse OTel agents |
| `agent_span_filters` | array | No | Optional span-scope refinement; at most ONE filter object. At conversation grain (`is_agent_conversation_aggregation=True`) only `agent`/`workflow` are allowed — not `task`/`spanName` |
| `sensitivity` | string | No | Anomaly detection sensitivity for AUTO operators (`low`/`medium`/`high`) |
| `aggregate_by` | string | No | Time-window bucketing (`hour`/`day`/`week`/`month`) |
| `schedule_type` | string | No | `fixed` (default) or `manual` |
| `interval_minutes` | int | No | Default `60`; at least 60 and a multiple of 60 |
| `tags` | array | No | Key-value tags on the monitor. Each tag is `{"name": "<key>", "value": "<value>"}` — the key field is `name` (NOT `key`), and unknown fields are rejected. **Default: tag every agent monitor with its agent** — `[{"name": "agent", "value": "<AGENT_NAME>"}]` (the `agentName` from `get_agent_metadata`) — so one agent's monitors can be filtered as a group |
| `domain_uuids` | array | No | Domain UUIDs to assign this monitor to — the agent-onboarding playbook passes the footprint's single resolved domain on every create (see agent-monitor-creation.md conventions) |
| `monitor_uuid` | string | No | UUID of an existing monitor to update in place (PUT semantics) |
| `dry_run` | boolean | No | Default `True` — preview YAML; set `False` to deploy |

## Predefined LLM transforms

Pass only `function` (plus an optional `alias`, an optional `modelName` to pin the
judge model — see **Judge model selection** below — and `modelConnectionId` on
BigQuery only). Do NOT set `prompt`, `sqlExpression`, `outputType`, or `field` — the
tool rejects them. Each writes a numeric score (1–5, except `semantic_similarity`
which is 0–5) to its built-in output field:

| Transform function | Output field | Output type | Description |
|-------------------|-------------|-------------|-------------|
| `answer_relevance` | `relevance_score` | number (1-5) | Is the response relevant to the question? |
| `helpfulness` | `helpfulness_score` | number (1-5) | Is the response helpful? |
| `task_completion` | `completion_score` | number (1-5) | Did the agent complete the task? |
| `language_match` | `match_score` | number (1-5) | Does the response match the expected language? |
| `clarity` | `clarity_score` | number (1-5) | Is the response clear and well-structured? |
| `prompt_adherence` | `adherence_score` | number (1-5) | Does the response follow the prompt instructions? |
| `semantic_similarity` | `similarity_score` | number (0-5) | How similar is the response to a reference? |

## Predefined SQL transforms (rule-based, no LLM needed)

Same rule: pass only `function` (and an optional `alias`); do NOT set `prompt`,
`sqlExpression`, `outputType`, `modelConnectionId`, `modelName`, or `field`.

| Transform function | Output field | Output type | Description |
|-------------------|-------------|-------------|-------------|
| `output_length` | `word_count` | number | Non-whitespace word count of the first completion |
| `json_validity` | `json_valid` | boolean | Is the first completion valid JSON? |
| `keywords` | `content_safe` | boolean | TRUE if output does NOT contain banned keywords (password, ssn, api secret, credit card). Not a general PII/secrets detector. |

## Custom transforms

Each writes an output column named by its `alias`, and that alias is what
`alert_conditions.fields` references. `outputType` is **camelCase** and one of
`"number"`, `"string"`, `"boolean"`.

| Function | Set these | Do NOT set | Output type |
|----------|-----------|------------|-------------|
| `custom_prompt` | `prompt` (with a `{{variable}}`), `alias`, `outputType` | `field`, `sqlExpression` | number / string / boolean |
| `custom_sql` | `sqlExpression`, `alias`, `outputType` | `field`, `prompt`, `modelConnectionId`, `modelName` | number / string / boolean |

- **`custom_prompt` prompts MUST reference at least one template variable** —
  `{{prompts}}`, `{{completions}}`, or `{{expected_output}}` for a per-span monitor,
  or `{{conversation}}` for a conversation-level monitor. A prompt with no variable,
  an unknown variable, or the wrong variable for the grain is rejected. With
  `"includeToolCalls": true` on the transform, `{{conversation}}` also carries the
  agent's tool calls as clearly identifiable TOOL entries (see Conversation-grain
  judges below).
- **`custom_sql` runs against warehouse columns.** On Snowflake Cortex agents,
  `prompts`/`completions` are arrays — reference the string columns
  `first_completion` / `full_completion` / `first_prompt` instead. The dry-run does
  not evaluate the SQL, so a bad column surfaces only at run time.
## Judge model selection (`modelName`)

**`modelName`** pins the judge model for LLM-based transforms (predefined judges and
`custom_prompt`). Optional — omit it to use the warehouse default. **Models are
warehouse-specific** because the judge runs inside the agent's warehouse — never
offer models from the wrong pool:

| Agent's warehouse | Judge models (default first) |
|-------------------|------------------------------|
| Snowflake (Cortex) | `llama3.1-70b`, `llama3.1-405b`, `llama3.1-8b`, `mistral-large`, `mixtral-8x7b`, `jamba-1.5-large`, `jamba-1.5-mini`, `jamba-instruct`, `snowflake-arctic` — **no Claude models on Snowflake** |
| Databricks | `databricks-meta-llama-3-3-70b-instruct`, plus other `databricks-*` endpoints |
| BigQuery | `gemini-2.5-flash`, `gemini-2.5-pro` |
| OpenTelemetry (ClickHouse/Athena traces) | `us.anthropic.claude-sonnet-4-5-20250929-v1:0`, `us.anthropic.claude-haiku-4-5-20251001-v1:0`, `us.anthropic.claude-opus-4-1-20250805-v1:0` |

A known catalog model on the wrong warehouse is rejected at dry-run; unrecognized
names pass through to the warehouse as-is.

**`modelConnectionId`** is **BigQuery-only** (and required there) — the BigQuery
Cloud resource connection in the customer's own GCP project that runs the judge. It
is NOT a Monte Carlo setting or integration and Monte Carlo cannot list it; on
BigQuery, ask the user for their BigQuery connection ID. **On every other warehouse,
omit it entirely and never ask the user for it.** To choose the judge model, use
`modelName` — there is no "model connection" to configure outside BigQuery.

## Conversation-grain judges

Each LLM judge has a `*_conversation` variant that evaluates a whole conversation
instead of a single span. These require `is_agent_conversation_aggregation: true`
**AND a conversation-capable agent** — OpenTelemetry/ClickHouse, Snowflake Cortex,
or Databricks Genie (Databricks MLflow agents reject conversation aggregation).
The output/score column is not always the span judge's name:

| Conversation function | Output/score field |
|-----------------------|--------------------|
| `answer_relevance_conversation` | `relevance_score` |
| `task_completion_conversation` | `task_completion_score` |
| `helpfulness_conversation` | `helpfulness_score` |
| `clarity_conversation` | `clarity_score` |
| `prompt_adherence_conversation` | `adherence_score` |
| `language_match_conversation` | `match_score` |
| `satisfaction_conversation` | `satisfaction_score` (no per-span counterpart) |

**`includeToolCalls` — default ON at conversation grain.** Every conversation-grain
transform (judge or custom) accepts an optional `includeToolCalls` boolean. When
`true`, the agent's tool calls (name, inputs, outputs, and errors) are included in
the judged conversation as clearly identifiable TOOL entries between the messages
that triggered them — in call order, autonomous agent steps included — so the judge
scores what the agent did, not just what it said. **Set `"includeToolCalls": true`
on every conversation-grain transform by default.** Omit it only for pure style/tone
judges — `clarity_conversation`, `language_match_conversation`, or a wording-only
custom prompt — where the transcript's wording alone is judged and tool noise
dilutes the judge. The field is invalid at span grain: the tool rejects
`includeToolCalls: true` on a monitor without
`is_agent_conversation_aggregation=True`.

At conversation grain, a `custom_prompt` may only reference `{{conversation}}`, and
the predefined SQL checks and `custom_sql` are not supported. At span grain,
`{{conversation}}` is not available. With `"includeToolCalls": true` on the
transform, `{{conversation}}` also carries the agent's tool calls (name, inputs,
outputs, errors) as clearly identifiable TOOL entries between the messages that
triggered them, in call order, autonomous steps included — write conversation
prompts that judge actions with that visibility in mind. `agent_span_filters` at
conversation grain may scope only by `agent`/`workflow` — `task`/`spanName` are
span-level and are rejected.

## Alert conditions

Use `thresholdValue` (camelCase) for threshold operators — NOT `threshold_value`
(snake_case). Each condition names one or more transform output fields in `fields`.

```json
{
    "metric": "NUMERIC_MEAN",
    "operator": "LT",
    "fields": ["relevance_score"],
    "thresholdValue": 2
}
```

**Match the metric to the transform's output type** (a mismatch is rejected at
dry-run):

- **number** (the 1–5 judges, `output_length`, numeric `custom_prompt`/`custom_sql`)
  → `NUMERIC_MEAN` and other numeric metrics.
- **boolean** (`json_validity`, `keywords`, boolean `custom_prompt`/`custom_sql`) →
  `TRUE_RATE` / `FALSE_RATE`. NEVER a numeric metric — a boolean field has no mean.
- `NULL_RATE` works on any output type.

`fields` must name a column in the evaluated schema — a predefined judge's built-in
field, a custom transform's `alias`, or a raw source column (span grain:
`duration_sec`, `total_tokens`, …; conversation grain: `turn_count`,
`duration_seconds`, `status`). Duplicate `(metric, field)` pairs across conditions
are rejected.

## Examples

The `agent` value below comes from `get_agent_metadata`'s `agentReference` field.
The first example uses a platform `{database}:{schema}.{name}` reference; the others
use an OTel `service_name`. Use whichever form your agent returns.

### Answer relevance evaluation (platform agent reference)

```
create_or_update_agent_evaluation_monitor(
    description="Chat Agent relevance evaluation",
    agent="analytics:agents.support_bot",
    warehouse="Prod Warehouse",
    transforms=[
        {"function": "answer_relevance"}
    ],
    alert_conditions=[
        {"metric": "NUMERIC_MEAN", "operator": "LT", "fields": ["relevance_score"],
         "thresholdValue": 2}
    ],
    sampling_config={"count": 100},
    dry_run=True
)
```

### Banned-keyword check as a boolean rate (OTel service_name)

`keywords` outputs the boolean `content_safe`, so alert on its false rate — a
numeric metric on a boolean field is rejected.

```
create_or_update_agent_evaluation_monitor(
    description="Chat Agent banned-keyword check",
    agent="checkout-agent",
    warehouse="Agent Observability",
    transforms=[
        {"function": "keywords"}
    ],
    alert_conditions=[
        {"metric": "FALSE_RATE", "operator": "GT", "fields": ["content_safe"],
         "thresholdValue": 0.05}
    ],
    sampling_config={"count": 100},
    dry_run=True
)
```

### Custom prompt as a pass/fail (boolean) check

The prompt references `{{completions}}`; there is no `field`; `outputType` is
`boolean` so the alert watches the true/false rate. This is the right shape for
"how often did the agent do X".

```
create_or_update_agent_evaluation_monitor(
    description="Did the agent disambiguate the product before answering?",
    agent="checkout-agent",
    warehouse="Agent Observability",
    transforms=[
        {
            "function": "custom_prompt",
            "alias": "disambiguated_product",
            "prompt": "Did this response either ask which product the user meant, or state which product it assumed, before answering? Response: {{completions}}. Answer true or false.",
            "outputType": "boolean"
        }
    ],
    alert_conditions=[
        {"metric": "FALSE_RATE", "operator": "GT", "fields": ["disambiguated_product"],
         "thresholdValue": 0.2}
    ],
    sampling_config={"percentage": 20.0},
    dry_run=True
)
```

### Custom SQL numeric check

`custom_sql` needs `sqlExpression` + `alias` + `outputType`; alert with a numeric
metric on the alias.

```
create_or_update_agent_evaluation_monitor(
    description="Completion length floor",
    agent="checkout-agent",
    warehouse="Agent Observability",
    transforms=[
        {
            "function": "custom_sql",
            "alias": "answer_chars",
            "sqlExpression": "LENGTH(first_completion)",
            "outputType": "number"
        }
    ],
    alert_conditions=[
        {"metric": "NUMERIC_MEAN", "operator": "LT", "fields": ["answer_chars"],
         "thresholdValue": 40}
    ],
    sampling_config={"count": 100},
    dry_run=True
)
```

### Conversation-level evaluation (OTel agent only)

Set `is_agent_conversation_aggregation=True`, use a `*_conversation` judge, and alert
on its score field (`task_completion_conversation` → `task_completion_score`).
Sampling `count` ≤ 500. The transform carries `"includeToolCalls": true` (the
conversation-grain default) so completion is judged against what the agent actually
did, not just what it said.

```
create_or_update_agent_evaluation_monitor(
    description="Task completion across full conversations",
    agent="checkout-agent",
    warehouse="Agent Observability",
    is_agent_conversation_aggregation=True,
    transforms=[
        {"function": "task_completion_conversation", "includeToolCalls": true}
    ],
    alert_conditions=[
        {"metric": "NUMERIC_MEAN", "operator": "AUTO", "fields": ["task_completion_score"]}
    ],
    sampling_config={"count": 100},
    dry_run=True
)
```

## Custom-prompt template library

Named, reusable `custom_prompt` templates for the most common Output-pillar checks. All three are
**conversation-level**: set `is_agent_conversation_aggregation=True` and reference
`{{conversation}}` — the only template variable a conversation-grain prompt may use. All three
carry `"includeToolCalls": true` — the conversation-grain default; none is a pure style/tone
judge (a wording-only check like a clarity- or language-style judge would omit it) — so the judge
reads the agent's TOOL entries alongside the messages. On a span-only agent (Databricks MLflow),
adapt the prompt to `{{completions}}` at span grain instead and drop `includeToolCalls` too — it
is rejected at span grain.

**Render, don't recite.** Before proposing a template, replace every `<AGENT_NAME>` placeholder
with the agent's actual name (from `get_agent_metadata`) and tailor the wording to the intents and
failure modes you observed in its real conversations — a template proposed as generic boilerplate
judges generically. `<AGENT_NAME>` is an authoring placeholder, **not** a template variable: never
send it verbatim or turn it into a curly-brace variable — the agent name goes into the prompt as
plain literal text. Always show the user the full rendered prompt text for approval before
creating the monitor (dry-run first, as usual).

### `frustration_free_score` — was the experience frustration-free?

1–5 score for user-visible friction: rephrasing, repeated corrections, complaints, giving up.
Complements `helpfulness` — helpfulness judges the answers, this judges the user's experience
across the whole conversation. Part of the **baseline pack** — propose it for every agent.

```json
{
    "function": "custom_prompt",
    "alias": "frustration_free_score",
    "prompt": "Read this conversation between a user and <AGENT_NAME>: {{conversation}}. Rate from 1 to 5 how frustration-free the user's experience was. 5 = no sign of frustration; the user got what they needed without friction. 4 = minor friction (one clarification or retry) but the user stayed satisfied. 3 = noticeable friction; the user had to rephrase or repeat themselves to get a useful answer. 2 = clear frustration; the user complained, corrected the agent repeatedly, or expressed annoyance. 1 = severe frustration; the user gave up, abandoned the task, or ended the conversation visibly dissatisfied. Answer with only the number.",
    "outputType": "number",
    "includeToolCalls": true
}
```

Recommended alert: `{"metric": "NUMERIC_MEAN", "operator": "LT", "fields": ["frustration_free_score"], "thresholdValue": 4}`

### `answer_attempt_score` — did the agent attempt a real answer?

1–5 score for whether the agent actually attempted to answer the user's data questions, versus
deflecting, refusing, asking clarifying questions without ever answering, or erroring out.
Part of the **analytics pack** (Cortex/Genie — see below), where deflection is the dominant
failure mode of NL2SQL/analytics agents. This judge benefits directly from `includeToolCalls`:
the TOOL entries show whether a query actually ran, separating a real answer attempt from a
confident deflection — so the prompt tells the judge to use them.

```json
{
    "function": "custom_prompt",
    "alias": "answer_attempt_score",
    "prompt": "Read this conversation between a user and <AGENT_NAME>, an analytics agent that answers data questions: {{conversation}}. Rate from 1 to 5 how fully the agent attempted to answer the user's data questions. TOOL entries in the conversation show what the agent actually ran; a substantive answer attempt is normally backed by one. 5 = every question got a direct, substantive answer attempt (a query, a result, or a concrete data answer). 4 = answered with minor gaps or hedging. 3 = partial; some questions were deflected or met only with clarifying questions. 2 = mostly deflected, refused, or answered a different question than asked. 1 = no real answer attempt at all. Answer with only the number.",
    "outputType": "number",
    "includeToolCalls": true
}
```

Recommended alert: `{"metric": "NUMERIC_MEAN", "operator": "LT", "fields": ["answer_attempt_score"], "thresholdValue": 4}`

### `user_correction` — did the user have to correct the agent?

Boolean detector for follow-up-turn corrections — the user saying an answer was wrong, restating
what they actually meant, or re-asking the same question. A correction is the strongest observable
ground-truth signal that an earlier answer missed. Part of the **analytics pack** (Cortex/Genie —
see below). Framed so `true` = a correction occurred, making `TRUE_RATE` the correction rate.

```json
{
    "function": "custom_prompt",
    "alias": "user_correction",
    "prompt": "Read this conversation between a user and <AGENT_NAME>: {{conversation}}. Did the user correct the agent in a follow-up turn - for example saying a previous answer was wrong, restating what they actually meant, or re-asking the same question because the answer missed it? A clarifying question from the agent does not count as a correction. Answer true if at least one correction occurred, false otherwise.",
    "outputType": "boolean",
    "includeToolCalls": true
}
```

Recommended alert: `{"metric": "TRUE_RATE", "operator": "GT", "fields": ["user_correction"], "thresholdValue": 0.2}` —
0.2 is a conservative starting point, not a calibrated one. Tune it to the agent's observed
correction rate after the first week of results, or switch the operator to `AUTO_HIGH` once
enough history has accumulated for anomaly detection.

### Action-aware checks — judging what the agent did

With tool calls included (`includeToolCalls: true`), a `custom_prompt` can judge **action
correctness**, not just answer text — the TOOL entries are the evidence the judge reads. Propose
one when the agent's job is to DO something and you observed the corresponding failure mode:

- "Was the create-monitor tool called with the configuration the user asked for, and did it
  error?" — catches an agent that confirms an action it never (or incorrectly) performed.
- "Did the agent run a SQL query before answering a data question?" — catches an analytics
  agent that answers a data question without ever touching the data.

Frame these as booleans so `FALSE_RATE` is the failure rate (see the pass/fail boolean example
above).

## Output-pillar eval packs

When setting up evaluation coverage for an agent (the Output pillar of agent observability),
propose these packs rather than inventing a one-off list. Shared defaults for every pack monitor:

- **Schedule:** daily — `interval_minutes=1440`
- **Sampling:** `{"count": 100}` (100 conversations per run; the conversation-grain cap is 500)
- **Tags:** `[{"name": "agent", "value": "<AGENT_NAME>"}]` — tag every monitor with its agent so
  one agent's monitors can be filtered as a group
- **Grain:** conversation (`is_agent_conversation_aggregation=True`) where the agent supports it;
  span grain with `{{completions}}` / span judges otherwise
- **Tool calls:** `includeToolCalls: true` on every conversation-grain transform (the default —
  omit only for pure style/tone judges); drop it at span grain, where it is rejected

### Baseline pack — every agent

| Monitor | Transform | Alert |
|---------|-----------|-------|
| Helpfulness | predefined `helpfulness_conversation` (plain `helpfulness` on span-only agents) | `NUMERIC_MEAN` `LT` 4 on `helpfulness_score` |
| Frustration | `frustration_free_score` template | `NUMERIC_MEAN` `LT` 4 on `frustration_free_score` |

Start with the fixed `LT 4` floor. `AUTO_LOW` (drift detection) is the alternative once the
monitor has accumulated a baseline — but not alongside it in the same monitor: duplicate
`(metric, field)` pairs across conditions are rejected, so moving to drift means changing the
condition's operator, not adding a second condition.

Full example — the frustration baseline monitor with all pack defaults applied:

```
create_or_update_agent_evaluation_monitor(
    description="Support Bot - frustration-free conversations (baseline)",
    agent="analytics:agents.support_bot",
    warehouse="Prod Warehouse",
    is_agent_conversation_aggregation=True,
    transforms=[
        {
            "function": "custom_prompt",
            "alias": "frustration_free_score",
            "prompt": "Read this conversation between a user and Support Bot: {{conversation}}. Rate from 1 to 5 how frustration-free the user's experience was. 5 = no sign of frustration; the user got what they needed without friction. 4 = minor friction (one clarification or retry) but the user stayed satisfied. 3 = noticeable friction; the user had to rephrase or repeat themselves to get a useful answer. 2 = clear frustration; the user complained, corrected the agent repeatedly, or expressed annoyance. 1 = severe frustration; the user gave up, abandoned the task, or ended the conversation visibly dissatisfied. Answer with only the number.",
            "outputType": "number",
            "includeToolCalls": true
        }
    ],
    alert_conditions=[
        {"metric": "NUMERIC_MEAN", "operator": "LT", "fields": ["frustration_free_score"],
         "thresholdValue": 4}
    ],
    interval_minutes=1440,
    sampling_config={"count": 100},
    tags=[{"name": "agent", "value": "Support Bot"}],
    dry_run=True
)
```

### Analytics pack — Cortex and Genie agents only

Propose **only when the agent's `backend_class` is `platform_agent` (Snowflake Cortex) or
`databricks_genie`** — these are the NL2SQL/analytics agents where deflected answers and
user-corrected answers are the dominant failure modes. Do not propose this pack for other agents.

| Monitor | Transform | Alert |
|---------|-----------|-------|
| Answer attempts | `answer_attempt_score` template | `NUMERIC_MEAN` `LT` 4 on `answer_attempt_score` |
| User corrections | `user_correction` template | `TRUE_RATE` `GT` 0.2 on `user_correction` (starting point — tune, or move to `AUTO_HIGH` with history) |

Same defaults as the baseline pack: daily, `{"count": 100}` sampling, the `agent` tag,
`includeToolCalls: true` on each transform, and full rendered prompt text shown for approval
before creating.

## Common errors

| Error message | Cause | Fix |
|--------------|-------|-----|
| Warehouse not found | `warehouse` omitted or wrong | Pass the agent's `warehouse_uuid` from `get_agent_metadata`; if null, list warehouses via `get_warehouses` |
| invalid / unresolvable `agent` reference | The `agent` value wasn't taken from `get_agent_metadata` | Use the exact `agentReference` value — do not construct it by hand, and never pass an MCON |
| "Field X doesn't exist" | Wrong transform output field name, or a `classification`/`sentiment` output that isn't in the schema | Use the documented output field (e.g. `relevance_score`) or a custom transform's `alias`; replace `classification`/`sentiment` with a `custom_prompt` (`outputType` `boolean`/`string`) |
| metric/output-type mismatch | Numeric metric on a boolean field (or vice versa) | `NUMERIC_MEAN` for numbers, `TRUE_RATE`/`FALSE_RATE` for booleans, `NULL_RATE` for any type |
| `task`/`spanName` rejected in `agent_span_filters` | Used a span-level filter dimension at conversation grain | At conversation grain (`is_agent_conversation_aggregation=True`), scope only by `agent`/`workflow` — `task`/`spanName` are span-level |
| `includeToolCalls` rejected | The field was set on a per-span monitor | `includeToolCalls` is conversation-grain only — keep it (default ON) with `is_agent_conversation_aggregation=True`; drop it at span grain |
