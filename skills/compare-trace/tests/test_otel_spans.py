#!/usr/bin/env python3
"""
Smoke test for ``sources/otel_spans.py`` — feeds each fixture JSONL into the
normalizer and asserts the resulting dict matches the expected shape.

Two fixtures cover the two tool-call dialects the normalizer has to handle:

- ``bedrock_dialect.jsonl`` — Traceloop's Bedrock instrumentor emits tool
  calls only under ``gen_ai.prompt.*.tool_calls.*`` on the NEXT LLM call
  (never on the completion that produced them). Exercises the
  prompt-history extraction path.
- ``completion_dialect.jsonl`` — OpenAI / Anthropic-native instrumentations
  emit tool calls under ``gen_ai.completion.*.tool_calls.*``. Exercises
  the completion-extraction path and the dedup-by-id behavior (the same
  call also appears in the next prompt's history; the normalizer must
  collapse to one).

Run:
    python3 skills/compare-trace/tests/test_otel_spans.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent
SKILL_ROOT = TESTS_DIR.parent
NORMALIZER = SKILL_ROOT / "scripts" / "sources" / "otel_spans.py"
FIXTURES_DIR = TESTS_DIR / "fixtures"

PASSED = 0
FAILED = 0


def run_normalizer(fixture: str) -> dict:
    """Run sources/otel_spans.py against a fixture, return parsed JSON."""
    result = subprocess.run(
        [sys.executable, str(NORMALIZER), str(FIXTURES_DIR / fixture)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)


def check(label: str, condition: bool, hint: str = "") -> None:
    """Record a single check; raise on failure so pytest sees per-test fails."""
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {label}")
        return
    FAILED += 1
    print(f"  FAIL  {label}" + (f" -- {hint}" if hint else ""))
    raise AssertionError(label + (f" ({hint})" if hint else ""))


def test_bedrock_dialect() -> None:
    """Bedrock: tool_calls live under gen_ai.prompt.*.tool_calls.* in later spans."""
    print("test_bedrock_dialect:")
    out = run_normalizer("bedrock_dialect.jsonl")

    check("trace_id picked", out["trace_id"] == "trace01", out["trace_id"])
    check(
        "node_path in start-time order",
        out["node_path"] == ["initialization", "react_agent", "_route_after_react"],
        repr(out["node_path"]),
    )
    check("llm_call_count = 2", out["llm_call_count"] == 2, str(out["llm_call_count"]))
    check(
        "total_tokens summed across LLM spans",
        out["total_tokens"] == 350,
        f"expected 350 (120+230), got {out['total_tokens']}",
    )
    check(
        "execution_time_seconds from workflow root",
        out["execution_time_seconds"] == 10.0,
        str(out["execution_time_seconds"]),
    )
    check("tool_call_count = 1", out["tool_call_count"] == 1, str(out["tool_call_count"]))
    check(
        "tool call extracted from prompt.*.tool_calls.*",
        len(out["tool_calls"]) == 1
        and out["tool_calls"][0]["name"] == "get_warehouses"
        and out["tool_calls"][0]["id"] == "tid_1"
        and out["tool_calls"][0]["args"] == {},
        repr(out["tool_calls"]),
    )
    check(
        "final_output_text from last LLM span's completion",
        out["final_output_text"] == "You have 3 warehouses with use cases.",
        repr(out["final_output_text"]),
    )


def test_completion_dialect() -> None:
    """OpenAI/Anthropic: tool_calls under completion.* on the producing span;
    the SAME call echoes back under prompt.* on the next span — must dedup."""
    print("test_completion_dialect:")
    out = run_normalizer("completion_dialect.jsonl")

    check("trace_id picked", out["trace_id"] == "trace02", out["trace_id"])
    check(
        "node_path",
        out["node_path"] == ["agent_node"],
        repr(out["node_path"]),
    )
    check("llm_call_count = 2", out["llm_call_count"] == 2, str(out["llm_call_count"]))
    check(
        "total_tokens uses gen_ai.usage.total_tokens",
        out["total_tokens"] == 165,
        f"expected 165 (75+90), got {out['total_tokens']}",
    )
    check(
        "execution_time_seconds",
        out["execution_time_seconds"] == 5.0,
        str(out["execution_time_seconds"]),
    )
    check(
        "tool_calls deduped by id across completion + prompt-history",
        out["tool_call_count"] == 1,
        f"expected 1 deduped call, got {out['tool_call_count']}: {out['tool_calls']}",
    )
    check(
        "deduped tool call retains parsed args",
        len(out["tool_calls"]) == 1
        and out["tool_calls"][0]["name"] == "do_thing"
        and out["tool_calls"][0]["id"] == "call_abc"
        and out["tool_calls"][0]["args"] == {"target": "foo", "force": True},
        repr(out["tool_calls"]),
    )
    check(
        "final_output_text from last LLM span",
        out["final_output_text"] == "All done — the thing was processed.",
        repr(out["final_output_text"]),
    )


def main() -> None:
    """Standalone runner — invokes each test with its own try/except so we
    get a single PASSED/FAILED summary instead of stopping at the first fail.
    pytest invokes ``test_*`` directly and gets per-test failures via the
    AssertionError raised in ``check()``."""
    for fn in [test_bedrock_dialect, test_completion_dialect]:
        try:
            fn()
        except AssertionError as e:
            print(f"  (test {fn.__name__} aborted: {e})")
    print()
    print(f"PASSED: {PASSED}")
    print(f"FAILED: {FAILED}")
    if FAILED:
        sys.exit(1)


if __name__ == "__main__":
    main()
