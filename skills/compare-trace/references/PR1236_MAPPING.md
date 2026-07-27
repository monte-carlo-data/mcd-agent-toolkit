# Mapping from PR #1236 to the MC trace API

PR: `monte-carlo-data/ai-agent#1236` ("Agents regression - TSA ready for now").

The PR builds an A/B framework that **runs the agent** under two branches and saves
`ScenarioOutput` snapshots locally, then runs 6 evaluators + an LLM summarizer + an
HTML renderer over the snapshot pairs. This skill backports the comparison half —
it operates on **already-captured traces** fetched via `get_agent_trace` and
`get_agent_conversation`, not on a fresh agent run.

## ScenarioOutput → normalized trace JSON

| PR field | Source in the trace API | Notes |
|---|---|---|
| `final_output` (dict) | Last `completions` string from `get_agent_conversation` filtered to the trace | Free text in v0.1 (not a named-field dict). |
| `node_path: list[str]` | `nodeName` of every span in `get_agent_trace`, sorted by `startTime` | Direct fit. |
| `tool_calls: list[{name,args}]` | Spans with `isToolCall == true`, take `nodeName` for `name`; `args` left empty | v0.2 will parse args from completion `tool_calls` JSON. |
| `execution_time_seconds` | `(max(endTime) - min(startTime))` across spans | Or sum root-span `duration / 1000`. |
| `llm_call_count` | Count of spans with `hasPrompts && hasCompletions` | Closer match than the PR's "AI-typed message count". |
| `total_tokens` | Sum of `totalTokens` across all spans | PR's runner left this at 0; we actually populate it. |
| `status` / `error` | Any `hasError == true` span → `has_errors: true` | Coarser than the PR's per-scenario try/except, but the agent already ran. |

## Evaluator parity

| PR evaluator | Trace-API parity | Status |
|---|---|---|
| `graph_path_diff` | Jaccard + LCS on `node_path` | ✅ identical implementation |
| `latency_diff` | Same 4 metrics (`execution_time_seconds`, `llm_call_count`, `total_tokens`, `tool_call_count`) | ✅ identical |
| `tool_call_diff` (names) | Levenshtein on tool-name sequences | ✅ identical |
| `tool_call_diff` (arguments) | Phase 2 walks `get_agent_conversation` and parses `tool_calls` blocks from each assistant completion (LangChain/Bedrock `arguments` JSON-string shape verified empirically; OpenAI / Anthropic shapes parsed best-effort). `_match_tools_by_proximity` + `_compare_args` ported verbatim from PR #1236. | ✅ shipped in v0.3.0 |
| `semantic_diff` | LLM prompt over two free-text completions instead of named fields | ⚠️ adapted — Claude runs the prompt inline, no per-field scoring |
| `fact_overlap` | LLM extraction over two free-text completions instead of named fields | ⚠️ adapted — same prompt, just unified text |
| `structured_field_diff` | Requires a named-field output schema from the agent | ❌ dropped — not meaningful for arbitrary traces |

## Things deliberately NOT backported

- **`capture` + `run_scenario`** — the PR's runner uses `graph.astream` and `_ScenarioLogCapture`. We skip the whole capture half because the user is comparing existing traces.
- **`AgentAdapter` protocol** — agent-specific, only useful when re-running.
- **Per-scenario corpus reporting** — we compare a single pair, not N scenarios. The HTML strips down to one card.
- **`get_fast_smart_llm` dependency** — the LLM evals run inline as Claude prompts (Phase 4 in SKILL.md), no Python LLM call.
