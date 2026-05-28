# 11. UNIVERSAL TECHNOLOGY CAPABILITY ASSESSMENT

## 1. SOFTWARE ENGINEERING
*   **Maturity Level:** High (Monoliths/Frontend) | Low (Distributed/High-Frequency)
*   **Missing Capabilities:** Realtime system orchestration, hard real-time latency verification, edge system cross-compilation testing.
*   **Weak Abstractions:** Treating microservices as adjacent files rather than isolated, network-partitioned entities.
*   **Remediation:** Introduce a `Topology` abstraction layer. Agents must define a bounded context and network contract before editing multi-service codebases.

## 2. PROGRAMMING LANGUAGES
*   **Maturity Level:** High (Python, TS/JS, Go) | Medium (Rust, C++, Java) | Low (Solidity, Haskell, Assembly)
*   **Missing Capabilities:** Autonomous memory leak detection in C/C++, borrow-checker resolution strategies in Rust, gas optimization in Solidity.
*   **Tooling Deficiencies:** The default sandbox terminal lacks specialized toolchains (e.g., `cargo`, `cmake`, `hardhat`) pre-configured with LLM-readable JSON outputs.
*   **Remediation:** Implement **Language-Specific Execution Hooks**. When Rust is detected, the agent autonomously downloads the `rust-analyzer` MCP server to get semantic LSP feedback rather than relying purely on compiler terminal output.

## 3. CLOUD & INFRASTRUCTURE
*   **Maturity Level:** Medium (Terraform, Docker) | Low (Kubernetes multi-node scaling, AWS IAM zero-trust)
*   **Missing Capabilities:** Autonomous verification of infrastructure-as-code (IaC) side effects (e.g., Terraform plan cost estimation).
*   **Orchestration Gaps:** Cannot dynamically mock cloud environments to test deployment scripts.
*   **Remediation:** Integrate a Cloud Testing MCP (e.g., LocalStack). Require a "dry-run" deployment validation step in the workflow before merging any IaC.

## 4. AI / ML / AGENTIC SYSTEMS
*   **Maturity Level:** Very High
*   **Weak Abstractions:** Struggles to autonomously evaluate *other* models objectively without drifting into self-affirmation bias.
*   **Token Inefficiencies:** Fine-tuning pipelines generate massive logs that pollute context.
*   **Remediation:** Pipe all ML training/eval logs to a background metric-aggregation script; only inject final loss/accuracy curves into the agent's prompt.

## 5. DEVOPS / PLATFORM ENGINEERING
*   **Maturity Level:** Low
*   **Missing Capabilities:** Incident management, rollback orchestration, canary deployment monitoring.
*   **Tooling Deficiencies:** No native webhook ingestion to "listen" for a failed GitLab CI pipeline.
*   **Remediation:** Event-Driven Webhook capabilities. Antigravity must be able to expose a local endpoint to receive pipeline callbacks, waking an agent to fix a breaking build asynchronously.

## 6. DATA ENGINEERING
*   **Maturity Level:** Medium (SQL/dbt) | Low (Kafka/Spark streaming)
*   **Missing Autonomous Workflows:** Cannot easily validate big-data transformations autonomously due to sandbox storage and compute limits.
*   **Remediation:** Data Sampling Hooks. Agents must autonomously write scripts to fetch a 1,000-row DataFrame subset to test ETL logic locally.

## 7. CYBERSECURITY
*   **Maturity Level:** Low
*   **Weak Capability Areas:** Zero-trust systems, runtime security, dependency supply chain.
*   **Missing Autonomous Workflows:** Does not autonomously fuzz inputs or run SAST/DAST tools before finalizing an API.
*   **Remediation:** Mandatory Security Verification Subagent. Before any backend PR is generated, a `Cybersecurity Agent` must run `semgrep` or `bandit` on the diff and approve it.

## 8. MOBILE & CROSS-PLATFORM
*   **Maturity Level:** Low
*   **Missing Toolchains:** No autonomous GUI/emulator interaction. It can write Flutter code, but cannot see if the UI renders correctly.
*   **Remediation:** Multimodal integration with automated UI testing frameworks (e.g., Appium + screenshot analysis).

## 9. BLOCKCHAIN & WEB3
*   **Maturity Level:** Very Low (High Risk)
*   **Weak Abstractions:** Lacks intrinsic understanding of chain orchestration and EVM opcodes at a security level.
*   **Remediation:** Strict containment. Web3 code must be piped through formal verification tools (e.g., Halmos, Certora) automatically. Human-in-the-loop is mandatory.

## 10. TESTING & QUALITY ENGINEERING
*   **Maturity Level:** High (Unit testing) | Low (Chaos Engineering, Fuzzing)
*   **Missing Capabilities:** Token-efficient distributed test execution.
*   **Remediation:** Implement Property-Based Testing templates as a default skill.
