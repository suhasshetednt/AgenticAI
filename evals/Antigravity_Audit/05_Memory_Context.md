# 5. MEMORY & CONTEXT ENGINEERING AUDIT

## Memory Pipeline Analysis

### Current Architecture
Antigravity relies predominantly on **Episodic Memory** (the `transcript.jsonl` file) loaded directly into the context window. It also features static **Semantic Memory** via pre-loaded skill/plugin documents.

### Identification of Waste and Pollution
1.  **Stale Context Contamination:** Old reasoning blocks, deprecated plans, and overwritten file states remain in the context, confusing the model's attention mechanism.
2.  **Oversized Retrieval Payloads:** Tools like `view_file` return up to 800 lines. If a file is viewed multiple times, the context window fills with redundant file states.
3.  **Missing Chunking & Embeddings:** There is no semantic vector store to recall long-term facts (e.g., user preferences across sessions, specific internal APIs without grep).

### Recommended Frontier-Grade Systems

1.  **Hierarchical Context Compression:**
    *   Implement an LLM-based Summarization Hook that triggers every 10 turns.
    *   Compress raw transcripts into a structured `Current State & Goals` YAML block.
    *   Evict raw dialogue older than 5 turns from the active context window.
2.  **Dynamic Workspace Snapshotting:**
    *   Instead of keeping file contents in the transcript, maintain a lightweight JSON state of "Files Currently Open and Their Hash." Fetch the active file state dynamically right before inference, ignoring historical states.
3.  **Vectorized Skill Injection (RAG):**
    *   Embed all skills in `C:\Users\ADMIN\.gemini\config\plugins\`.
    *   When the model's intent maps to "design", dynamically retrieve and inject the `frontend-design` skill via a hidden prompt layer. Do not inject it by default.
