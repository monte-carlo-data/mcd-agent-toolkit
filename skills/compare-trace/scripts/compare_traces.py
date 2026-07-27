#!/usr/bin/env python3
"""Driver for the compare-trace skill.

Takes two normalized trace JSON files (baseline + candidate), runs the three
deterministic evaluators, optionally folds in LLM-eval results that Claude
ran inline, and writes a single-pair HTML report. Opens the report in the
default browser unless ``--no-open`` is passed.

Normalized trace JSON shape::

    {
      "trace_id": "<hex>",
      "label": "baseline|candidate|...",
      "node_path": ["node_a", "node_b", ...],
      "tool_calls": [{"name": "<tool>", "args": {}}, ...],
      "execution_time_seconds": 12.34,
      "llm_call_count": 5,
      "total_tokens": 1234,
      "prompt_tokens": 900,
      "completion_tokens": 334,
      "has_errors": false,
      "final_output_text": ""
    }

LLM-eval JSON shapes are documented in SKILL.md (Phase 4).
"""

from __future__ import annotations

import argparse
import html
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from evaluators.graph_path_diff import compare_graph_paths  # noqa: E402
from evaluators.latency_diff import compare_latency  # noqa: E402
from evaluators.tool_call_diff import compare_tool_calls  # noqa: E402


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return json.load(f)


def _open_in_browser(path: Path) -> None:
    url = f"file://{path.resolve()}"
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", url], check=False)
        elif system == "Linux":
            subprocess.run(["xdg-open", url], check=False)
        elif system == "Windows":
            subprocess.run(["start", url], shell=True, check=False)
    except FileNotFoundError:
        # Browser command not available; caller prints the path instead.
        pass


# ---------------------------------------------------------------------------
# Tab renderers (single-pair flavor, ported from PR #1236's html_renderer.py)
# ---------------------------------------------------------------------------


def _render_graph_tab(g) -> str:
    rows = ""
    if g.baseline_only_nodes:
        rows += (
            f'<tr><td class="removed">Baseline only</td>'
            f'<td>{html.escape(", ".join(g.baseline_only_nodes))}</td></tr>'
        )
    if g.candidate_only_nodes:
        rows += (
            f'<tr><td class="added">Candidate only</td>'
            f'<td>{html.escape(", ".join(g.candidate_only_nodes))}</td></tr>'
        )
    if g.shared_nodes:
        rows += (
            f'<tr><td>Shared</td>'
            f'<td>{html.escape(", ".join(g.shared_nodes))}</td></tr>'
        )
    return f"""
        <div class="signal-summary">
          <span>Jaccard (node set): <strong>{g.jaccard_similarity:.2f}</strong></span>
          <span>Ordering (LCS): <strong>{g.ordering_similarity:.2f}</strong></span>
          <span>Overall: <strong>{g.overall_similarity:.2f}</strong></span>
        </div>
        <table class="field-table"><thead><tr><th>Category</th><th>Nodes</th></tr></thead>
          <tbody>{rows or "<tr><td colspan='2'>Identical paths</td></tr>"}</tbody></table>
        <details style="margin-top:8px"><summary style="cursor:pointer;font-size:0.85rem;color:#666">Full paths</summary>
          <div class="raw-columns">
            <div class="raw-col"><h4>Baseline ({len(g.baseline_path)} nodes)</h4><pre>{html.escape(chr(10).join(g.baseline_path[:200]) or "(empty)")}</pre></div>
            <div class="raw-col"><h4>Candidate ({len(g.candidate_path)} nodes)</h4><pre>{html.escape(chr(10).join(g.candidate_path[:200]) or "(empty)")}</pre></div>
          </div>
        </details>"""


def _render_latency_tab(lat) -> str:
    rows = ""
    for m in lat.metrics:
        if m.baseline_value == 0 and m.candidate_value == 0:
            continue
        css = "field-changed" if m.is_regression else "field-unchanged"
        ratio_str = f"{m.ratio:.2f}x" if m.ratio != float("inf") else "inf"
        badge = (
            '<span class="badge-regressed">regressed</span>'
            if m.is_regression
            else ""
        )
        rows += f"""
          <tr class="{css}">
            <td>{html.escape(m.field_name)}</td>
            <td>{m.baseline_value:.1f}</td>
            <td>{m.candidate_value:.1f}</td>
            <td>{ratio_str}</td>
            <td>{badge}</td>
          </tr>"""

    assessment_css = {"regressed": "red", "improved": "green"}.get(
        lat.overall_assessment, ""
    )
    return f"""
        <div class="signal-summary">
          <span>Assessment: <strong class="{assessment_css}">{lat.overall_assessment.upper()}</strong></span>
        </div>
        <table class="field-table">
          <thead><tr><th>Metric</th><th>Baseline</th><th>Candidate</th><th>Ratio</th><th></th></tr></thead>
          <tbody>{rows or "<tr><td colspan='5'>No metrics</td></tr>"}</tbody>
        </table>"""


_VALUE_TRUNCATE = 80


def _format_arg_value(value: Any) -> tuple[str, str]:
    """Return (truncated_repr, full_repr) for an arg value.

    Both reprs are JSON-encoded for dict/list values so the rendering is
    stable across types. Truncated is 80 chars with an ellipsis suffix.
    """
    if isinstance(value, (dict, list)):
        full = json.dumps(value, sort_keys=True, default=str)
    elif value is None:
        full = "null"
    elif isinstance(value, bool):
        full = "true" if value else "false"
    else:
        full = str(value)
    if len(full) <= _VALUE_TRUNCATE:
        return full, full
    return full[:_VALUE_TRUNCATE] + "…", full


def _render_arg_diff_lines(ac: dict[str, Any]) -> str:
    """Build the per-row diff content (inline truncated values + expand toggle)."""
    inline_lines: list[str] = []
    full_lines: list[str] = []

    added_values = ac.get("added_values", {}) or {}
    removed_values = ac.get("removed_values", {}) or {}
    changed_values = ac.get("changed_values", {}) or {}

    for k in ac.get("added_keys", []) or []:
        v = added_values.get(k, "")
        trunc, full = _format_arg_value(v)
        inline_lines.append(
            f'<div class="added">+ <code>{html.escape(k)}</code>: '
            f'<code>{html.escape(trunc)}</code></div>'
        )
        full_lines.append(f'+ {k}: {full}')

    for k in ac.get("removed_keys", []) or []:
        v = removed_values.get(k, "")
        trunc, full = _format_arg_value(v)
        inline_lines.append(
            f'<div class="removed">- <code>{html.escape(k)}</code>: '
            f'<code>{html.escape(trunc)}</code></div>'
        )
        full_lines.append(f'- {k}: {full}')

    for k in ac.get("changed_keys", []) or []:
        pair = changed_values.get(k, {}) or {}
        b_val = pair.get("baseline", "")
        c_val = pair.get("candidate", "")
        b_trunc, b_full = _format_arg_value(b_val)
        c_trunc, c_full = _format_arg_value(c_val)
        inline_lines.append(
            f'<div>Δ <code>{html.escape(k)}</code>: '
            f'<code class="removed">{html.escape(b_trunc)}</code> → '
            f'<code class="added">{html.escape(c_trunc)}</code></div>'
        )
        full_lines.append(f'Δ {k}:\n  baseline:  {b_full}\n  candidate: {c_full}')

    inline_html = "".join(inline_lines)
    any_truncated = any(
        _format_arg_value(v)[0] != _format_arg_value(v)[1]
        for v in list(added_values.values()) + list(removed_values.values())
    ) or any(
        _format_arg_value(pair.get("baseline", ""))[0]
        != _format_arg_value(pair.get("baseline", ""))[1]
        or _format_arg_value(pair.get("candidate", ""))[0]
        != _format_arg_value(pair.get("candidate", ""))[1]
        for pair in changed_values.values()
    )
    if any_truncated:
        full_block = html.escape("\n".join(full_lines))
        inline_html += (
            '<details style="margin-top:4px"><summary '
            'style="cursor:pointer;font-size:0.72rem;color:#666">▸ show full values</summary>'
            f'<pre style="margin:4px 0;padding:8px;background:#f8f9fa;border-radius:4px;'
            f'font-size:0.75rem;white-space:pre-wrap;word-break:break-word">{full_block}</pre>'
            "</details>"
        )
    return inline_html


def _render_tool_call_tab(t) -> str:
    rows = ""
    if t.added:
        rows += (
            f'<tr><td class="added">+ Added tools</td>'
            f'<td>{html.escape(", ".join(t.added))}</td></tr>'
        )
    if t.removed:
        rows += (
            f'<tr><td class="removed">- Removed tools</td>'
            f'<td>{html.escape(", ".join(t.removed))}</td></tr>'
        )
    if t.shared:
        rows += (
            f'<tr><td>Shared tools</td>'
            f'<td>{html.escape(", ".join(t.shared))}</td></tr>'
        )

    arg_rows = ""
    for ac in t.argument_changes:
        diff_html = _render_arg_diff_lines(ac)
        pos = f"#{ac.get('position_baseline', '?')} → #{ac.get('position_candidate', '?')}"
        arg_rows += (
            f'<tr><td><code>{html.escape(ac.get("tool_name", ""))}</code></td>'
            f'<td style="color:#666;font-size:0.78rem;white-space:nowrap">{pos}</td>'
            f'<td>{diff_html}</td></tr>'
        )

    arg_section = (
        '<h4 style="margin-top:14px;font-size:0.95rem">Argument changes (matched calls)</h4>'
        '<table class="field-table">'
        '<thead><tr><th>Tool</th><th>Positions</th><th>Diff</th></tr></thead>'
        f'<tbody>{arg_rows}</tbody></table>'
        if arg_rows
        else (
            '<div style="margin-top:8px;padding:8px 12px;background:#f0fdf4;'
            'border-radius:4px;font-size:0.8rem;color:#166534">'
            "No argument-level changes for matched calls "
            "(or tool_calls were captured without args)."
            "</div>"
        )
    )

    return f"""
        <div class="signal-summary">
          <span>Edit distance: <strong>{t.edit_distance}</strong></span>
          <span>Similarity: <strong>{t.similarity:.2f}</strong></span>
          <span>Baseline: {len(t.baseline_tools)} calls</span>
          <span>Candidate: {len(t.candidate_tools)} calls</span>
          <span>Arg-diff matches: <strong>{len(t.argument_changes)}</strong></span>
        </div>
        <table class="field-table"><thead><tr><th>Change</th><th>Tools</th></tr></thead>
          <tbody>{rows or "<tr><td colspan='2'>Identical tool sequences</td></tr>"}</tbody></table>
        {arg_section}
        <details style="margin-top:8px"><summary style="cursor:pointer;font-size:0.85rem;color:#666">Full sequences</summary>
          <div class="raw-columns">
            <div class="raw-col"><h4>Baseline</h4><pre>{html.escape(chr(10).join(t.baseline_tools[:200]) or "(empty)")}</pre></div>
            <div class="raw-col"><h4>Candidate</h4><pre>{html.escape(chr(10).join(t.candidate_tools[:200]) or "(empty)")}</pre></div>
          </div>
        </details>"""


def _render_semantic_tab(s: dict | None, has_completions: bool) -> str:
    if s is None:
        msg = (
            "Skipped — no final-completion text available for one or both traces. "
            "Pass <code>--conversation-ids</code> when invoking the skill, or re-run "
            "with the conversation IDs from the MC UI."
        ) if not has_completions else (
            "Skipped — Claude did not run the inline semantic diff for this comparison."
        )
        return f'<p style="color:#666;font-size:0.9rem">{msg}</p>'

    verdict = s.get("verdict", "unknown")
    verdict_css = {
        "regression": "red",
        "improvement": "green",
        "preserved": "green",
        "mixed": "orange",
    }.get(verdict, "")

    lost = s.get("lost_findings") or []
    added = s.get("added_findings") or []

    def _bullets(items: list[str], css: str) -> str:
        if not items:
            return ""
        return (
            '<ul style="margin:4px 0 0 16px;padding:0">'
            + "".join(
                f'<li class="{css}" style="margin:2px 0">{html.escape(str(i))}</li>'
                for i in items[:10]
            )
            + ("<li>…</li>" if len(items) > 10 else "")
            + "</ul>"
        )

    return f"""
        <div class="signal-summary">
          <span>Overall verdict: <strong class="{verdict_css}">{verdict.upper()}</strong></span>
          <span>Semantic similarity: <strong>{float(s.get("similarity_score", 0.0)):.2f}</strong></span>
        </div>
        <div style="background:#f8f9fa;padding:8px 12px;border-radius:4px;font-size:0.9rem;margin-bottom:12px">
          {html.escape(s.get("explanation", "") or "")}
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
          <div><strong class="removed">Lost in candidate ({len(lost)})</strong>{_bullets(lost, "removed")}</div>
          <div><strong class="added">Added in candidate ({len(added)})</strong>{_bullets(added, "added")}</div>
        </div>"""


def _render_entities_tab(f: dict | None, has_completions: bool) -> str:
    if f is None:
        msg = (
            "Skipped — no final-completion text available for one or both traces."
        ) if not has_completions else (
            "Skipped — Claude did not run the inline entity overlap for this comparison."
        )
        return f'<p style="color:#666;font-size:0.9rem">{msg}</p>'

    per_type = f.get("per_type_jaccard", {}) or {}
    shared = f.get("shared", {}) or {}
    b_only = f.get("baseline_only", {}) or {}
    c_only = f.get("candidate_only", {}) or {}

    def _chips(items: list[str], css: str, limit: int = 5) -> str:
        if not items:
            return ""
        tags = " ".join(
            f'<code class="{css}">{html.escape(str(i)[:60])}</code>' for i in items[:limit]
        )
        suffix = f" +{len(items) - limit} more" if len(items) > limit else ""
        return tags + suffix

    rows = ""
    for entity_type in sorted(per_type):
        jaccard = float(per_type.get(entity_type, 0.0))
        css = "field-changed" if jaccard < 1.0 else "field-unchanged"
        details = ""
        s_items = shared.get(entity_type, []) or []
        b_items = b_only.get(entity_type, []) or []
        c_items = c_only.get(entity_type, []) or []
        if s_items:
            details += f'<div><strong>Shared ({len(s_items)}):</strong> {_chips(s_items, "entity-shared")}</div>'
        if b_items:
            details += f'<div><strong>Baseline only ({len(b_items)}):</strong> {_chips(b_items, "entity-removed")}</div>'
        if c_items:
            details += f'<div><strong>Candidate only ({len(c_items)}):</strong> {_chips(c_items, "entity-added")}</div>'
        rows += f"""
          <tr class="{css}">
            <td>{html.escape(entity_type)}</td>
            <td>{jaccard:.2f}</td>
            <td>{details or "-"}</td>
          </tr>"""

    overall = float(f.get("overall_jaccard", 0.0))
    return f"""
        <div class="signal-summary">
          <span>Overall entity overlap: <strong>{overall:.2f}</strong></span>
        </div>
        <table class="field-table">
          <thead><tr><th>Entity Type</th><th>Jaccard</th><th>Details</th></tr></thead>
          <tbody>{rows or "<tr><td colspan='3'>No entities extracted</td></tr>"}</tbody>
        </table>"""


# ---------------------------------------------------------------------------
# Top-level renderer
# ---------------------------------------------------------------------------


def render_html(
    baseline: dict,
    candidate: dict,
    graph,
    latency,
    tools,
    semantic: dict | None,
    entities: dict | None,
    narrative: str,
    output_path: Path,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    baseline_label = baseline.get("label") or "baseline"
    candidate_label = candidate.get("label") or "candidate"
    baseline_id = baseline.get("trace_id", "")
    candidate_id = candidate.get("trace_id", "")

    has_completions = bool(
        baseline.get("final_output_text") and candidate.get("final_output_text")
    )

    semantic_section = _render_semantic_tab(semantic, has_completions)
    graph_section = _render_graph_tab(graph)
    latency_section = _render_latency_tab(latency)
    entities_section = _render_entities_tab(entities, has_completions)
    tools_section = _render_tool_call_tab(tools)

    n_regressed = sum(1 for m in latency.metrics if m.is_regression)
    latency_color = "red" if n_regressed > 0 else "green"
    avg_semantic = (
        float(semantic.get("similarity_score", 0.0)) if semantic else 0.0
    )
    avg_entities = (
        float(entities.get("overall_jaccard", 0.0)) if entities else 0.0
    )

    semantic_stat = (
        f'<div class="stat"><div class="stat-value">{avg_semantic:.2f}</div>'
        f'<div class="stat-label">Semantic Similarity</div></div>'
        if semantic else ""
    )
    entities_stat = (
        f'<div class="stat"><div class="stat-value">{avg_entities:.2f}</div>'
        f'<div class="stat-label">Entity Overlap</div></div>'
        if entities else ""
    )

    baseline_raw_pre = html.escape(
        (baseline.get("final_output_text") or "(no completion text)")[:8000]
    )
    candidate_raw_pre = html.escape(
        (candidate.get("final_output_text") or "(no completion text)")[:8000]
    )

    body = f"""
<h1>Trace Comparison</h1>
<div class="meta">
  Generated {timestamp} | <strong>{html.escape(baseline_label)}</strong>
  (<code>{html.escape(baseline_id)}</code>)
  vs <strong>{html.escape(candidate_label)}</strong>
  (<code>{html.escape(candidate_id)}</code>)
</div>

<div class="corpus-summary">
  <h2>Summary</h2>
  <div class="stats">
    <div class="stat">
      <div class="stat-value">{graph.overall_similarity:.2f}</div>
      <div class="stat-label">Graph Similarity</div>
    </div>
    <div class="stat">
      <div class="stat-value">{tools.similarity:.2f}</div>
      <div class="stat-label">Tool Similarity</div>
    </div>
    <div class="stat">
      <div class="stat-value {latency_color}">{n_regressed}</div>
      <div class="stat-label">Latency Regressed</div>
    </div>
    {semantic_stat}
    {entities_stat}
  </div>
  <div class="llm-narrative">{html.escape(narrative or "(no narrative provided)")}</div>
</div>

<div class="scenario-card expanded">
  <div class="scenario-body">
    <div class="tabs">
      <div class="tab-buttons">
        <button class="tab-btn active" onclick="switchTab(this, 'card', 'semantic')">Semantic Diff</button>
        <button class="tab-btn" onclick="switchTab(this, 'card', 'graph')">Graph Path</button>
        <button class="tab-btn" onclick="switchTab(this, 'card', 'latency')">Latency &amp; Tokens</button>
        <button class="tab-btn" onclick="switchTab(this, 'card', 'entities')">Entity Overlap</button>
        <button class="tab-btn" onclick="switchTab(this, 'card', 'tools')">Tool Calls</button>
      </div>
      <div class="tab-content" id="card-semantic">{semantic_section}</div>
      <div class="tab-content" id="card-graph" style="display:none">{graph_section}</div>
      <div class="tab-content" id="card-latency" style="display:none">{latency_section}</div>
      <div class="tab-content" id="card-entities" style="display:none">{entities_section}</div>
      <div class="tab-content" id="card-tools" style="display:none">{tools_section}</div>
    </div>
    <details class="raw-data">
      <summary>Final completion text (both traces)</summary>
      <div class="raw-columns">
        <div class="raw-col"><h4>Baseline</h4><pre>{baseline_raw_pre}</pre></div>
        <div class="raw-col"><h4>Candidate</h4><pre>{candidate_raw_pre}</pre></div>
      </div>
    </details>
  </div>
</div>
"""

    html_doc = _TEMPLATE.replace("{{BODY}}", body)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_doc)
    return output_path


_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Monte Carlo Trace Comparison</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f5f5f5; color: #333; padding: 24px; max-width: 1200px; margin: 0 auto; }
  h1 { font-size: 1.5rem; margin-bottom: 4px; }
  .meta { color: #666; font-size: 0.85rem; margin-bottom: 20px; }
  .meta code { background: #eef; padding: 1px 6px; border-radius: 4px; font-size: 0.78rem; }
  .corpus-summary { background: #fff; border: 1px solid #ddd; border-radius: 8px;
                    padding: 20px; margin-bottom: 24px; }
  .corpus-summary h2 { font-size: 1.1rem; margin-bottom: 12px; }
  .stats { display: flex; gap: 24px; margin-bottom: 16px; flex-wrap: wrap; }
  .stat { text-align: center; min-width: 110px; }
  .stat-value { font-size: 1.8rem; font-weight: 700; }
  .stat-label { font-size: 0.7rem; color: #666; text-transform: uppercase; }
  .stat-value.green { color: #16a34a; }
  .stat-value.orange { color: #ea580c; }
  .stat-value.red { color: #dc2626; }
  .llm-narrative { background: #f8f9fa; padding: 12px; border-radius: 4px;
                   font-size: 0.9rem; line-height: 1.5; white-space: pre-wrap; }
  .scenario-card { background: #fff; border: 1px solid #ddd; border-radius: 8px;
                   margin-bottom: 12px; overflow: hidden; }
  .scenario-body { padding: 20px; }
  .tabs { margin-bottom: 16px; }
  .tab-buttons { display: flex; gap: 4px; margin-bottom: 12px; border-bottom: 2px solid #eee; }
  .tab-btn { padding: 8px 16px; border: none; background: none; cursor: pointer;
             font-size: 0.85rem; color: #666; border-bottom: 2px solid transparent;
             margin-bottom: -2px; transition: all 0.2s; }
  .tab-btn:hover { color: #333; }
  .tab-btn.active { color: #2563eb; border-bottom-color: #2563eb; font-weight: 600; }
  .tab-content { min-height: 80px; }
  .signal-summary { display: flex; gap: 20px; padding: 8px 0 12px; font-size: 0.85rem;
                    color: #555; flex-wrap: wrap; }
  .signal-summary strong { color: #333; }
  .field-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  .field-table th { text-align: left; padding: 8px; border-bottom: 2px solid #ddd; font-weight: 600; }
  .field-table td { padding: 8px; border-bottom: 1px solid #eee; vertical-align: top; }
  .field-unchanged td { color: #999; }
  .field-changed td { background: #fffbeb; }
  .badge-regressed { background: #fee2e2; color: #991b1b; padding: 1px 6px;
                     border-radius: 6px; font-size: 0.75rem; }
  .added { color: #16a34a; }
  .removed { color: #dc2626; }
  code.entity-shared { background: #f0fdf4; color: #166534; padding: 1px 5px;
                       border-radius: 4px; font-size: 0.8rem; margin: 1px; display: inline-block; }
  code.entity-removed { background: #fef2f2; color: #991b1b; padding: 1px 5px;
                        border-radius: 4px; font-size: 0.8rem; margin: 1px; display: inline-block; }
  code.entity-added { background: #eff6ff; color: #1e40af; padding: 1px 5px;
                      border-radius: 4px; font-size: 0.8rem; margin: 1px; display: inline-block; }
  .green { color: #16a34a; }
  .red { color: #dc2626; }
  .orange { color: #ea580c; }
  .raw-data { margin-top: 16px; }
  .raw-data summary { cursor: pointer; font-size: 0.85rem; color: #666; padding: 8px 0; }
  .raw-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .raw-col h4 { font-size: 0.8rem; margin-bottom: 8px; color: #666; }
  .raw-col pre { background: #f8f9fa; padding: 12px; border-radius: 4px;
                 font-size: 0.75rem; overflow-x: auto; max-height: 400px;
                 overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
</style>
<script>
function switchTab(btn, cardId, tabName) {
  const card = btn.closest('.scenario-card');
  card.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  card.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
  btn.classList.add('active');
  document.getElementById(cardId + '-' + tabName).style.display = 'block';
}
</script>
</head>
<body>
{{BODY}}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", required=True, type=Path, help="Baseline trace JSON path")
    parser.add_argument("--candidate", required=True, type=Path, help="Candidate trace JSON path")
    parser.add_argument("--semantic", type=Path, help="Optional semantic-diff JSON")
    parser.add_argument("--entities", type=Path, help="Optional entity-overlap JSON")
    parser.add_argument("--narrative", type=Path, help="Optional plaintext corpus narrative")
    parser.add_argument("--output", required=True, type=Path, help="HTML output path")
    parser.add_argument("--no-open", action="store_true", help="Do not open the report in a browser")
    args = parser.parse_args(argv)

    baseline = _load_json(args.baseline)
    candidate = _load_json(args.candidate)

    graph = compare_graph_paths(
        baseline.get("node_path", []) or [],
        candidate.get("node_path", []) or [],
    )
    latency = compare_latency(baseline, candidate)
    tools = compare_tool_calls(
        baseline.get("tool_calls", []) or [],
        candidate.get("tool_calls", []) or [],
    )

    semantic = _load_json(args.semantic) if args.semantic and args.semantic.exists() else None
    entities = _load_json(args.entities) if args.entities and args.entities.exists() else None
    narrative = (
        args.narrative.read_text().strip()
        if args.narrative and args.narrative.exists()
        else ""
    )

    output = render_html(
        baseline=baseline,
        candidate=candidate,
        graph=graph,
        latency=latency,
        tools=tools,
        semantic=semantic,
        entities=entities,
        narrative=narrative,
        output_path=args.output,
    )
    print(f"Wrote report: {output}")
    if not args.no_open:
        _open_in_browser(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
