#!/usr/bin/env bash
# install.sh - Monte Carlo Claude skills installer
#
# Downloads Monte Carlo Claude Code skills to ~/.claude/skills/
#
# Usage:
#   ./install.sh
#   bash <(curl -fsSL https://raw.githubusercontent.com/monte-carlo-data/monte-carlo-claude-plugin/main/install.sh)

set -euo pipefail

SKILLS_DIR="${HOME}/.claude/skills"
RAW_BASE="https://raw.githubusercontent.com/monte-carlo-data/mcd-skills/main"

echo "Installing Monte Carlo Claude Code skills..."

# safe-change
echo "  → monte-carlo-safe-change"
mkdir -p "${SKILLS_DIR}/monte-carlo-safe-change"
curl -fsSL -o "${SKILLS_DIR}/monte-carlo-safe-change/SKILL.md" \
  "${RAW_BASE}/safe-change/SKILL.md"

# generate-validation-notebook
echo "  → monte-carlo-generate-validation-notebook"
mkdir -p "${SKILLS_DIR}/monte-carlo-generate-validation-notebook/scripts"
curl -fsSL -o "${SKILLS_DIR}/monte-carlo-generate-validation-notebook/SKILL.md" \
  "${RAW_BASE}/generate-validation-notebook/SKILL.md"
curl -fsSL -o "${SKILLS_DIR}/monte-carlo-generate-validation-notebook/scripts/generate_notebook_url.py" \
  "${RAW_BASE}/generate-validation-notebook/scripts/generate_notebook_url.py"
curl -fsSL -o "${SKILLS_DIR}/monte-carlo-generate-validation-notebook/scripts/resolve_dbt_schema.py" \
  "${RAW_BASE}/generate-validation-notebook/scripts/resolve_dbt_schema.py"

echo ""
echo "Done. Skills installed to ${SKILLS_DIR}/"
echo ""
echo "Next: configure the Monte Carlo MCP server to use safe-change."
echo "See https://github.com/monte-carlo-data/mcd-skills/blob/main/safe-change/README.md#setup"
