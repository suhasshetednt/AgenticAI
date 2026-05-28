# 7. MCP & TOOL ECOSYSTEM AUDIT

## Model Context Protocol (MCP) Evaluation

### Current Implementation
Antigravity connects to MCP servers (e.g., Atlassian Rovo) effectively, exposing skills like Confluence/Jira search directly into the agent's namespace.

### Inefficiencies Identified
1.  **Orchestration Latency:** Every tool call, even deterministic local ones (like `list_dir`), requires a full roundtrip to the LLM to process the result before firing the next tool.
2.  **Lack of Batching:** The agent often requests `view_file` on File A, reads it, then requests `view_file` on File B. These should be batched.
3.  **Context Passed Into Tools:** Tool inputs are highly structured, but tool *outputs* are unstructured and verbose. An MCP server returning a massive Confluence page dump will instantly pollute the context window.

### Recommended Scalable Tool Execution Architecture

1.  **Tool-Call Batching (Parallelism):**
    *   Enable the model to emit a graph of tool calls. "Read A AND Read B AND list C". The executor runs them in parallel, concatenates the formatted results, and returns them in a single inference cycle.
2.  **Semantic Truncation on Tool Outputs:**
    *   Implement an intermediate output parsing layer. If `grep_search` returns 500 lines, the executor should pipe it through a tiny, local, ultra-fast embedding model to extract only the 5 lines relevant to the user's prompt, injecting *only* those 5 lines back to Antigravity.
3.  **MCP Caching Layer:**
    *   Add a local LRU cache for immutable MCP queries (e.g., Jira issue descriptions that haven't changed since the last poll) to save network latency and token generation costs.
