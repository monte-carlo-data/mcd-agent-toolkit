#!/bin/bash
set -e

echo "Running post-uninstall cleanup for Monte Carlo Safe Change plugin..."

SKILL_PATH="$HOME/.claude/skills/safe-change"
BACKUP_PATH="$SKILL_PATH.backup"
if [ -d "$BACKUP_PATH" ]; then
  echo "Restoring standalone safe-change skill from backup..."
  mv "$BACKUP_PATH" "$SKILL_PATH"
  echo "✓ Standalone skill restored."
else
  echo "No backup found. Install standalone skill from mcd-agent-toolkit/skills/ if needed."
fi

echo "✓ Post-uninstall cleanup complete."
echo "  Remove MCD_ID and MCD_TOKEN from your shell profile if no longer needed."
