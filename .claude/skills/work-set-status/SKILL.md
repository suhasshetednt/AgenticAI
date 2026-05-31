---
description: "Manually set work item status for corrections. Only invoke via /work-set-status."
argument-hint: <READY_FOR_ARCH|READY_FOR_TEST|READY_FOR_IMPL|READY_FOR_VERIFY|READY_FOR_DOCS|READY_FOR_PUSH|DONE>
allowed-tools: Bash(python3:*)
disable-model-invocation: true
---

!`python3 .claude/workflow/work_item.py set-status $ARGUMENTS`

Status updated. Run `/work-status` to verify.
