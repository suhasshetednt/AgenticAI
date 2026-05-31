---
description: "Show Jira work item status. Use when user asks about Jira ticket state or says 'jira status'."
argument-hint: [PP-1]
allowed-tools: Bash(python3:*), Bash(ls *), Read, Glob, mcp__atlassian__getJiraIssue, mcp__atlassian__searchJiraIssuesUsingJql
---

<instructions>
## Overview

Show the status of Jira work items being tracked locally.

**Jira Cloud ID**: `<configure-in-atlassian-mcp-settings>`

### If issue key provided (e.g., `PP-1`):

1. Read `.claude/work-items-jira/<ISSUE_KEY>/meta.json`
2. Fetch latest status from Jira using `mcp__atlassian__getJiraIssue`
3. Show:
   ```
   PP-1: <summary>
   Jira Status: <In Progress / Done / To Do>
   Local Resolution: <query_answered / already_fixed / implementing / needs_info / null>
   Task File: <tasks/PP-1.md or N/A>
   Work Item: <active work item slug or N/A>
   ```

### If no issue key:

1. List all directories in `.claude/work-items-jira/`
2. For each, read `meta.json` and show summary table:
   ```
   | Key  | Summary               | Jira Status | Resolution     |
   |------|-----------------------|-------------|----------------|
   | PP-1 | Pay to Unlock issues  | In Progress | implementing   |
   | PP-2 | Subscription issues   | To Do       | not started    |
   ```

3. Also query Jira for all open PP tickets:
   ```
   project = PP AND statusCategory != Done ORDER BY created DESC
   ```
4. Cross-reference with local state to show what's tracked vs untracked
</instructions>
