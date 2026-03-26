# Skill Trigger Evals

This directory contains the trigger accuracy eval set for the `push-ingestion` skill.

## What it tests

Each case in `trigger-evals.json` is a realistic customer prompt with an expected outcome:
- `"trigger"` — the skill should activate for this message
- `"no-trigger"` — the skill should stay quiet

The eval runner asks Claude to act as a judge: given the skill's description and a user message, would the skill trigger? It compares the judge's answer against the expected outcome and reports overall accuracy.

## Running locally

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# From repo root:
python plugins/claude-code/push-ingestion/evals/run_evals.py

# Or from this directory:
python run_evals.py
```

Options:
```
--model      Claude model to use as judge (default: claude-sonnet-4-6)
--threshold  Minimum pass rate to exit 0   (default: 0.85)
--evals      Path to eval cases JSON       (default: trigger-evals.json)
```

## Adding new cases

Edit `trigger-evals.json` and add an entry to the `cases` array:

```json
{
  "id": "should-11",
  "prompt": "...",
  "expected": "trigger",
  "rationale": "Why this should trigger"
}
```

Use `should-XX` IDs for trigger cases and `should-not-XX` for no-trigger cases.
