---
description: "Start a new work item and execute the development pipeline. Use when user invokes /work explicitly."
argument-hint: [--task TASK_ID] <describe what you want to do...>
allowed-tools: Bash(python3:*), Task, Read, Grep, Glob, AskUserQuestion, Skill
---

<instructions>
## Overview

You are starting a new work item from a natural language description. Your job is to:
1. **Understand** what the user wants (ask questions, research if needed)
2. **Confirm** your understanding before creating anything
3. **Create** the work item with appropriate slug and title
4. **Execute** the pipeline automatically

## Phase 1: Understand the Request

### If `--task TASK_ID` is provided:
1. Find and read the task file: `./tasks/{TASK_ID}-*.md`
2. Extract the task title and sections (DELETE/UPDATE/CREATE)
3. Use task content as primary context
4. Skip to Phase 2 (task files are already well-defined)

### If natural language description:
1. **Analyze** the request - what is the user asking for?
2. **Research** if needed:
   - Use Grep/Glob to find existing patterns
   - Read relevant files to understand current implementation
   - Identify which service(s) will be affected
3. **Clarify** if ambiguous - use AskUserQuestion for:
   - Unclear scope ("Should this include X or just Y?")
   - Multiple approaches ("Do you want A or B?")
   - Missing details ("What should happen when...?")
   - Which service(s) should be modified

**DO NOT proceed to Phase 2 until you fully understand the request.**

## Phase 2: Confirm Understanding

Before creating anything, confirm with the user:

```
I understand you want to:
- [bullet 1]
- [bullet 2]
- [bullet 3]

Service(s) affected:
- [service-name]: [what changes]
```

**Branch workflow check**: Read `.claude/workflow-config.json`. If `branch_workflow.enabled` is true, add to the confirmation message:
```
Branch workflow: feature/payments_v2-<TASK_ID or slug> (stacked from current branch)
PR target: feature/payments_v2
```

```
Shall I proceed?
```

Wait for user confirmation. If they correct you, update understanding and confirm again.

## Phase 3: Create Work Item

### Generate Slug
- Extract 2-4 key terms from the request
- Create kebab-case: `add-logout-button`, `fix-auth-timeout`
- Max 30 characters
- If conflict exists, add more context: `add-logout-button-profile`
- If still conflicts, add date: `add-logout-button-20240130`

### Generate Title
- Concise summary, max 60 characters
- Action-oriented: "Add logout button to user profile"
- For tasks: Use task title from file

### Create the work item:
```bash
python3 .claude/workflow/work_item.py start <slug> "<title>" [--task TASK_ID]
```

## Phase 4: Execute Pipeline

After work item is created:
1. Invoke `/work-continue` using the Skill tool
2. This routes to `architect-review` subagent
3. **HITL STOP** after ARCH - user reviews spec+ADR+plan
4. After user approval, pipeline auto-continues: TEST -> IMPL -> VERIFY
5. If branch workflow enabled: -> PUSH (commit, push, pipeline check, PR) -> DONE
6. If branch workflow disabled: -> DONE

## Rules

- **NEVER** create a work item without confirming understanding
- **NEVER** skip clarification if the request is ambiguous
- **ALWAYS** research before assuming you know what needs to change
- **ALWAYS** identify which service(s) are affected
- **ALWAYS** get explicit "yes" or confirmation before creating work item
</instructions>
