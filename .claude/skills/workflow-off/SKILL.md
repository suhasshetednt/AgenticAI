---
description: "Disable workflow enforcement. Only invoke manually via /workflow-off."
allowed-tools: Bash(touch:*)
disable-model-invocation: true
---

!`touch .claude/workflow-disabled`

Workflow disabled. You can now edit any directory without a work item.
Run `/workflow-on` to re-enable.
