# 12. UNIVERSAL SKILL ARCHITECTURE BLUEPRINT

To operate across all technology domains without exploding token limits, Antigravity requires a **Dynamic Capability Loading System**.

## 1. Dynamic Capability Loading System (Semantic RAG for Skills)

**The Problem:** Loading instructions for Rust borrow checking, AWS IAM policies, and React Native UI rendering into a single system prompt is impossible and highly wasteful.

**The Solution:** The **Skill Registry Architecture**.
*   **Registry:** A centralized, version-controlled repository of `SKILL.json` and `SKILL.md` files.
*   **Capability Graph:** Skills are mapped as nodes in a graph. (e.g., `React` -> `Frontend`, `React` -> `TypeScript`, `TypeScript` -> `Node`).
*   **Semantic Router:** When the user prompts "Build a Solana smart contract", the router embeds the prompt, queries the Capability Graph, and pulls *only* the `Solidity`, `Hardhat`, and `Web3_Security` skills into the context.

## 2. Technology-Specific Agent Design

Instead of a monolithic generic worker, deploy specialized executor classes:
*   `Agent::RustExecutor`: Pre-configured with cargo commands, understands clippy output, and uses a stricter token budget for compiler iterations.
*   `Agent::DataEngineer`: Has native tools to execute SQL against a remote Warehouse MCP without needing a local bash environment.
*   `Agent::SecOps`: Read-only file access. Can only run analysis tools and output threat reports.

## 3. Cross-Domain Orchestration Model

**Hierarchical Contract-Based Orchestration:**
When tasked with building a full-stack App (React + Go + Postgres):
1.  **Lead Architect Agent** creates an OpenAPI `.yaml` contract and a database schema.
2.  It spawns **Frontend Agent** and **Backend Agent** via `invoke_subagent`.
3.  The Frontend Agent mocks the API based on the `.yaml` and builds the UI.
4.  The Backend Agent builds the Go server based on the `.yaml`.
5.  **Integration Agent** spins up docker-compose and verifies the endpoints.

**Token Efficiency:** The Frontend Agent never sees the Go code. The Backend Agent never sees the CSS. Token burn is slashed by 70%.

## 4. Skill Composition & Lifecycle Management
*   **Self-Improving Skills:** When an agent solves a novel problem (e.g., a specific weird edge case in Kubernetes networking), a **Distillation Hook** extracts the solution and appends it to the relevant `SKILL.md` file autonomously.
*   **Versioning:** Skills are versioned tightly with language updates (e.g., `skill-rust-v1.75` vs `skill-rust-v1.80`).
