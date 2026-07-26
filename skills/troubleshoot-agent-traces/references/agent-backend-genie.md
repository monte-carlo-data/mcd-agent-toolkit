# Backend: Databricks Genie (`databricks_genie`)

## What this backend is

A Databricks **Genie space** — a declarative NL2SQL agent. Users ask natural-language
questions; Genie generates and runs SQL against curated tables. This is the **coarsest
signal** of any backend: one record per turn, with the generated SQL as the only "tool
call". The investigation is SQL-and-lineage-centric, not span-tree-centric.

**CRITICAL: model and token fields are empty by design here — a token-usage, cost, or
model-swap question has no answer on this backend. Do not produce token/cost/model
findings.**

## Signal available here

- **Turn-grain records** shaped as a shallow two-level tree: a root turn span (the NL
  question and the answer) with one child per generated SQL statement — the whole story
  for a turn. Read turns through the conversation tools (`get_agent_trace` does not
  read this backend — it is a managed-store-only tool and errors here).
- **Native conversation grouping** — every span carries a real conversation id;
  `get_agent_conversations` / `get_agent_conversation` reconstruct multi-turn threads.
  **Conversation-grain evaluation monitors** run on this backend, so a breached eval
  alert may name whole conversations.
- **Conversation clustering** — when the account has clustering enabled for this space,
  Monte Carlo groups its conversations into an intent-cluster taxonomy, shown alongside
  the space's conversations in the Monte Carlo UI. No toolkit tool reads clusters
  directly: point the user at the cluster view to see which *kind* of questions a
  regression concentrates in, or hand off to `run_troubleshooting_agent`, which uses
  cluster-share shifts as evidence.
- **Per-turn failure status**, and for failed turns the **recorded Genie error** (a real
  error type and message captured by the collector) surfaced in the span's attributes —
  not just a generic failure wrapper.
- **The generated SQL itself** (consent-gated content) — what questions were asked, what
  SQL Genie wrote, whether that SQL failed or changed shape.
- **Volume and failure trends** — turns, conversations, failed turns, duration, via
  `get_agent_traces` aggregation.
- **A config surface** — the space's instructions, curated/annotated tables, and example
  SQL / benchmark questions are the platform analog of code history.

## Absent by design — do not chase

- **No model, no tokens** — always null. No cost or "expensive" framing applies.
- **No real span tree** — the two-level tree is fabricated for presentation. Do not
  analyze intra-trace execution structure, span ordering, or nesting depth.
- **No agent source code and no PRs** — a Genie space is declarative.
- **Eval scores are not in the spans** — quality scores are Monte Carlo–computed and
  live on the monitor/alert. The spans tell you what a turn *did*; the alert tells you
  what *scored* low. Don't hunt for a score field in trace data.
- **Private conversations may not be ingested** — reason over the ingested slice (the
  same slice the monitor evaluated), not necessarily every conversation in the space.

## Investigation approach

1. **Confirm the backend** — `get_alert_agent_classification` / `get_agent_metadata`.
2. **Run the lineage play FIRST (the primary root-cause move).** Identify the source
   tables the space's generated SQL queried, then check `get_alerts` for
   freshness/volume/schema incidents on those tables. An upstream data incident is the
   single most likely root cause of a wrong, empty, or failed Genie answer — and the
   bridge only Monte Carlo can draw. Lead with this.
3. **Compare BEFORE vs AFTER.** Incident window vs the prior baseline: turns,
   conversations, generated-SQL volume, failed turns, duration — **not tokens** — plus
   the daily activity trend. A step on a specific day points at a curated-table or
   instruction change that day.
4. **Look at WHAT happened — and rule out a false positive.** Start content-free: list
   conversations with turn/failure counts (`get_agent_conversations`), then drill into a
   flagged conversation's question / answer / generated SQL with
   `get_agent_conversation` (content is consent-gated). Genuine problem (wrong NL2SQL
   translation, unfiltered scan, error spike) vs false positive (a legitimately hard
   question, an expected spike, a too-tight threshold). When clustering is enabled for
   the space, localize first: a cluster whose share moved in the breach window tells
   you which kind of questions to sample (cluster view in the UI, or the automated
   run's cluster evidence).
5. **For FAILED turns, read the recorded error before hypothesizing.** The recorded
   error type/message in the failed turn's span attributes IS the literal root-cause
   signal (e.g. a schema-access error). Fall back to structural reasoning only when no
   recorded message exists (older collector installs).
6. **Diff the config surface** — instructions, curated/annotated tables and their column
   descriptions, example SQL — against the onset date.
7. For a full automated root-cause run, hand off to `run_troubleshooting_agent` and
   collect results with `get_troubleshooting_agent_results`.

## Gotchas

- **The recorded error beats the wrapper.** A failed turn may show a generic
  "run failed" label; the real recorded error type and text live in the span's
  attributes — always read those specific attributes, never settle for the wrapper.
- **Content is JSON-string shaped.** Prompt/completion content on this backend is stored
  as JSON strings, not structured fields — read the specific attribute you need (the
  question, the answer, one SQL statement) rather than pulling and parsing whole content
  blobs.
- **Consent gating is a fact to report, not a failure.** Question/answer/SQL text may be
  blocked by the account's data-sampling settings — say so and continue from
  volume/failure structure.
- **Schema questions are answered from the normalized vocabulary** — see the span-field
  reference below; do not run exploratory queries against the trace store to discover
  fields.
- **Fix language:** space instructions, curated/annotated tables and column
  descriptions, example SQL / benchmark questions, or resolving the source-table data
  incident. Never code changes, never model or token tuning.

## Cross-links

- Span-field vocabulary: `../../monitoring-advisor/references/agent-span-fields.md`
- Alert-type playbooks: `agent-alert-*.md`
