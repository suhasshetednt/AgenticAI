---
description: Complete the active work item
argument-hint: <summary words...>
allowed-tools: Bash(python3:*)
---

!`python3 .claude/workflow/work_item.py finish --force $ARGUMENTS`

Work item completed. Active slug cleared.

**Branch workflow**: Do NOT switch branches after finishing. Stay on the current
task branch so the next task can stack from it.
