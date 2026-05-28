# 9. PERFORMANCE & TOKEN OPTIMIZATION ROADMAP

## Optimization Timelines & ROI

### Immediate High-Impact Fixes (0-2 Weeks)
1.  **Implement `<thought>` Token Budgets (ROI: 9/10):**
    *   *Action:* Enforce strict max-lengths on internal reasoning tokens via prompt engineering or injection-layer truncation.
    *   *Savings:* ~10% overall cost reduction.
2.  **Tool Output Minification (ROI: 8/10):**
    *   *Action:* Strip whitespace, markdown padding, and null keys from tool outputs before context injection.
    *   *Savings:* ~5-8% token savings.

### Medium-Term Improvements (1-3 Months)
1.  **Dynamic Skill Loading (ROI: 10/10):**
    *   *Action:* Remove `SKILL.md` contents from the default system prompt. Use a lightweight classifier router to fetch and inject only required skills.
    *   *Savings:* 30-40% context savings per turn.
2.  **Cyclic Guardrails (ROI: 7/10):**
    *   *Action:* Implement state-machine hooks that block the agent if it repeats the same file edit -> fail sequence 3 times.

### Frontier-Level Upgrades (3-6 Months)
1.  **Hierarchical Context Compression Agent (ROI: 10/10):**
    *   *Action:* Deploy a background 8B-parameter local model (or fast cloud model) to continuously squash `transcript.jsonl` into dense semantic state vectors, completely eliminating the linear growth of prompt size.
    *   *Savings:* 80% context savings on deep >50-turn interactions.

### AGI-Scale Architectural Recommendations
1.  **Asynchronous Speculative Decoding & Execution:**
    *   Run multiple subagents on separate branched workspaces simultaneously when faced with architectural ambiguity. Have a Verifier agent compile all branches, test them, and merge the successful branch to main, discarding the rest. This trades raw compute parallelization for extreme reliability and zero human intervention.
