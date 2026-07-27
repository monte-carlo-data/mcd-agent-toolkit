"""Latency and resource-usage diff for two agent runs.

Compares execution time, LLM call count, total tokens, tool call count.
Reports per-metric ratios; flags regressions above ``regression_threshold``.
Ported from monte-carlo-data/ai-agent#1236.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MetricComparison:
    field_name: str
    baseline_value: float
    candidate_value: float
    ratio: float
    is_regression: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "baseline_value": self.baseline_value,
            "candidate_value": self.candidate_value,
            "ratio": self.ratio if self.ratio != float("inf") else "inf",
            "is_regression": self.is_regression,
        }


@dataclass
class LatencyDiffResult:
    metrics: list[MetricComparison]
    overall_assessment: str = "neutral"
    regressions: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.regressions = [m.field_name for m in self.metrics if m.is_regression]
        if self.regressions:
            self.overall_assessment = "regressed"
        elif any(m.ratio < 1.0 for m in self.metrics):
            self.overall_assessment = "improved"
        else:
            self.overall_assessment = "neutral"

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": [m.to_dict() for m in self.metrics],
            "overall_assessment": self.overall_assessment,
            "regressions": self.regressions,
        }


_METRICS = [
    "execution_time_seconds",
    "llm_call_count",
    "total_tokens",
    "tool_call_count",
]


def _compute_ratio(baseline: float, candidate: float) -> float:
    if baseline == 0:
        return 1.0 if candidate == 0 else float("inf")
    return candidate / baseline


def compare_latency(
    baseline: dict,
    candidate: dict,
    regression_threshold: float = 1.5,
) -> LatencyDiffResult:
    """``baseline`` and ``candidate`` follow the normalized trace JSON shape.

    ``tool_call_count`` is derived from ``len(tool_calls)`` if not present.
    """

    def _extract(snapshot: dict, key: str) -> float:
        if key == "tool_call_count":
            return float(len(snapshot.get("tool_calls", []) or []))
        return float(snapshot.get(key, 0) or 0)

    comparisons: list[MetricComparison] = []
    for key in _METRICS:
        b = _extract(baseline, key)
        c = _extract(candidate, key)
        ratio = _compute_ratio(b, c)
        comparisons.append(
            MetricComparison(
                field_name=key,
                baseline_value=b,
                candidate_value=c,
                ratio=ratio,
                is_regression=ratio > regression_threshold,
            )
        )
    return LatencyDiffResult(metrics=comparisons)
