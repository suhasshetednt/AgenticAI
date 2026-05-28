# 3. AGENTIC AI ARCHITECTURE REVIEW

## Agent Topology Evaluation

Antigravity currently relies heavily on a **Monolithic Generalist Agent** pattern, supported by optional `research` and `self` subagents.

### Current Implementation Status

*   **Planner Agents:** Missing distinct entity. Planning is done implicitly inside the monolithic `<thought>` block.
*   **Executor Agents:** Active. The main loop serves as the executor.
*   **Verifier Agents:** Missing. No dedicated adversarial verifier exists to check output *before* finalizing.
*   **Routing Agents:** Missing. Tool routing is handled via base model instruction fine-tuning.
*   **Memory Agents:** Missing. Context is managed passively via transcripts.

### Identified Flaws

1.  **Planner/Executor Entanglement:** By forcing the model to plan and execute in the same inference pass, context becomes heavily polluted with implementation details, causing "architectural drift" during long tasks.
2.  **Recursive Delegation Risks:** Subagents (`invoke_subagent`) inherit massive context payloads but lack strict semantic boundaries, leading to overlapping work and token duplication.
3.  **Hallucination Amplification:** Without a Critic/Verifier agent in the loop, logic errors in step 1 are blindly accepted and built upon in step 2.

### Recommended Optimal Agent Topology

Shift from a Monolithic architecture to a **Directed Acyclic Graph (DAG) of Specialized Micro-Agents**:

1.  **The Orchestrator (Router/Planner):** Fast, low-parameter model. Ingests User Request, queries semantic memory, generates a JSON Plan, and delegates to Executors. *Never runs bash or edits files.*
2.  **The Executor (Worker):** Receives strict, isolated sub-tasks (e.g., "Refactor file X"). Uses `multi_replace_file_content`. Returns diff/status.
3.  **The Critic (Verifier):** Runs tests, runs linters, and semantically compares Executor output against the Orchestrator's plan. Returns Pass/Fail with feedback.
4.  **The Memory Custodian (Background):** Continuously summarizes and vectorizes the transcript in parallel, injecting only relevant `<ephemeral_context>` into the Orchestrator's prompts.

### Frontier-Grade Coordination Strategy
Implement an **Actor Model** framework for agent coordination. Agents communicate strictly via typed message passing (using `send_message`), eliminating the need for shared state or monolithic transcript injection.
