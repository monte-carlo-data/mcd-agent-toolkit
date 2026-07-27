# Local OTel collection

Alternative ingestion source for the compare-trace skill. Instead of pulling
two traces from Monte Carlo's stored agent conversations, collect them
locally from any OTel-instrumented agent and feed them into the same
comparator and HTML report.

**When to reach for this:** A/B-testing a change (prompt, code, model) before
it ships, so there's no production conversation to point at. Run the agent
twice locally — once with the baseline, once with the candidate — capture
spans, compare.

The main workflow in `SKILL.md` (Phases 1–6) still applies from Phase 4
onward; this doc replaces Phases 1–3 (MC conversation walking) with three
local steps.

---

## Pipeline overview

```
your agent process  ──OTLP/HTTP──▶  local_otlp_receiver.py  ──▶  *.jsonl
                                                                    │
                                              sources/otel_spans.py ▼
                                                          *.normalized.json
                                                                    │
                                                  compare_traces.py ▼
                                                              report.html
```

Three scripts, all under `${CLAUDE_PLUGIN_ROOT}/skills/compare-trace/scripts/`:

- `local_otlp_receiver.py` — receiver. Accepts OTLP/HTTP protobuf, writes raw
  spans as JSON-lines.
- `sources/otel_spans.py` — normalizer. Converts raw spans into the trace
  shape the comparator consumes.
- `compare_traces.py` — main driver (shared with the MC-conversation path).

---

## Step 1: Start the receiver

The receiver requires `opentelemetry-proto` (already a transitive dep of
`opentelemetry-sdk`, so any venv that runs an OTel-instrumented agent
already has it).

```bash
python3 skills/compare-trace/scripts/local_otlp_receiver.py \
    --output /tmp/run-a.jsonl \
    --port 4318
```

Stays in the foreground; send `SIGINT` (Ctrl+C) when the agent run completes
to stop and flush. Each POST is appended to the JSONL — multiple agent runs
into one file is fine if you want to accumulate; one-file-per-run is
cleaner for diffing.

If port 4318 is busy, either pass `--port <n>` or kill the stale process —
`lsof -i :4318` shows the holder. (The script does not bind-retry; it
exits on `EADDRINUSE`.)

---

## Step 2: Configure your agent's OTel exporter

The receiver speaks OTLP/HTTP at `/v1/traces` on the bound port. Any agent
using the OpenTelemetry SDK can point at it with one env var:

```bash
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces
```

(The SDK appends `/v1/traces` automatically when you set
`OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318` instead — either form
works.)

If your agent uses a wrapper that takes a base URL (e.g. ai-agent's
`MC_OTEL_ENDPOINT`), set that to `http://127.0.0.1:4318` and let the wrapper
append the path.

**Force-flush before the process exits.** `BatchSpanProcessor` buffers — if
the agent exits abruptly, the last few spans never reach the receiver. Call
`tracer_provider.shutdown()` (or `force_flush()`) at the end of your run
script. See the ai-agent example in the appendix.

---

## Step 3: Normalize each run

```bash
python3 skills/compare-trace/scripts/sources/otel_spans.py \
    /tmp/run-a.jsonl \
    --output /tmp/run-a.normalized.json
```

The normalizer reads the JSONL, picks the dominant `trace_id` (handles stray
spans landing in the same file), and produces the dict shape the comparator
expects:

```json
{
  "trace_id": "...",
  "node_path": ["initialization", "react_agent", ...],
  "tool_calls": [{"name": "...", "args": {...}, "id": "..."}, ...],
  "execution_time_seconds": ...,
  "llm_call_count": ...,
  "total_tokens": ...,
  "tool_call_count": ...,
  "final_output_text": "..."
}
```

Run it once per JSONL.

---

## Step 4: Compare

Hand the two normalized files to the main driver (same call as the
MC-conversation path):

```bash
python3 skills/compare-trace/scripts/compare_traces.py \
    --baseline /tmp/run-a.normalized.json \
    --candidate /tmp/run-b.normalized.json \
    --output /tmp/report.html
```

For the optional LLM-based evaluators (`semantic_diff`, `entity_overlap`),
follow Phase 4 of `SKILL.md` — the inputs are the same.

---

## Dialect coverage

The normalizer reads three families of attributes, all derived from
conventions rather than ai-agent-specific code paths:

- **OTel GenAI semantic conventions** —
  `gen_ai.prompt.*`, `gen_ai.completion.*`, `gen_ai.usage.*`. Emitted by
  Traceloop's `LangchainInstrumentor`, OpenInference, and the official
  OpenTelemetry GenAI instrumentations.
- **LangGraph node spans** — `<node>.task` for each node call, `<name>.workflow`
  for the compiled-graph root, `<tool>.tool` for tool executions. Emitted by
  Traceloop when LangGraph is in use.
- **Tool-call attributes** — `gen_ai.{completion,prompt}.<i>.tool_calls.<j>.{name,arguments,id}`.
  The normalizer dedupes by `id` because Traceloop's Bedrock instrumentor
  only emits these under `prompt.*` on the *next* LLM call (where the call
  shows up as part of the message history), not on the completion that
  produced them. Other instrumentations emit them on completions; both
  forms are merged.

If your agent doesn't use LangGraph or Traceloop, you'll get partial
results — typically `node_path` will be empty and `tool_calls` may be
missing args. Pointing the normalizer at a different dialect is a contained
edit (it's ~200 lines); add a second module under `scripts/sources/` keyed
to whatever attribute conventions your stack uses, and feed its output into
`compare_traces.py` the same way.

---

## Appendix: ai-agent integration example

Concrete glue for driving ai-agent's `coverage_agent` locally with OTel
pointed at the receiver. The pattern transfers to other ai-agent graphs
(chat, tsa, performance) — swap the `invoke_*` import.

**Where this code should live:** in ai-agent (e.g.
`tests/scripts/coverage_repl_with_otel.py`), not in the skill. It's
ai-agent-specific glue.

```python
import os, sys, asyncio

# 1) Env bootstrap (mirrors ai-agent's .envrc dev profile).
os.environ.setdefault("AWS_PROFILE", "dev")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("AUTH_MODE", "none")
os.environ.setdefault("MONOLITH_URL", "https://cli.dev.mcinfra.io")
os.environ.setdefault("MC_USER_ID", "d930a36b-ee0b-4200-9f7b-fcc62cbbd645")
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ["MC_OTEL_ENDPOINT"] = "http://127.0.0.1:4318"
# IMPORTANT: do NOT set MCP_SERVER_URL. With it unset and no signing key
# resolved, get_mcp_tools() falls through to load_mcp_tools_in_process,
# which wraps the local mcp_server package and avoids the lambda-URL 403.

# 2) OTel setup before importing the graph.
from opentelemetry import trace as otel_trace
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from ai_agent.shared.observability import setup_otel_tracing

setup_otel_tracing(
    agent_name="coverage_agent",
    instrumentors=[LangchainInstrumentor()],
)

# 3) Optional: monkeypatch a system prompt for A/B testing. Works because
# nodes/initialization.py reads coverage_system_prompt at run time, not
# at module-load time. Won't work for prompts that get baked in at
# graph-compile time — those need a real file edit (or git worktree).
from ai_agent.coverage_agent import prompts as _p
_p.coverage_system_prompt = "<your alternate prompt>"

# 4) Invoke. tests_evals/.../coverage_agent/conftest.py provides
# invoke_coverage_agent() which compiles the graph with MemorySaver and
# returns a structured result.
sys.path.insert(0, "/path/to/ai-agent")
from tests_evals.ai_agent.coverage_agent.conftest import invoke_coverage_agent

async def run():
    result = await invoke_coverage_agent(
        user_message="what is my coverage gap?",
        sql_permission="ALLOW_SESSION",
    )
    print(result.output[:500])
    # 5) Force-flush spans before exit.
    provider = otel_trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()

asyncio.run(run())
```

**Known gotchas:**

- `load_mcp_tools_in_process()` imports `mcp_server.beacon` which requires
  `slowapi`. If it's missing from the ai-agent venv, MCP tool loading
  silently returns `[]` (the loader has a bare `except`). Install it with
  `uv pip install slowapi` (pulls in `limits` and `deprecated`).
- The `tests_evals` coverage conftest compiles the graph at import time. If
  you need to A/B-test changes that affect graph structure (not just prompt
  text), use a git worktree per branch, not in-process monkeypatching.
- The `MCP_SERVER_URL` unset trick depends on
  `ai_agent.shared.mcp.tools.get_mcp_tools` checking `is_local_mcp_available()`
  before falling back to the HTTP path. If that branch is ever removed,
  local runs will need an explicit override.
