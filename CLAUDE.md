# Agent Instructions

## Versioning

When committing to `main` or creating a PR for a feature branch, bump the version in **both** files for any modified plugin:

1. `plugins/<plugin-name>/.claude-plugin/plugin.json`
2. `.claude-plugin/marketplace.json`

Both must match. Without a version bump, users won't pick up the update.
