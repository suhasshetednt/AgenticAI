# Autonomous Agent Workflow Guidelines

This document standardizes the agentic workflow pipeline reviewed from external skill files (`SKILL.md`), heavily optimized for robust execution and Human-in-the-Loop (HITL) safety.

## The 4-Phase Execution Pipeline

Every complex work item must follow these phases:

### Phase 1: Understand the Request
*   **Analyze:** Read the task definition completely. You MUST actively scan and understand structured, semi-structured, and unstructured data. This includes parsing text descriptions and visually analyzing attached images (e.g., screenshots of UI/UX, logic, or conditional formatting tables).
*   **Research:** Use file reading and semantic search (grep/glob) to understand the current implementation state. Identify affected services.
*   **Clarify:** Do not proceed if ambiguous. Ask the user questions regarding scope, multiple approaches, or missing edge cases.

### Phase 2: Confirm Understanding
*   **Playback:** Before writing any code or creating artifacts, echo the understanding back to the user in a structured format:
    *   Bullet points of planned changes.
    *   Specific services/files affected.
*   **Gate:** Ask "Shall I proceed?" and wait for explicit confirmation.

### Phase 3: Create Work Item & Plan
*   **Slug/Title:** Generate a semantic, kebab-case slug for the branch or task (e.g., `fix-auth-timeout`).
*   **Design:** Formulate the exact tool calls needed (e.g., specific `multi_replace_file_content` chunks).

### Phase 4: Execute & Verify
*   **Execute:** Run the pipeline.
*   **Verify:** Trigger a verification subagent or run tests/linters immediately after execution to confirm success before reporting completion to the user.
