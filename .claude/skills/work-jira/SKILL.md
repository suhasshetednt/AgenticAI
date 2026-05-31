---
description: "Work on a Jira ticket. Use when user mentions a Jira ticket key or says 'work on Jira issue'."
argument-hint: --task=ASL-1
allowed-tools: Bash(python3:*), Bash(git *), Bash(mkdir *), Task, Read, Write, Edit, Grep, Glob, Skill, Agent, AskUserQuestion, mcp__atlassian__getJiraIssue, mcp__atlassian__searchJiraIssuesUsingJql, mcp__atlassian__addCommentToJiraIssue, mcp__atlassian__transitionJiraIssue, mcp__atlassian__getTransitionsForJiraIssue, mcp__atlassian__editJiraIssue
---

<instructions>
## Overview

You are working on a Jira ticket from the **ASL** project.
Your job is to fetch the ticket, understand it fully, then either answer it directly
or implement a fix through the existing `/work` pipeline.

Write Jira comments in a casual, direct, technical but approachable voice.
NEVER mention AI, Claude, or any agent.
Write as a senior dev who knows the codebase inside out.

**Jira Cloud ID**: `<configure-in-atlassian-mcp-settings>`

---

## Phase 1: Parse Arguments

Extract the issue key from `$ARGUMENTS`:
- `--task=PP-1` → issue key is `PP-1`
- `--task PP-1` → issue key is `PP-1`
- Just `PP-1` → issue key is `PP-1`

If no issue key provided, STOP and ask: "Which Jira ticket? Usage: `/work-jira --task=ASL-1`"

---

## Phase 2: Fetch & Store

### 2a. Fetch Issue Details

Use `mcp__atlassian__getJiraIssue` to fetch:
- fields: `summary`, `description`, `status`, `issuetype`, `priority`, `assignee`, `reporter`, `created`, `updated`, `comment`, `subtasks`, `parent`
- Use `responseContentFormat: "markdown"` for readable content

### 2b. Fetch Comments

Comments come in the `comment` field of the issue response. Extract all comments with:
- Author name
- Created date
- Body text

### 2c. Fetch Subtasks (if Story/Epic)

If the issue has subtasks, fetch each subtask's details too (summary, description, status, comments).

### 2d. Fetch Parent (if Subtask)

If the issue is a subtask, also fetch the parent issue for context.

### 2e. Save Locally

Create directory: `.claude/work-items-jira/<ISSUE_KEY>/`

Save `issue.md`:
```markdown
# <ISSUE_KEY>: <Summary>

**Type**: <issuetype>
**Status**: <status>
**Priority**: <priority>
**Assignee**: <assignee>
**Reporter**: <reporter>
**Created**: <created>
**Updated**: <updated>
**Parent**: <parent key if subtask, or "N/A">

## Description

<description in markdown>

## Comments

### <Author> — <date>
<comment body>

### <Author> — <date>
<comment body>

## Subtasks

- [ ] <KEY>: <summary> (<status>)
- [ ] <KEY>: <summary> (<status>)
```

Save `meta.json`:
```json
{
  "issue_key": "PP-1",
  "summary": "...",
  "type": "Story|Bug|Task|Subtask",
  "status": "To Do",
  "reporter": "...",
  "reporter_account_id": "...",
  "assignee": "...",
  "parent_key": null,
  "subtask_keys": ["PP-5", "PP-6"],
  "fetched_at": "2026-03-13T...",
  "resolution": null
}
```

---

## Phase 3: Transition to In Progress

Use `mcp__atlassian__transitionJiraIssue`:
- `issueIdOrKey`: the issue key
- `transition.id`: `"21"` (In Progress)

Log: "Moved <ISSUE_KEY> to In Progress"

---

## Phase 4: Analyze the Ticket

Read the issue content and determine what kind of work this is.

### 4a. Research the Codebase

Based on the issue description and affected APIs:
1. Use Grep/Glob to find relevant code (endpoints, services, models)
2. Check if the issue describes something that's already been fixed
3. Check if it's a question that can be answered by reading the code
4. Check existing task files in `tasks/` for related work

### 4b. Classify the Ticket

Determine ONE of these categories:

| Category | When | Action |
|----------|------|--------|
| **QUERY** | Question about how something works, which endpoint to use, or clarification needed by team | Comment with answer on Jira → Done |
| **ALREADY_FIXED** | The issue describes something already fixed in current branch (e.g., on `feature/&lt;current-branch&gt;`) | Comment explaining it's fixed + what branch/commit → Done |
| **NEEDS_INFO** | Can't determine what to do without more information | Comment asking specific questions → Stay In Progress |
| **BUG** | Confirmed bug in the code that needs a fix | Create task → `/work` pipeline |
| **TASK** | New feature or enhancement that needs implementation | Create task → `/work` pipeline |

---

## Phase 5: Execute Based on Category

### QUERY or ALREADY_FIXED → Comment & Close

1. Draft a Jira comment:
   - Casual, direct tone (as Tirth)
   - Include specific code references (file paths, line numbers)
   - Include endpoint URLs, example requests/responses if relevant
   - For ALREADY_FIXED: mention the branch, what was changed, link to relevant code
   - Keep it concise but thorough

2. Post comment using `mcp__atlassian__addCommentToJiraIssue`:
   - `contentFormat`: `"markdown"`
   - `commentBody`: your drafted comment

3. Transition to Done:
   - `transition.id`: `"31"`

4. Save resolution to `meta.json`:
   ```json
   { "resolution": "query_answered" }
   ```
   or
   ```json
   { "resolution": "already_fixed", "fixed_in": "feature/&lt;current-branch&gt;" }
   ```

5. **STOP** — report to user what you did.

### NEEDS_INFO → Comment & Wait

1. Draft a Jira comment:
   - Casual tone, asking specific questions
   - Show what you've found so far
   - Tag the reporter if possible (use their display name)

2. Post comment using `mcp__atlassian__addCommentToJiraIssue`

3. Do NOT transition status — keep In Progress

4. Save to meta.json:
   ```json
   { "resolution": "needs_info", "waiting_on": "<reporter name>" }
   ```

5. **STOP** — tell user: "Commented on <ISSUE_KEY> asking for more info. Run `/work-jira --task=<ISSUE_KEY>` again after they respond."

### BUG or TASK → Create Task & Run Pipeline

1. Create a task file at `tasks/<ISSUE_KEY>.md`:

```markdown
# <ISSUE_KEY>: <Summary>

> Source: Jira <ISSUE_KEY> (<issuetype>)
> Reporter: <reporter>
> Priority: <priority>

## Context

<Summarize the issue in your own words — what's broken/needed and why>

## Affected APIs / Services

<List from the Jira description + your codebase research>

## Acceptance Criteria

- [ ] <criterion 1 derived from description>
- [ ] <criterion 2>
- [ ] <criterion 3>

## Technical Analysis

<Your findings from codebase research — what files need changing, root cause if bug>

## DELETE

<files/code to remove, or "N/A">

## UPDATE

<files/code to modify with specific changes>

## CREATE

<new files/code needed, or "N/A">
```

2. Update meta.json:
   ```json
   { "resolution": "implementing", "task_file": "tasks/<ISSUE_KEY>.md" }
   ```

3. Invoke the existing work pipeline:
   ```
   /work --task=<ISSUE_KEY>
   ```

4. The `/work` pipeline (READY_FOR_PUSH stage) automatically:
   - Creates a `feature/{ISSUE_KEY}` branch (e.g., `feature/ASL-123`)
   - Runs unit tests (VERIFY stage) before committing
   - Asks for explicit commit approval before pushing
   - Creates the PR to `development`
   - Posts a Jira comment with the PR link and fix summary
   - Asks the developer if it's running correctly in dev
   - If yes → transitions the ticket to "In Test" on Jira
   - If no → loops back to VERIFY for a fix

   **Do not manually post PR comments or transition the ticket** — the pipeline handles it.

---

## Phase 6: Close After Test Passes

After the ticket has been validated in test and is ready to close:

1. Run `/work-jira --task=<ISSUE_KEY>` — this re-fetches the latest Jira state
2. If status is "In Test" / "Testing" and testing is confirmed passed:
   - Post a Jira comment: "Tested and verified. Closing." (or confirm with team first)
   - Transition to Done: `mcp__atlassian__transitionJiraIssue` with `transition.id: "31"`
3. If the ticket is already Done: just confirm and STOP

Note: The PR comment with fix summary and the "In Test" transition are handled automatically by the `/work` pipeline's READY_FOR_PUSH stage — do not duplicate them here.

---

## Comment Tone Guide

**DO:**
- "Hey, looked into this — the issue is [X]. Here's what's happening: ..."
- "This is actually already fixed on `feature/&lt;current-branch&gt;`. The [endpoint] now ..."
- "Fixed this up. The root cause was [X]. Changes: ..."
- "Quick question — when you say [X], do you mean [A] or [B]? Because ..."
- "Good catch. The `productId` validation was too strict for type 6. Pushed a fix ..."

**DON'T:**
- Don't say "I" when referring to AI actions
- Don't use formal language ("Please be advised...", "I would like to inform...")
- Don't mention Claude, AI, agents, or automation
- Don't use emojis unless the team typically does
- Don't over-explain — the team are developers, they get it

---

## Error Handling

- If Jira API fails: retry once, then STOP and tell user
- If issue doesn't exist: STOP with clear error
- If transition fails (already in target state): log and continue
- If codebase research is inconclusive: default to NEEDS_INFO, ask team

---

## Subtask Handling

When working on a **Story** with subtasks:
- Option A: User ran `/work-jira --task=PP-1` (the story) — analyze all subtasks, work through each
- Option B: User ran `/work-jira --task=PP-5` (a subtask) — work on just that subtask, reference parent for context

When completing the LAST subtask of a story:
- Also transition the parent story to Done if all subtasks are now Done

---

## Resume Support

If `/work-jira --task=PP-1` is run again on an already-fetched ticket:
1. Re-fetch to get latest comments
2. Check if new comments were added since last fetch
3. If new comments: analyze them and respond/act accordingly
4. If `resolution: "needs_info"`: check if the answer came in via new comments
5. If `resolution: "implementing"`: check if `/work` pipeline is still running
</instructions>
