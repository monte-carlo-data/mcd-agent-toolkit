# compare-trace

A/B compare two Monte Carlo agent conversations by ID and produce an HTML report.

Trace-driven backport of the [Agent A/B Evaluation Framework](https://github.com/monte-carlo-data/ai-agent/pull/1236) (PR #1236 in `ai-agent`). The original ran the agent itself against fixed scenarios; this skill operates on already-captured conversations fetched via the Monte Carlo MCP server.

## Invocation

```
/compare-trace <conv_id_a> <conv_id_b>
```

Optional flags: `--mcon`, `--agent`, `--trace-ids a,b` (force specific OTel trace_ids when a conversation has multiple), `--labels A,B`, `--output path.html`.

## ID model

`conversation_id` is the user-facing identifier (per the OTel GenAI `gen_ai.conversation.id` semantic convention). It's stored as a span attribute, **not** as the OTel `trace_id`. One conversation can contain multiple OTel traces (retries, fan-outs, multi-turn).

The skill resolves `conversation_id → trace_id` via `get_agent_conversation`. By default it picks the trace with the most spans (= the "main" execution); override with `--trace-ids` to compare specific sub-traces.

## Signals

| Signal | Type | Notes |
|---|---|---|
| Graph Path | deterministic | Jaccard on node sets + LCS/max ordering |
| Latency & Tokens | deterministic | Per-metric ratios; flag if candidate > 1.5x baseline |
| Tool Call Sequence + Args | deterministic | Levenshtein on tool-name sequences; matched calls also get a top-level arg-key diff (added / removed / changed) |
| Semantic Diff | LLM (inline) | Claude runs prompt over both final-completion texts |
| Entity Overlap | LLM (inline) | Extracts 8 entity types, computes per-type Jaccard |

The two LLM signals require non-empty `final_output_text` for both sides (pulled from the last completion span in each conversation). Without that, the report ships with the 3 structural signals.

## Files

- `SKILL.md` — full workflow Claude follows
- `scripts/compare_traces.py` — driver that consumes normalized trace JSON + optional LLM-eval JSON and writes HTML
- `scripts/evaluators/{graph_path_diff,latency_diff,tool_call_diff}.py` — pure-Python evaluators ported from PR #1236
- `references/PR1236_MAPPING.md` — fields-and-signals mapping from PR #1236 to the trace API

## Known limitations (v0.3)

- Picks one trace per conversation (the largest non-error one by edge count). Multi-trace conversations (retries, fan-outs) currently get their other traces dropped — pass `--trace-ids` to override.
- Arg-diff matches calls by name + nearest position (greedy). When a tool's count differs between A and B, the surplus calls go unmatched. v0.4 plan: stable-ID fallback using `tool_use_id` when present.
- No "structured fields" diff (the 6th evaluator in PR #1236) — only meaningful when you control the agent's output schema, which we don't from trace-land.
