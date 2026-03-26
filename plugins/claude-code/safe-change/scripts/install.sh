#!/bin/bash
set -e

echo "Running post-install cleanup for Monte Carlo Safe Change plugin..."

# Remove standalone safe-change skill if present (superseded by plugin)
SKILL_PATH="$HOME/.claude/skills/safe-change"
if [ -d "$SKILL_PATH" ]; then
  echo "Backing up and removing standalone safe-change skill (now bundled in plugin)..."
  cp -r "$SKILL_PATH" "$SKILL_PATH.backup"
  rm -rf "$SKILL_PATH"
  echo "Backup saved to $SKILL_PATH.backup"
fi

echo "✓ Post-install cleanup complete."
echo "  Ensure MCD_ID and MCD_TOKEN are set in your shell profile."
echo "  Restart Claude Code to activate."
