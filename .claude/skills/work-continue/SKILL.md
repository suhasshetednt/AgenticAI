---
description: Continue the work item pipeline (routes to correct subagent)
allowed-tools: Bash(python3:*), Bash(git *), Bash(gh *), Task, Read, Skill, AskUserQuestion, mcp__atlassian__addCommentToJiraIssue, mcp__atlassian__getTransitionsForJiraIssue, mcp__atlassian__transitionJiraIssue
---

!`python3 .claude/workflow/work_item.py status`

<instructions>
## Routing Logic

Based on the status shown above, route to the appropriate stage.

### No Active Work Item
-> STOP. Tell user: `/work <describe what you want to do>`

---

### READY_FOR_ARCH

**Check if architecture is complete:**

1. Read `.claude/work-items/<slug>/spec.md`
2. If spec.md is just a template (placeholder content) OR empty:
   - Run `architect-review` subagent with this prompt:

   ```
   ## Task: Architecture Review for Work Item

   **Slug**: <slug>
   **Title**: <title>
   **Task ID**: <task_id or "none">

   Read the work item context and create:
   1. spec.md - Acceptance criteria (Given/When/Then)
   2. adr.md - Architecture decisions
   3. plan.md - Implementation checklist

   Also detect and set work_type in meta.json (backend/frontend/fullstack).
   Store affected_repos in meta.json (list of repo paths relative to workspace root).

   If task_id exists, read the task file from ./tasks/ for context.

   Return with "AWAITING APPROVAL" when complete.
   ```

   - Subagent will return with "AWAITING APPROVAL"
   - **STOP** and show user the summary
   - Tell user: "Reply 'approved' or 'continue' to proceed, or provide feedback"

3. If spec.md has real content (architecture done):
   - User has approved — now handle branch creation before moving to TEST

   **Branch Creation (when branch_workflow enabled):**
   1. Read `.claude/workflow-config.json` — check `branch_workflow.enabled`
   2. Read meta.json for `affected_repos` (set by architect-review)
   3. Compute branch name: `{branch_prefix}{task_id}` (e.g., `feature/ASL-123`)
      - `branch_prefix` from workflow-config.json (default: `feature/`)
      - `task_id` is the Jira ticket number — result is always `feature/{ticket-no}`
      - If no task_id, use slug only: `feature/{slug}` (no hyphenated prefixes)
   4. For each repo in affected_repos:
      a. `cd` into repo directory
      b. **Capture parent branch**: `parent_branch = $(git branch --show-current)` — this is the branch we're stacking on
      c. If `stack_branches` is true: branch from current HEAD
         Else: `git checkout {pr_target} && git pull`
      d. Check if branch already exists: `git branch --list {branch_name}`
         - If exists: `git checkout {branch_name}`
         - If not: `git checkout -b {branch_name}`
   5. Update meta.json with `branch_name` and `parent_branches`:
      ```bash
      python3 -c "
      import json
      meta_path = '.claude/work-items/<slug>/meta.json'
      with open(meta_path) as f:
          meta = json.load(f)
      meta['branch_name'] = '<branch_name>'
      # Store parent branch per repo for stacked PR targeting
      if 'parent_branches' not in meta:
          meta['parent_branches'] = {}
      meta['parent_branches']['<repo_path>'] = '<parent_branch>'
      with open(meta_path, 'w') as f:
          json.dump(meta, f, indent=2, sort_keys=True)
          f.write('\n')
      "
      ```
   6. Log: "Created branch {branch_name} in: [repo list]"
   7. Log parent branches: "PR targets: {repo} → {parent_branch} for each repo"

   If branch_workflow is NOT enabled or config file is missing, skip branch creation.

   - Update status:
     ```bash
     python3 .claude/workflow/work_item.py set-status READY_FOR_TEST
     ```
   - **Auto-continue**: Invoke `/work-continue` via Skill

---

### READY_FOR_TEST

**Run tester-agent to write TDD tests.**

1. Read `.claude/work-items/<slug>/meta.json` to get work_type
2. Read `.claude/work-items/<slug>/spec.md` for acceptance criteria
3. Run `tester-agent` subagent with this prompt:

   ```
   ## Task: Write TDD Tests for Work Item

   **Slug**: <slug>
   **Title**: <title>
   **Work Type**: <work_type from meta.json>
   **Task ID**: <task_id or "none">
   **Branch**: <branch_name from meta.json or "none">

   ### Context Files to Read:
   - `.claude/work-items/<slug>/spec.md` - Acceptance criteria
   - `.claude/work-items/<slug>/adr.md` - Architecture decisions
   - `.claude/work-items/<slug>/plan.md` - Implementation plan

   ### Your Job:
   1. Write comprehensive failing tests for ALL acceptance criteria
   2. Cover edge cases from spec.md
   3. Use Jest + supertest for API tests
   4. Write test-summary.md for handoff to IMPL stage

   ### Work Type Guidance:
   - If backend: Write Jest tests in the relevant service's test directory
   - If fullstack: Write tests for each affected service

   Ask user to run tests and verify they fail correctly.
   ```

4. After completion, update status:
   ```bash
   python3 .claude/workflow/work_item.py set-status READY_FOR_IMPL
   ```
5. **Auto-continue**: Invoke `/work-continue` via Skill

---

### READY_FOR_IMPL

**Run developer-agent to implement code.**

1. Read `.claude/work-items/<slug>/meta.json` to get work_type
2. Run `developer-agent` subagent with this prompt:

   ```
   ## Task: Implement Code for Work Item

   **Slug**: <slug>
   **Title**: <title>
   **Work Type**: <work_type from meta.json>
   **Stage**: READY_FOR_IMPL
   **Task ID**: <task_id or "none">
   **Branch**: <branch_name from meta.json or "none">
   **Affected Repos**: <affected_repos from meta.json or "none">

   ### Context Files to Read:
   - `.claude/work-items/<slug>/spec.md` - Acceptance criteria
   - `.claude/work-items/<slug>/adr.md` - Architecture decisions
   - `.claude/work-items/<slug>/plan.md` - Implementation plan
   - `.claude/work-items/<slug>/test-summary.md` - Tests to pass

   ### Your Job:
   1. Read the tests to understand what needs to pass
   2. Implement minimal code to pass ALL tests
   3. Follow engineering standards (TypeScript strict, async/await, error handling)
   4. Iterate with user until tests pass
   5. Write impl-summary.md for handoff to VERIFY stage

   ### Service Structure:
   - Services: <name>/ (e.g., file-receiver/, data-management/)
   - Shared packages: installed as local .tgz files (db-sdk, email-service, json-to-xml-component)
   - Infra: k8s/ (Kubernetes manifests — one folder per environment: asl-dev, asl-test, asl-prod)

   If task file exists, execute DELETE -> UPDATE -> CREATE order.
   ```

3. After completion, update status:
   ```bash
   python3 .claude/workflow/work_item.py set-status READY_FOR_VERIFY
   ```
4. **Auto-continue**: Invoke `/work-continue` via Skill

---

### READY_FOR_VERIFY

**Run developer-agent in verification mode.**

1. Read `.claude/work-items/<slug>/meta.json` to get work_type
2. Run `developer-agent` subagent with this prompt:

   ```
   ## Task: Verify Quality for Work Item

   **Slug**: <slug>
   **Title**: <title>
   **Work Type**: <work_type from meta.json>
   **Stage**: READY_FOR_VERIFY
   **Task ID**: <task_id or "none">
   **Branch**: <branch_name from meta.json or "none">
   **Affected Repos**: <affected_repos from meta.json or "none">

   ### Context Files to Read:
   - `.claude/work-items/<slug>/impl-summary.md` - What was implemented

   ### Your Job:
   1. Identify all changed files and which service(s) were modified
   2. Run quality checks per affected service:
      ```bash
      # For each repo in affected_repos — run from inside the service directory
      cd <repo_path> && npm run lint && npx tsc --noEmit && npm test
      ```
      Example: if affected_repos = ["file-receiver"], run:
      ```bash
      cd file-receiver && npm run lint && npx tsc --noEmit && npm test
      ```
      **CRITICAL**: `npx tsc --noEmit` must be run separately — ts-jest with `isolatedModules: true` does NOT catch type errors during test runs.
   3. Fix any failures (ESLint, test failures)
   4. Iterate until all checks pass (max 2 attempts, then escalate to user)
   5. Write final summary.md

   After all checks pass, the work item is complete.
   ```

3. After quality checks pass, transition to DOCS:
   ```bash
   python3 .claude/workflow/work_item.py set-status READY_FOR_DOCS
   ```
4. **Auto-continue**: Invoke `/work-continue` via Skill

---

### READY_FOR_DOCS

**Generate repo-level docs and team impact docs.**

1. Read `.claude/work-items/<slug>/meta.json` for work_type, affected_repos, task_id, title
2. Run `developer-agent` subagent with this prompt:

   ```
   ## Task: Generate Documentation for Work Item

   **Slug**: <slug>
   **Title**: <title>
   **Work Type**: <work_type>
   **Stage**: READY_FOR_DOCS
   **Task ID**: <task_id or "none">
   **Branch**: <branch_name or "none">
   **Affected Repos**: <affected_repos>

   ### Context Files to Read:
   - `.claude/work-items/<slug>/impl-summary.md`
   - `.claude/work-items/<slug>/summary.md`
   - Task file: `./tasks/<task_id>-*.md` or `./tasks/archive/<task_id>-*.md`

   ### Your Job:
   1. Identify all changed files per affected repo (read impl-summary, git diff)
   2. Generate REPO-LEVEL DOCS — for EACH affected repo separately:
      - Create `<repo_path>/docs/<task_id>-<slug>.md`
      - Content: overview, fields/exports added, files changed, code examples, downstream tasks
      - CRITICAL: Only document changes that happened IN THAT REPO
      - Follow date header: `> *Created: YYYY-MM-DD · Last Updated: YYYY-MM-DD*`
   3. Generate TEAM IMPACT DOCS in `./tasks/impacts/`:
      - Naming: `<TEAM>-<task_id>-<slug>-impact.md`
      - Teams: BE, DEVOPS, FE (FE only for perdiems-frontend changes)
      - Only create if there ARE action items for that team
      - Include: summary, specific action items, code examples, priority
      - Use task file's "Team Impact" section as starting point
   4. Write `docs-summary.md` in work item directory listing all generated docs

   ### Rules:
   - NEVER put repo docs in wrong repo (e.g., data-management changes go in data-management docs)
   - Each doc must be self-contained and useful to the target team
   ```

3. After completion, determine next status:
   - Read `.claude/workflow-config.json`
   - If `branch_workflow.enabled` is true:
     ```bash
     python3 .claude/workflow/work_item.py set-status READY_FOR_PUSH
     ```
   - If branch workflow disabled or config missing:
     ```bash
     python3 .claude/workflow/work_item.py set-status DONE
     ```
4. **Auto-continue**: Invoke `/work-continue` via Skill

---

### READY_FOR_PUSH

**Commit, push, verify pipeline, create PR, post Jira comment, and validate in dev.**

1. Read `.claude/work-items/<slug>/meta.json` for:
   - `affected_repos` — list of repo paths
   - `branch_name` — the task branch (`feature/{ticket-no}`)
   - `task_id` — for commit/PR messages
   - `title` — for commit/PR messages
   - `parent_branches` — per-repo parent branch for PR destination
   - `pr_urls` — if present, PRs were already created; skip straight to step 8
2. Read `.claude/workflow-config.json` for `pr_target` and `pr_target_mode`

3. **Request Commit Approval** — before staging ANY files:
   a. For each affected repo run `git status` and `git diff --stat` to list changed files
   b. Show a clear summary to the user:
      ```
      Ready to commit to: {branch_name}

      Repo: {repo_path}
        Modified: file1.ts, service2.ts
        Added:    new-handler.ts

      Commit message: "{task_id}: {title}"
      ```
   c. Use AskUserQuestion: "Commit and push these changes to `{branch_name}`?"
      - Options: "Yes, commit and push" / "No, I want to review first"
   d. If user declines: **STOP** — tell user "Run `/work-continue` when you're ready to commit."
   e. If user approves: proceed.

4. **Commit & Push** — for each affected repo:
   a. `cd` into the repo directory
   b. Stage specific changed files (NOT `git add -A` or `git add .`)
   c. Commit: `{task_id}: {title}` (or `{slug}: {title}` if no task_id) — **no AI attribution**
   d. `git push origin {branch_name}`
   e. Log push result

5. **Pipeline Verification** — for each pushed repo:
   a. Wait for the GitHub Actions workflow to complete:
      ```bash
      RUN_ID=$(gh run list --branch {branch_name} --limit 1 --json databaseId --jq '.[0].databaseId')
      gh run watch "$RUN_ID"
      ```
   b. Check result:
      - **success**: Continue to PR creation
      - **failure**:
        1. `gh run view "$RUN_ID" --log-failed`
        2. Set status back to READY_FOR_VERIFY
        3. Tell user: "Pipeline failed. Run `/work-continue` to re-enter VERIFY and fix issues."
        4. **Return immediately**
      - **Still running / timeout**: Ask: "Pipeline still running — wait longer, skip verification, or abort?"
        - skip: continue | wait: re-run watch | abort: return
   c. If `gh` unavailable: warn and continue

6. **Create PRs** — for each pushed repo (run from inside the repo directory):
   a. Check if PR already exists: `gh pr list --head {branch_name} --json url --jq '.[0].url'`
      - If a URL is returned: save it, skip creation (idempotent)
   b. **Determine PR destination**:
      - `pr_target_mode` = `"parent"` AND `parent_branches` set → use `parent_branches[repo_path]`
      - Otherwise: use `pr_target` from workflow-config.json (default: `development`)
   c. Create the PR:
      ```bash
      gh pr create \
        --base {pr_destination} \
        --head {branch_name} \
        --title "{task_id}: {title}" \
        --body "$(cat <<'EOF'
## Summary
{bullet list from impl-summary.md — 3–6 concise points of what changed}

## Jira
{task_id}: {title}

## Test Plan
- [ ] lint passes
- [ ] typecheck passes
- [ ] unit tests pass
- [ ] manually tested in dev after deploy
EOF
)"
      ```
   d. Save the PR URL to meta.json under `pr_urls.{repo_path}`
   e. Log: "PR created: {branch_name} → {pr_destination}: {pr_url}"

7. **Post Jira Comment** (only if `task_id` is set):
   a. Read `impl-summary.md` and `summary.md` for a concise description of the change
   b. Draft a comment (casual dev tone — see voice guide in work-jira SKILL.md):
      ```
      PR raised: {PR_URL}

      What changed:
      - {bullet 1 from impl-summary}
      - {bullet 2}
      - {bullet 3}
      ```
   c. Post with `mcp__atlassian__addCommentToJiraIssue` (`contentFormat: "markdown"`)
   d. Log: "Jira {task_id} — PR comment posted"

8. **Dev Validation Checkpoint**:
   a. Use AskUserQuestion:
      - Question: "Has the PR been merged and is the change running correctly in dev?"
      - Options:
        - "Yes, working fine in dev"
        - "No, something broke in dev"
        - "Not merged yet — I'll validate later"
   b. **If working fine in dev**:
      1. Fetch available transitions: `mcp__atlassian__getTransitionsForJiraIssue`
      2. Find the transition named "In Test", "Ready for Test", "Testing", or closest match
      3. If found: apply with `mcp__atlassian__transitionJiraIssue`
      4. Post Jira comment: "Running fine in dev. Moving to test."
      5. Log: "Jira {task_id} → In Test"
      6. Proceed to step 9 (DONE)
   c. **If something broke**:
      1. Ask: "What's broken? Describe the issue so it can be investigated."
      2. Set status back to READY_FOR_VERIFY:
         ```bash
         python3 .claude/workflow/work_item.py set-status READY_FOR_VERIFY
         ```
      3. Tell user: "Run `/work-continue` to re-enter VERIFY and fix the issue."
      4. **Return immediately** — do NOT proceed to DONE
   d. **If not merged yet**:
      - Tell user: "PR is ready at {PR_URL}. After merging and checking dev, run `/work-continue` to complete the Jira transition."
      - **STOP** — do NOT transition to DONE

9. Transition to DONE (only reached after dev validates):
   ```bash
   python3 .claude/workflow/work_item.py set-status DONE
   ```
10. **Auto-continue**: Invoke `/work-continue` via Skill

---

### DONE

-> STOP. Tell user: `/work-finish <summary of what was done>`

---

## Launching Subagents

Use Task tool with appropriate subagent_type:

| Stage | Subagent | Purpose |
|-------|----------|---------|
| READY_FOR_ARCH | `architect-review` | Write spec, ADR, plan |
| READY_FOR_TEST | `tester-agent` | Write comprehensive TDD tests |
| READY_FOR_IMPL | `developer-agent` | Implement code to pass tests |
| READY_FOR_VERIFY | `developer-agent` | Run quality checks, fix issues |
| READY_FOR_DOCS | `developer-agent` | Generate repo + impact docs |
| READY_FOR_PUSH | *(no subagent)* | Main agent handles git ops directly |

**Always include in prompt:**
- Work item slug and title
- Work type (backend/frontend/fullstack)
- Task ID if exists
- Branch name if exists
- Affected repos if exists
- Current stage context
- Relevant handoff files

---

## HITL Checkpoint

**ARCH is the only HITL stage.** After architect-review:
- Show summary of spec, ADR, plan
- Show work_type detected
- Show affected_repos and branch_name (if branch workflow enabled)
- Explicitly say "AWAITING APPROVAL"
- Wait for user to say "approved", "continue", "looks good", etc.
- Do NOT auto-continue until user approves

---

## On Errors

If any subagent reports errors or blockers:
- **STOP auto-continuation**
- Summarize the issue clearly
- Ask user how to proceed:
  - Fix and retry?
  - Skip this stage? (use `/work-set-status`)
  - Abandon work item?

---

## Handoff Files

Each stage writes a handoff file for the next:

| Stage | Writes | Read By |
|-------|--------|---------|
| ARCH | spec.md, adr.md, plan.md | TEST, IMPL |
| TEST | test-summary.md | IMPL |
| IMPL | impl-summary.md | VERIFY |
| VERIFY | summary.md | DOCS |
| DOCS | docs-summary.md, repo docs, team impact docs | PUSH, /work-finish, other teams |

Ensure subagents read their predecessor's handoff files.
</instructions>
