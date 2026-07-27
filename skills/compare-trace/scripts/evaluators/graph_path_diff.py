"""Graph path diff for two agent runs.

Jaccard on visited node sets + LCS/max for ordering similarity. Neither side
is ground truth. Ported from monte-carlo-data/ai-agent#1236.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GraphPathDiff:
    baseline_path: list[str]
    candidate_path: list[str]
    baseline_only_nodes: list[str] = field(default_factory=list)
    candidate_only_nodes: list[str] = field(default_factory=list)
    shared_nodes: list[str] = field(default_factory=list)
    jaccard_similarity: float = 1.0
    ordering_similarity: float = 1.0
    overall_similarity: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _lcs_length(a: list[str], b: list[str]) -> int:
    m, n = len(a), len(b)
    if m == 0 or n == 0:
        return 0
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, [0] * (n + 1)
    return prev[n]


def compare_graph_paths(
    baseline_path: list[str],
    candidate_path: list[str],
) -> GraphPathDiff:
    baseline_set = set(baseline_path)
    candidate_set = set(candidate_path)

    shared = baseline_set & candidate_set
    baseline_only = baseline_set - candidate_set
    candidate_only = candidate_set - baseline_set
    union = baseline_set | candidate_set

    jaccard = len(shared) / len(union) if union else 1.0

    max_len = max(len(baseline_path), len(candidate_path))
    ordering = _lcs_length(baseline_path, candidate_path) / max_len if max_len else 1.0

    return GraphPathDiff(
        baseline_path=baseline_path,
        candidate_path=candidate_path,
        baseline_only_nodes=sorted(baseline_only),
        candidate_only_nodes=sorted(candidate_only),
        shared_nodes=sorted(shared),
        jaccard_similarity=jaccard,
        ordering_similarity=ordering,
        overall_similarity=(jaccard + ordering) / 2.0,
    )
