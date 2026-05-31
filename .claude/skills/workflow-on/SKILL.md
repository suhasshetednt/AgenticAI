---
description: "Re-enable workflow enforcement. Only invoke manually via /workflow-on."
allowed-tools: Bash(rm:*)
disable-model-invocation: true
---

!`rm -f .claude/workflow-disabled`

Workflow re-enabled. Edits to protected directories now require an active work item.
