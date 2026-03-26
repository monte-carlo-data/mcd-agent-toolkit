#!/usr/bin/env bash
# Installs the push-ingestion skill and /mc-* slash commands into Claude Code.
# Run from any directory — the script resolves its own location.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$PLUGIN_DIR/skills/push-ingestion"
COMMANDS_SRC="$PLUGIN_DIR/commands"

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
SKILLS_DIR="$CLAUDE_DIR/skills"
COMMANDS_DIR="$CLAUDE_DIR/commands"

echo "Installing push-ingestion skill..."

# Pre-flight check
[[ -d "$SKILL_SRC" ]] || { echo "ERROR: skill source not found: $SKILL_SRC"; exit 1; }

# Skill
mkdir -p "$SKILLS_DIR"
SKILL_DEST="$SKILLS_DIR/push-ingestion"
if [ -L "$SKILL_DEST" ] || [ -d "$SKILL_DEST" ]; then
  echo "  Skill already exists at $SKILL_DEST — skipping (remove it manually to reinstall)"
else
  ln -s "$SKILL_SRC" "$SKILL_DEST"
  echo "  Linked skill → $SKILL_DEST"
fi

# Commands
mkdir -p "$COMMANDS_DIR"
for cmd_file in "$COMMANDS_SRC"/*.md; do
  cmd_name="$(basename "$cmd_file")"
  dest="$COMMANDS_DIR/$cmd_name"
  if [ -L "$dest" ] || [ -f "$dest" ]; then
    echo "  Command /$cmd_name already exists — skipping"
  else
    ln -s "$cmd_file" "$dest"
    echo "  Linked /$cmd_name"
  fi
done

echo ""
echo "Done. Restart Claude Code to activate the skill and /mc-* commands."
