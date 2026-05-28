# 6. HOOKS, RULES & AUTONOMOUS GUARDRAILS AUDIT

## Safeguards and Lifecycle Management

### Current Status
Antigravity uses asynchronous task tracking (`manage_task`) and reactive wakeups, but lacks deep interceptor-level hooks for execution safety.

### Identified Risks & Weaknesses
1.  **Uncontrolled Recursion (Runaway Agent):** If a lint error persists, the model can enter an infinite loop of patching, failing, and repatching, burning through tokens and compute budget without an escalating intervention threshold.
2.  **Missing Token Budget Hooks:** No mechanism hard-stops a subagent if it exceeds an allocated token quota for a given sub-task.
3.  **Weak Fallback Systems:** If `multi_replace_file_content` fails repeatedly due to line number shifts, the agent lacks a built-in rule to autonomously fallback to a full file overwrite (`write_to_file` with Overwrite) or an AST-based parser.

### Recommended Ideal Hook Architecture

1.  **Pre-Execution Token Validator Hook:**
    *   *Logic:* Before sending a prompt to the LLM, evaluate the payload size. If Payload > 80% of max context, trigger the Context Compression Agent automatically.
2.  **Cyclic Failure Guardrail (Recursion Guard):**
    *   *Logic:* Track tool call signatures. If the exact same sequence of tool calls (e.g., Edit -> Lint -> Error) repeats 3 times, pause execution, alert the user, and switch the system prompt to a strict "Debug/Analysis Only" mode.
3.  **Policy Engine Hook:**
    *   *Logic:* Enforce read/write boundaries natively. Subagents invoked with `Workspace: branch` should be strictly blocked by the tooling layer from writing to the parent directory, enforced via a filesystem Policy Hook independent of the LLM prompt.
