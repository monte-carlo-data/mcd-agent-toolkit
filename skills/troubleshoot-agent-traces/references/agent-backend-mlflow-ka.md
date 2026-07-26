# Backend: Databricks Knowledge Assistant / Agent Bricks (`databricks_mlflow_ka`)

## What this backend is

A **no-code** Agent Bricks Knowledge Assistant — a RAG assistant over document sets,
configured entirely through the Databricks UI. Each trace is one Q&A turn: the root span
carries the user's question and the final answer, and retriever spans carry the document
chunks the answer was grounded on. Its behavior is driven by its configuration — the
assistant's instructions and its **knowledge sources** — so the investigation centers on
retrieval grounding and document quality, not on code or models.

**CRITICAL: model and token fields are empty by design here — a token-usage, cost, or
model-swap question has no answer on this backend. Never chase token anomalies.**

## Signal available here

- **Per-turn traces** — each trace is one turn: a root span with the question and final
  answer, chain steps, and retriever tool-call spans. (`get_agent_trace` does not read
  this backend — it errors; span-grain detail comes from `run_troubleshooting_agent`,
  and manual reads work at turn grain via `get_agent_traces`.)
- **Retrieval grounding (the differentiator)** — the retriever spans' tool-call output
  holds the retrieved document chunks. What was asked, what was retrieved, and whether
  the answer was grounded in it is THE signal on this backend. Chunk content is
  consent-gated; retrieval counts and structure are always readable.
- **Failure status per span** — failed turns carry a Knowledge-Assistant-specific error
  marker; error rates and failed-turn trends are readable via `get_agent_traces`.
- **Volume and latency trends** — turns, retrievals, failed turns, duration, via
  `get_agent_traces` aggregation.
- **A config surface** — instructions plus the knowledge sources (the document sets it
  retrieves from), the platform analog of code history.

## Absent by design — do not chase

- **No model, no tokens** — always null. No cost or model-swap framing applies.
- **No agent source code and no PRs** — the assistant is configured, not coded.
- **Conversation grouping is usually absent** — `conversation_id` is frequently null;
  each trace is then a standalone turn. Do not rely on conversation reads
  (`get_agent_conversations` / `get_agent_conversation` may come back empty — that is
  expected, not a data problem; work at turn grain with `get_agent_traces` instead).
- **Eval scores are not in the spans** — quality scores are Monte Carlo–computed and
  live on the monitor/alert.
- **No SQL and no lineage** — a Knowledge Assistant generates no SQL, so there are no
  source tables to extract from queries; retrieval grounding is the analogous
  root-cause bridge.

## Investigation approach

1. **Confirm the backend** — `get_alert_agent_classification` / `get_agent_metadata`.
2. **Inspect the retrieval grounding FIRST (the primary root-cause move).** For the
   failing or low-scored turns, look at what the retriever spans fetched. Missing,
   stale, or off-topic chunks point at the knowledge source — a document set that
   changed, went stale, or lost coverage — not at the assistant itself. This is the KA
   analogue of tracing a wrong answer back to its data source.
3. **Compare BEFORE vs AFTER.** Incident window vs the prior baseline: turns, traces,
   retrievals, failed turns, duration — **not tokens**. A step on a specific day points
   at a knowledge-source or config change that day.
4. **Look at WHAT happened — and rule out a false positive.** Read the failing turns
   (and, when consent allows, the actual question/answer pairs). Genuine problem (bad
   grounding, real error spike) vs false positive (legitimately hard questions, an
   expected spike, a too-tight threshold). A benign breach is a finding — say so and
   recommend adjusting the monitor.
5. **Diff the config surface against the onset** — the instructions and the list of
   knowledge sources. Check `get_alerts` for data incidents on the tables/documents
   behind the knowledge sources.
6. For a full automated root-cause run, hand off to `run_troubleshooting_agent` and
   collect results with `get_troubleshooting_agent_results`.

## Gotchas

- **Never produce PR, token, cost, or model findings.** Evidence must be about the
  retrieval grounding, the failure/volume trend, or the assistant's configuration.
- **Consent gating is a fact to report, not a failure.** Question/answer text and
  retrieved chunks may be blocked by the account's data-sampling settings — say so and
  continue from retrieval counts and failure structure.
- **Don't lean on conversation ids** — treat each trace as a standalone turn unless the
  data proves otherwise.
- **Schema questions are answered from the normalized vocabulary** — see the span-field
  reference below; never run exploratory queries against the trace store to discover
  fields.
- **Fix language:** adjust the assistant's instructions, refresh or fix a knowledge
  source, or resolve the data incident behind it. Verification steps are grounding
  checks ("inspect the retrieved chunks for the failing turns", "diff the knowledge
  sources against the onset date") — never "review the PR" or model/token tuning.

## Cross-links

- Span-field vocabulary: `../../monitoring-advisor/references/agent-span-fields.md`
- Alert-type playbooks: `agent-alert-*.md`
