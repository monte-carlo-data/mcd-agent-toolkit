"""Tool-call sequence + argument diff for two agent runs.

v0.3: compares ordered sequences of tool names (Levenshtein) AND argument
dicts (top-level keys) for matched tool calls. Argument-level diff is enabled
when callers pass tool_calls with populated ``args`` dicts.

Sequence math and matching logic ported from monte-carlo-data/ai-agent#1236.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ArgumentChange:
    """One matched tool-call pair whose arg keys differ.

    `position_baseline` / `position_candidate` are the indices into the
    respective sequences (useful for the HTML rendering). The ``*_values``
    dicts carry the actual values that the renderer surfaces inline.
    """

    tool_name: str
    position_baseline: int
    position_candidate: int
    added_keys: list[str] = field(default_factory=list)
    removed_keys: list[str] = field(default_factory=list)
    changed_keys: list[str] = field(default_factory=list)
    added_values: dict[str, Any] = field(default_factory=dict)
    removed_values: dict[str, Any] = field(default_factory=dict)
    changed_values: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolCallDiff:
    baseline_tools: list[str]
    candidate_tools: list[str]
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    shared: list[str] = field(default_factory=list)
    edit_distance: int = 0
    similarity: float = 1.0
    argument_changes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _levenshtein(a: list[str], b: list[str]) -> int:
    m, n = len(a), len(b)
    if m < n:
        a, b = b, a
        m, n = n, m
    previous = list(range(n + 1))
    current = [0] * (n + 1)
    for i in range(1, m + 1):
        current[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            current[j] = min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + cost,
            )
        previous, current = current, previous
    return previous[n]


def _match_tools_by_proximity(
    baseline_calls: list[dict[str, Any]],
    candidate_calls: list[dict[str, Any]],
) -> list[tuple[int, int]]:
    """Match tool calls between baseline and candidate by name and position.

    For each tool name that appears in both sequences, greedily pairs calls by
    closest positional proximity (baseline index vs candidate index). Each
    call is matched at most once. Returns ``(baseline_index, candidate_index)``
    pairs, sorted by baseline index.

    Ported verbatim from monte-carlo-data/ai-agent#1236.
    """
    baseline_by_name: dict[str, list[int]] = defaultdict(list)
    candidate_by_name: dict[str, list[int]] = defaultdict(list)

    for i, call in enumerate(baseline_calls):
        baseline_by_name[call.get("name", "")].append(i)
    for j, call in enumerate(candidate_calls):
        candidate_by_name[call.get("name", "")].append(j)

    matches: list[tuple[int, int]] = []
    for name in baseline_by_name:
        if name not in candidate_by_name:
            continue
        b_indices = list(baseline_by_name[name])
        c_indices = list(candidate_by_name[name])

        used_c: set[int] = set()
        for bi in b_indices:
            best_ci: int | None = None
            best_dist: float = float("inf")
            for ci in c_indices:
                if ci in used_c:
                    continue
                dist = abs(bi - ci)
                if dist < best_dist:
                    best_dist = dist
                    best_ci = ci
            if best_ci is not None:
                matches.append((bi, best_ci))
                used_c.add(best_ci)

    matches.sort()
    return matches


def _compare_args(
    tool_name: str,
    baseline_idx: int,
    candidate_idx: int,
    baseline_args: dict[str, Any],
    candidate_args: dict[str, Any],
) -> ArgumentChange | None:
    """Compare two arg dicts at the top-level key granularity.

    Returns an ``ArgumentChange`` if anything differs, else ``None`` (so the
    caller can skip noise). Nested-dict diff is intentionally out of scope —
    a key whose value changes (including a nested dict that changed inside)
    surfaces as a ``changed_keys`` entry.

    Ported verbatim from monte-carlo-data/ai-agent#1236.
    """
    b_keys = set(baseline_args.keys())
    c_keys = set(candidate_args.keys())

    added_keys = sorted(c_keys - b_keys)
    removed_keys = sorted(b_keys - c_keys)
    changed_keys = sorted(k for k in b_keys & c_keys if baseline_args[k] != candidate_args[k])

    if not added_keys and not removed_keys and not changed_keys:
        return None

    return ArgumentChange(
        tool_name=tool_name,
        position_baseline=baseline_idx,
        position_candidate=candidate_idx,
        added_keys=added_keys,
        removed_keys=removed_keys,
        changed_keys=changed_keys,
        added_values={k: candidate_args[k] for k in added_keys},
        removed_values={k: baseline_args[k] for k in removed_keys},
        changed_values={
            k: {"baseline": baseline_args[k], "candidate": candidate_args[k]}
            for k in changed_keys
        },
    )


def compare_tool_calls(
    baseline_calls: list[dict[str, Any]],
    candidate_calls: list[dict[str, Any]],
) -> ToolCallDiff:
    """Compare two ordered tool call sequences from baseline and candidate runs.

    Each call is a dict with ``"name"`` (str) and ``"args"`` (dict). If ``args``
    is empty or missing for both sides, argument_changes will be empty too.
    """
    baseline_tools = [c.get("name", "") for c in baseline_calls]
    candidate_tools = [c.get("name", "") for c in candidate_calls]

    baseline_set = set(baseline_tools)
    candidate_set = set(candidate_tools)

    edit_dist = _levenshtein(baseline_tools, candidate_tools)
    max_len = max(len(baseline_tools), len(candidate_tools))
    similarity = 1.0 - (edit_dist / max_len) if max_len > 0 else 1.0

    matches = _match_tools_by_proximity(baseline_calls, candidate_calls)
    argument_changes: list[dict[str, Any]] = []
    for bi, ci in matches:
        b_call = baseline_calls[bi]
        c_call = candidate_calls[ci]
        change = _compare_args(
            tool_name=b_call.get("name", ""),
            baseline_idx=bi,
            candidate_idx=ci,
            baseline_args=b_call.get("args", {}) or {},
            candidate_args=c_call.get("args", {}) or {},
        )
        if change is not None:
            argument_changes.append(change.to_dict())

    return ToolCallDiff(
        baseline_tools=baseline_tools,
        candidate_tools=candidate_tools,
        added=sorted(candidate_set - baseline_set),
        removed=sorted(baseline_set - candidate_set),
        shared=sorted(baseline_set & candidate_set),
        edit_distance=edit_dist,
        similarity=similarity,
        argument_changes=argument_changes,
    )
