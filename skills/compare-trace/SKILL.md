---
name: compare-trace
description: Compare two Monte Carlo agent conversations side-by-side. Walks each conversation to its OTel trace, runs structural diffs (graph path, latency/tokens, tool-call sequence) plus LLM-based semantic and entity-overlap evals, and opens an HTML report.
when_to_use: |
  Invoke when the user wants to A/B compare two AI agent runs by conversation ID — e.g. "compare these two agent conversations", "diff these two agent runs", "did my prompt change cause a regression", or `/compare-trace <conv_id_a> <conv_id_b>`. Useful for evaluating prompt changes, graph changes, model swaps, or tool-loadout changes by replaying a fixed scenario and comparing the resulting traces.

  Do NOT invoke for:
  - Single-trace inspection or troubleshooting one agent run (use `analyze-root-cause` / `incident-response`).
  - Comparing data tables, monitors, or alerts (different domain).
  - Generic prompt evaluation without two existing conversation IDs to compare.
bucket: Evaluate
version: 0.4.0
---

# Compare Trace

A/B compare two existing Monte Carlo agent conversations. Walks each conversation to its OTel trace via MCP, runs deterministic structural evaluators in a helper script, runs LLM-based semantic and entity evaluators inline, and emits an HTML report.

**Arguments:** $ARGUMENTS

Parse the arguments:
- **conv_id_a** (required): first positional — the baseline conversation ID (UUIDv7 or whatever ID the MC UI exposes for the run/thread).
- **conv_id_b** (required): second positional — the candidate conversation ID.
- **`--mcon <mcon>`** (optional): trace-table MCON shared by both conversations. If omitted, discover via `get_agent_metadata`.
- **`--agent <name>`** (optional): agent name to disambiguate when multiple agents are configured.
- **`--trace-ids a,b`** (optional): if a conversation contains multiple traces (retries, fan-out, multi-turn), pass the specific OTel trace_ids to compare. If omitted, the skill picks the main trace from each conversation (see Phase 2 for the rule).
- **`--labels A,B`** (optional): display labels (default `baseline`, `candidate`).
- **`--output <path>`** (optional): output HTML path. Default `/tmp/compare-trace/<short_a>_vs_<short_b>.html`.

> **Heritage:** This skill is the trace-driven backport of the [Agent A/B Evaluation Framework](https://github.com/monte-carlo-data/ai-agent/pull/1236) — same 5-signal idea, applied to already-captured traces rather than re-running the agent.

> **ID model:** `conversation_id` is the user-facing identifier (`gen_ai.conversation.id` per the OTel GenAI semantic convention). It's stored as a span attribute, **not** as the OTel `trace_id`. A single conversation can contain multiple OTel traces (retries, parallel branches, multi-turn). This skill takes the conversation_id as primary input, walks to the trace, then compares.

> **Field naming:** The MCP server returns **snake_case** in JSON responses (`trace_id`, `page_info`, `turn_errors`, `has_next_page`, `node_name`, `parent_span_id`, `is_tool_call`, `has_error`, `total_tokens`, `start_time`, `end_time`, `duration_seconds`, `is_tool_call`). The schema *descriptions* sometimes show camelCase — trust the response, not the description.

---

## Trace sources

The comparator works on **normalized traces**. Two ingestion paths produce that shape:

- **MC-stored agent conversations** — the default. Phases 1–3 below walk each conversation via MCP to its OTel trace and assemble the normalized dict.
- **Locally-collected OTel traces** — for A/B-testing changes (prompt, code, model) before they ship, with no production conversation to point at. The skill ships a local OTLP/HTTP receiver and a span-to-normalized converter. Run your agent twice, capture spans, normalize, then jump straight to Phase 4. See [`references/local-otel-collection.md`](references/local-otel-collection.md).

Both paths produce the same normalized trace shape and feed the same Phase 4+ comparator and HTML report.

---

## Setup

**Prerequisites:**
- **`python3`** for the helper scripts (stdlib only for the default MC-conversation path).
- Monte Carlo MCP server (`monte-carlo-mcp`) configured and authenticated.
- *Local OTel path only:* `opentelemetry-proto` in the Python env that runs the receiver (already a transitive dep of `opentelemetry-sdk`).

Helper scripts live under `${CLAUDE_PLUGIN_ROOT}/skills/compare-trace/scripts/`:
- `compare_traces.py` — main driver; takes two normalized trace JSON files (+ optional LLM-eval results JSON) and writes the HTML report.
- `evaluators/graph_path_diff.py`, `evaluators/latency_diff.py`, `evaluators/tool_call_diff.py` — deterministic evaluators ported from PR #1236.
- `local_otlp_receiver.py`, `sources/otel_spans.py` — used only by the local-OTel ingestion path. See `references/local-otel-collection.md`.

---

## Workflow

### Phase 1: Discover MCON and agent_name (skip if `--mcon` was provided)

Call `get_agent_metadata` with no filters. The response lists agents with `agent_name`, `trace_table_mcon`, and `source_type`. Pick the MCON + `agent_name`:
- If `--agent <name>` was given, match by `agent_name` exactly.
- Else if exactly one agent is configured, use it.
- Else ask the user which agent the conversations belong to (list `agent_name` options).

Both conversations must live on the same MCON. If you suspect otherwise (e.g. labels suggest different envs), ask first.

### Phase 2: Resolve each conversation → OTel trace_id + final completion

For each conversation_id, call:

```
get_agent_conversation(
  agent_name=<from Phase 1>,
  trace_table_mcon=<from Phase 1>,
  conversation_id=<conv_id>,
  first=100,                         # the server caps `first` at 100
  start_time="<conv_id timestamp - 1 min, ISO 8601>",
  end_time="<conv_id timestamp + 1 hour, ISO 8601>",
)
```

The conversation_id is a UUIDv7 — decode the timestamp from the first 48 bits and use a tight window. This drastically cuts response size on big tables.

**Pagination:** The server caps `first` at 100. Track `page_info.has_next_page`; paginate until exhausted **only if** you need the final completion text (see step 3 below). For trace-id selection alone (step 2), the first page is usually sufficient.

From the response:

1. **Collect candidate trace_ids.** From `edges[*].node.trace_id` plus `turn_errors[*].trace_id`. Build two sets: `all_trace_ids` and `error_trace_ids`.
2. **Pick the main trace.** Apply these rules in order:
   - If `--trace-ids a,b` was provided, use the matching value (no further filtering).
   - Else, drop any `trace_id` in `error_trace_ids`. This is critical — failed retries can appear as full sub-runs with many spans once you paginate, so "most spans" alone is not enough.
   - From the remaining trace_ids, pick the one with the most edges in the response. Tie-break by `min(start_time)` (earliest).
   - If zero non-error trace_ids remain, abort with `"conversation {conv_id} contains only failed traces"` — don't fabricate a comparison.
3. **Extract `final_output_text` from the picked trace.** This step is what forces full pagination when `page_info.has_next_page` is true.
   - Filter `edges` to the chosen `trace_id`.
   - Order by `start_time` ascending.
   - Walk **from the end** to find the last edge whose `node.completions` is a non-empty JSON-encoded string.
   - Parse `node.completions` as JSON — it's a stringified `[{is_end, is_start, message, position, role, tool_calls?}]` array (the conversation API serializes assistant turns as a list of message blocks).
   - From that parsed array, find the last entry where `role == "assistant"` AND `message` is a non-empty string AND `message` itself is not just whitespace. (You don't need to inspect `tool_calls` — a message field with substantive text is the signal that the assistant produced a final answer rather than only emitting tool requests.) That `message` value is `final_output_text`.
   - If no such entry exists (e.g. trace ended mid-tool-call), set `final_output_text = ""` — the LLM evals will be skipped and the report will note this.
4. **Extract `tool_calls` (with args) for the picked trace.** v0.3 feeds these into the argument-diff evaluator.
   - Iterate `edges` for the chosen `trace_id` in `start_time` order.
   - For each edge, parse `node.completions` as JSON (same as step 3).
   - Within each parsed assistant message, iterate its `tool_calls` array (may be empty or missing). Each tool_call has the LangChain/Bedrock shape `{"name": "<str>", "id": "<tool_use_id>", "arguments": "<JSON string>"}`.
   - For each tool_call, parse `arguments` into a dict. Be defensive: `arguments` is a JSON string in the LangChain/Bedrock shape but may already be a `dict` in Anthropic-native or OpenAI Tool API shapes — `isinstance(arguments, dict) -> use as-is`, `isinstance(arguments, str) -> json.loads(arguments or "{}")`. Empty string and missing keys both mean `{}`.
   - Accumulate ordered `[{"name": "<str>", "args": <parsed dict>, "id": "<tool_use_id>"}, ...]`. This is the `tool_calls` list for the normalized JSON.
   - If a completion has a different shape (e.g. OpenAI `function.arguments`, raw Anthropic `tool_use.input` block), parse what you can and fall through with `args = {}` for any blob you can't decode. Don't fail the whole comparison on one weird message.

Cache the conversation response and the picked `trace_id` for Phase 3 — don't refetch.

### Phase 3: Fetch each trace's structural data (with fallback)

For each selected `trace_id`, call:

```
get_agent_trace(
  mcon=<from Phase 1>,
  trace_id=<from Phase 2, dashless hex>,
  trace_start_time=<conv_id timestamp - 1 min, ISO 8601>,
  trace_end_time=<+1 hour, ISO 8601>,
)
```

The response is a flat span list with `node_name`, `parent_span_id`, `child_span_ids`, `start_time`, `end_time`, `duration` (ms), `total_tokens`, `prompt_tokens`, `completion_tokens`, `is_tool_call`, `has_prompts`, `has_completions`, `has_error`.

**Failure modes and the conversation-edge fallback:**

If `get_agent_trace` errors with `"Incomplete trace"` (or returns empty despite the conversation having edges for that trace_id), fall back to **reconstructing structural data from the conversation edges** you already have from Phase 2:

- Filter the cached `edges` to ones with this `trace_id`, ordered by `start_time`.
- `node_path` ← `[e.node.name for e in edges]`. This will be **shallower** than `get_agent_trace` would give you — only LLM and tool spans, no internal workflow/task spans. Note this in the chat report.
- `tool_calls` ← **use the list you already built in Phase 2 step 4** (from assistant completion `tool_calls` blocks). Don't rebuild it from tool-execution spans here — those spans don't carry args.
- `execution_time_seconds` ← `(max(end_time) - min(start_time))` across these edges, in seconds.
- `llm_call_count` ← count where `e.node.prompts` is non-empty and `e.node.completions` is non-empty.
- token counts ← sum of `total_tokens` / `prompt_tokens` / `completion_tokens` where present.
- `has_errors` ← `True` if any edge had a non-null `status` indicating error, else `False`. (The conversation API doesn't expose `has_error` directly.)

If `get_agent_trace` returns 404 / permission denied / retention expired, stop and report which trace failed. Don't silently treat one side as empty.

**Normalized trace JSON shape** (write one file per trace under `/tmp/compare-trace/<short>.json`):

```json
{
  "trace_id": "<hex>",
  "conversation_id": "<the conv_id this came from>",
  "label": "baseline|candidate|...",
  "source": "trace_api" | "conversation_fallback",
  "node_path": ["root_node", "child_a", "child_b", ...],
  "tool_calls": [{"name": "<tool>", "args": {"k": "v", ...}, "id": "<tool_use_id>"}, ...],
  "execution_time_seconds": 12.34,
  "llm_call_count": 5,
  "total_tokens": 1234,
  "prompt_tokens": 900,
  "completion_tokens": 334,
  "has_errors": false,
  "final_output_text": "<from Phase 2>"
}
```

**Normalization rules when using `get_agent_trace`:**
- `node_path`: sort spans by `start_time` ascending and take `node_name` for each. Skip spans where `node_name` is empty.
- `tool_calls`: **use the list you built in Phase 2 step 4** (from assistant completion `tool_calls` blocks). The trace API's tool-call spans only carry names, not args; the conversation API is where args live, so we always read tool_calls from there regardless of whether structural data came from trace_api or conversation_fallback.
- `execution_time_seconds`: `(max(end_time) - min(start_time))` in seconds across all spans.
- `llm_call_count`: count spans where `has_prompts == true` and `has_completions == true`.
- `total_tokens` / `prompt_tokens` / `completion_tokens`: sum across all spans (skip nulls).
- `has_errors`: any span with `has_error == true`.
- `final_output_text`: copied in from Phase 2.

### Phase 4: Run LLM-based evaluators inline (only if both `final_output_text` fields are non-empty)

#### 4a. Semantic diff

Run this prompt yourself (Claude) with the two final outputs as inputs:

```
You are comparing two AI agent outputs for the same scenario.
The BASELINE is the reference version. The CANDIDATE is the variant under evaluation.

Focus on SUBSTANCE, not wording — two paragraphs saying the same thing in different
words are "preserved."

BASELINE:
<paste final_output_text from trace A, truncated to ~3000 chars>

CANDIDATE:
<paste final_output_text from trace B, truncated to ~3000 chars>

Respond with exactly this JSON structure (no other text):
{
  "verdict": "preserved" | "regression" | "improvement" | "mixed",
  "similarity_score": 0.0-1.0,
  "lost_findings": ["<exact quote from baseline that candidate dropped>", ...],
  "added_findings": ["<exact quote from candidate that baseline lacked>", ...],
  "explanation": "<1-2 sentence summary of the semantic diff>"
}

Rules:
- "preserved" = same core findings, even if phrased differently.
- "regression" = candidate lost important information.
- "improvement" = candidate added valuable information.
- "mixed" = some lost, some added.
- similarity_score: 1.0 = semantically identical, 0.0 = completely different.
- For lost_findings / added_findings, QUOTE the actual phrases (≤100 words each).
  Do not paraphrase.
```

Save your JSON response into `/tmp/compare-trace/llm_semantic.json`.

#### 4b. Entity overlap

Run this extraction prompt twice (once per final output), with text input truncated to ~4000 chars:

```
Extract all concrete entities from the text below. Return a JSON object with these keys,
each mapping to a list of strings. Use exact values from the text — do not paraphrase.

Entity types:
- table_names: fully qualified table/view names (e.g. "db.schema.table")
- column_names: column or field names referenced
- metric_values: numeric values with units (e.g. "45.2%", "1000 rows")
- timestamps: dates, times, or relative time references
- job_pipeline_names: ETL job, DAG, pipeline, model, or workflow names
- pr_commit_refs: PR numbers or commit hashes
- severity_status: status or severity keywords
- monitoring_types: monitoring/anomaly type names

Omit empty lists. Return ONLY valid JSON, no other text.

Text:
<paste final_output_text>
```

Take both extraction results and compute Jaccard overlap per entity type yourself, then assemble:

```json
{
  "per_type_jaccard": {"table_names": 0.83, "column_names": 1.0, ...},
  "shared":         {"table_names": ["analytics.orders"], ...},
  "baseline_only":  {"table_names": ["staging.orders"], ...},
  "candidate_only": {"table_names": ["analytics.orders_v2"], ...},
  "overall_jaccard": 0.71,
  "baseline_facts": {...full extraction...},
  "candidate_facts": {...full extraction...}
}
```

Lowercase + strip-trailing-punctuation each value before set comparison (normalize like `_normalize` in PR #1236's `fact_overlap.py`).

Save into `/tmp/compare-trace/llm_entities.json`.

#### 4c. Corpus narrative (optional, 2-3 sentences)

A single short narrative summarising the overall verdict. Save to `/tmp/compare-trace/llm_narrative.txt`. The renderer surfaces this above the per-signal tabs.

**Sanity check before rendering:** If `overall_jaccard` is ~0 and `execution_time_seconds` ratio is >5x, the two conversations are likely **not** the same scenario. Say that explicitly in the narrative — don't let the report read as a clean A/B when the inputs aren't.

### Phase 5: Render the report

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/compare-trace/scripts/compare_traces.py \
  --baseline /tmp/compare-trace/<short_a>.json \
  --candidate /tmp/compare-trace/<short_b>.json \
  --semantic /tmp/compare-trace/llm_semantic.json \
  --entities /tmp/compare-trace/llm_entities.json \
  --narrative /tmp/compare-trace/llm_narrative.txt \
  --output /tmp/compare-trace/<short_a>_vs_<short_b>.html
```

The `--semantic`, `--entities`, and `--narrative` flags are all optional — omit them when Phase 4 was skipped.

The script opens the HTML in the user's default browser (`open` on macOS, `xdg-open` on Linux). On failure, print the file path for manual opening.

### Phase 6: Report back

Print a compact summary to chat with:
- The headline number for each signal (graph similarity, tool similarity, latency assessment, semantic verdict, entity overlap).
- The report path.
- For each conversation: which `trace_id` was picked, how many turn_errors traces were skipped, and whether structural data came from `get_agent_trace` or the conversation-edge fallback.
- If the MC webapp URL helps, call `get_mc_webapp_url` (no args) to get the regionalized base URL and include it — but don't fabricate deep-link paths; the conversation-URL schema isn't a documented public contract.

No walls of raw JSON.

---

## Known limitations (v0.3.1)

| Limitation | Why | Plan |
|---|---|---|
| **Picks one trace per conversation.** Multi-trace conversations (retries, fan-outs, multi-turn) get the largest non-error trace; the others are reported as skipped. | One-pair comparison is the simplest mental model. | **v0.4 plan:** aggregate latency/tokens across all sub-traces; show retries in a separate tab. |
| **`get_agent_trace` "Incomplete trace" forces a shallower comparison.** When we fall back to conversation edges, `node_path` only covers LLM + tool spans (no internal workflow/task spans). | The conversation API doesn't expose the framework's nested-span hierarchy. | **v0.4 plan:** report `source: "conversation_fallback"` more prominently in the HTML and add a "graph depth" note so users understand the lower node count. |
| **Arg-diff matches calls by name + position only.** PR #1236's `_match_tools_by_proximity` algorithm: for each tool name shared between A and B, greedy-pair calls by closest positional index. Doesn't recover when a tool's arg shape changed *and* its name is the only one shared (e.g. `get_warehouses()` called 5x in A and 3x in B — the extra 2 in A are unmatched). | Position-based greedy matching is what the original framework did. | **v0.4 idea:** add a stable-ID fallback using `tool_use_id` if present. |
| **No "structured fields" diff (the 6th evaluator in PR #1236).** | Trace outputs are free-form text, not named-field dicts. | Stays dropped — only meaningful when you control the agent's output schema, which we don't in trace-land. |

---

## Heuristics and edge cases

- **Empty conversations.** If `get_agent_conversation` returns zero edges for either conv_id, abort with a clear message rather than producing a misleading 0/0 report. Common causes: wrong MCON, retention expired, wrong agent_name.
- **All-failed conversations.** If every distinct `trace_id` in a conversation appears in `turn_errors`, abort — see Phase 2 rule 2 last bullet.
- **Single-span traces.** Graph-path diff and tool-call diff still run, just return trivial results. Don't suppress.
- **Token counts of 0.** If both traces show 0 total tokens (some agents don't report tokens), the latency evaluator's `total_tokens` row is suppressed automatically (rows where both sides are 0 are filtered).
- **Very large traces (>500 spans).** Truncate `node_path` and `tool_calls` to 200 entries each in the report's "full sequences" detail blocks — the diffs themselves run on the full lists.
- **Trace ID format quirks.** `get_agent_conversation` returns dashless 32-char hex `trace_id`s; pass those verbatim to `get_agent_trace`. ClickHouse-backed MCONs accept dashed UUIDs too, but BigQuery-backed ones reject dashes (`non-hexadecimal number found`).
- **`get_agent_conversation` responses routinely exceed the tool-output cap.** A single page of 100 edges is typically multiple MB once prompts and completions are included. The harness will spill the JSON to a file on disk and hand you a path instead of inline content — parse the file. Don't try to pipe the response into `jq` or assume it's in-message. Plan for 2–5 MB per page on busy agents.
- **`get_agent_conversation` does not support per-`trace_id` filtering.** When a conversation has multiple traces (main + retries from `turn_errors`), pagination returns interleaved edges across all of them. You'll fetch (and pay for) edges from error traces you'll never use. Filter client-side after the fetch; don't try to scope the API call.
- **Transient 5xx from the upstream GraphQL.** `get_agent_conversation` and `get_agent_trace` occasionally surface a `502` from `monolith-frontend` mid-pagination. Retry once with ~2–3 s backoff before aborting; a single retry resolves the vast majority of these. If a second attempt fails, stop and surface the error — don't loop.
- **Not actually an A/B?** Per Phase 4c, watch for `overall_jaccard ≈ 0` paired with a `>5x` exec-time ratio — those usually mean the user picked two unrelated runs by mistake. Call it out in the narrative; the report stat tiles alone won't.

---

## Acceptance — what "done" looks like for a single invocation

You've succeeded when:
1. Both `get_agent_conversation` calls returned edges; you selected a non-error main trace for each.
2. Both traces have structural data — either from `get_agent_trace` or the conversation-edge fallback (and you noted which).
3. The HTML report wrote to disk.
4. The LLM evaluator sections rendered (or are clearly absent with a "skipped: no completion text" note, not silently empty).
5. The browser opened the report (or you printed the file:// URL for manual opening).
6. The chat reply lists each signal's headline number, the report path, the picked trace_id per conversation, and the source (trace_api / conversation_fallback) per side. If the inputs look like a mis-paired comparison (per the Phase 4c sanity check), the chat reply says so prominently.
