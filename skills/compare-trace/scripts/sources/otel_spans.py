"""Normalize a JSONL stream of OTLP spans (as written by
``local_otlp_receiver.py``) into the shape the compare-trace skill consumes.

Span dialect: GenAI semantic conventions (``gen_ai.prompt.*``, ``gen_ai.completion.*``,
``gen_ai.usage.*``) — these are emitted by the Traceloop / openllmetry
``LangchainInstrumentor`` and are stable across LangChain releases.

LangGraph node spans are detected by the ``*.task`` name suffix that the
instrumentor uses for each node call. The workflow root is detected by the
``*.workflow`` suffix and is also where we read the overall duration from.

Tool-call extraction reads ``gen_ai.completion.{i}.tool_calls.{j}.{name,arguments,id}``
attributes when present. If they are absent — either because the run made no
tool calls, or because the instrumentor omitted them — ``tool_calls`` is
returned empty rather than guessed-at.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_TASK_NAME_RE = re.compile(r"^(?P<node>.+)\.task$")
_WORKFLOW_NAME_RE = re.compile(r"^(?P<name>.+)\.workflow$")
_TOOL_SPAN_NAME_RE = re.compile(r"^(?P<tool>.+)\.tool$")

# Attribute key patterns we care about for tool-call extraction.
# Traceloop's Bedrock instrumentor only emits tool_calls under
# ``gen_ai.prompt.*.tool_calls.*`` (where prior assistant tool calls echo
# back as part of the message history); OpenAI / Anthropic native paths
# also emit under ``gen_ai.completion.*.tool_calls.*``. Accept both.
_TOOL_CALL_RE = re.compile(
    r"^gen_ai\.(?:completion|prompt)\."
    r"(?P<msg_idx>\d+)\.tool_calls\.(?P<tc_idx>\d+)\.(?P<field>name|arguments|id)$"
)


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            spans.append(json.loads(line))
    return spans


def _extract_tool_calls_from_attrs(
    attrs: dict[str, Any],
) -> list[dict[str, Any]]:
    """Pull tool_calls out of one LLM span's gen_ai.{completion,prompt}.* attrs.

    Returns calls in (msg_idx, tc_idx) order. Callers are expected to
    dedupe across spans by tool-call ``id``: the same call typically appears
    in the producing completion AND in every subsequent prompt's message
    history.

    ``arguments`` is a JSON-encoded string in nearly all cases; some
    instrumentations emit a dict instead. Both are handled.
    """
    buckets: dict[tuple[int, int], dict[str, Any]] = defaultdict(dict)
    for key, value in attrs.items():
        match = _TOOL_CALL_RE.match(key)
        if not match:
            continue
        msg_idx = int(match.group("msg_idx"))
        tc_idx = int(match.group("tc_idx"))
        buckets[(msg_idx, tc_idx)][match.group("field")] = value

    calls: list[dict[str, Any]] = []
    for (_, _), raw in sorted(buckets.items()):
        name = raw.get("name") or ""
        args_raw = raw.get("arguments", "")
        if isinstance(args_raw, dict):
            args = args_raw
        elif isinstance(args_raw, str) and args_raw:
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {}
        else:
            args = {}
        calls.append({"name": name, "args": args or {}, "id": raw.get("id", "")})
    return calls


def normalize(spans: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert raw OTLP spans into a compare-trace normalized trace dict."""
    if not spans:
        return {
            "trace_id": "",
            "node_path": [],
            "tool_calls": [],
            "execution_time_seconds": 0.0,
            "llm_call_count": 0,
            "total_tokens": 0,
            "tool_call_count": 0,
            "final_output_text": "",
        }

    # Take the dominant trace_id (handles stray smoke spans landing in the
    # same file). All spans in a single agent run share one trace_id.
    by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in spans:
        by_trace[s.get("trace_id", "")].append(s)
    trace_id = max(by_trace, key=lambda k: len(by_trace[k]))
    run_spans = by_trace[trace_id]

    # LangGraph nodes — ordered by start time, suffix stripped.
    node_spans = sorted(
        (s for s in run_spans if _TASK_NAME_RE.match(s.get("name", ""))),
        key=lambda s: s.get("start_time_unix_nano", 0),
    )
    node_path = [_TASK_NAME_RE.match(s["name"]).group("node") for s in node_spans]

    # LLM calls: any span carrying gen_ai.prompt.* counts.
    llm_spans = [
        s
        for s in run_spans
        if any(k.startswith("gen_ai.prompt.") for k in s.get("attributes", {}))
    ]

    total_tokens = 0
    final_output_text = ""

    # Dedupe tool calls by id across spans — the same call appears once in
    # the producing completion and again in every subsequent prompt history.
    tool_calls_by_id: dict[str, dict[str, Any]] = {}
    # Anonymous calls (no id) keyed by (name, json-args) to avoid losing
    # repeated tool invocations that legitimately differ from each other.
    anon_tool_calls: list[dict[str, Any]] = []
    # Order calls by the start_time of the FIRST span that mentioned them.
    first_seen_ns: dict[str, int] = {}

    for llm in sorted(llm_spans, key=lambda s: s.get("start_time_unix_nano", 0)):
        attrs = llm.get("attributes", {})
        start_ns = llm.get("start_time_unix_nano", 0)

        # Prefer the explicit total_tokens attr if present; else sum the parts.
        total = (
            attrs.get("llm.usage.total_tokens")
            or attrs.get("gen_ai.usage.total_tokens")
            or (
                (attrs.get("gen_ai.usage.prompt_tokens") or 0)
                + (attrs.get("gen_ai.usage.completion_tokens") or 0)
            )
        )
        try:
            total_tokens += int(total)
        except (TypeError, ValueError):
            pass

        for call in _extract_tool_calls_from_attrs(attrs):
            tid = call.get("id") or ""
            if tid:
                if tid not in tool_calls_by_id:
                    tool_calls_by_id[tid] = call
                    first_seen_ns[tid] = start_ns
            else:
                anon_tool_calls.append(call)

        # Capture the LATEST assistant completion as final_output_text.
        # Walk completion indices in order; the highest index is the
        # canonical final answer for that LLM call.
        for i in range(20):
            content = attrs.get(f"gen_ai.completion.{i}.content")
            role = attrs.get(f"gen_ai.completion.{i}.role")
            if content and role == "assistant" and isinstance(content, str):
                final_output_text = content.strip()

    tool_calls = [
        tool_calls_by_id[tid]
        for tid in sorted(tool_calls_by_id, key=lambda t: first_seen_ns.get(t, 0))
    ]
    tool_calls.extend(anon_tool_calls)

    # Workflow root span carries the wall-clock duration.
    workflow_spans = [
        s for s in run_spans if _WORKFLOW_NAME_RE.match(s.get("name", ""))
    ]
    if workflow_spans:
        wf = workflow_spans[0]
        execution_time_seconds = (
            wf.get("end_time_unix_nano", 0) - wf.get("start_time_unix_nano", 0)
        ) / 1_000_000_000.0
    else:
        ends = [s.get("end_time_unix_nano", 0) for s in run_spans]
        starts = [s.get("start_time_unix_nano", 0) for s in run_spans]
        execution_time_seconds = (max(ends) - min(starts)) / 1_000_000_000.0

    return {
        "trace_id": trace_id,
        "node_path": node_path,
        "tool_calls": tool_calls,
        "execution_time_seconds": round(execution_time_seconds, 3),
        "llm_call_count": len(llm_spans),
        "total_tokens": total_tokens,
        "tool_call_count": len(tool_calls),
        "final_output_text": final_output_text,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="JSONL of OTLP spans from local_otlp_receiver.py")
    p.add_argument("--output", help="Write normalized JSON here (default: stdout)")
    args = p.parse_args()

    spans = _parse_jsonl(Path(args.input))
    normalized = normalize(spans)
    out = json.dumps(normalized, indent=2)
    if args.output:
        Path(args.output).write_text(out)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
