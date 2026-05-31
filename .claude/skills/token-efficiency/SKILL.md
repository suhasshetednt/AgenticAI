---
name: token-efficiency
description: >
  Actionable prompt patterns that genuinely reduce token usage with Claude.
  Covers natural language instructions, Claude Code CLI techniques, API prompt
  caching, and the caveman skill. Use when user asks "how do I reduce tokens",
  "save tokens", "cheaper Claude", "efficient prompting", or invokes /token-efficiency.
---

# Token Efficiency — Real Patterns That Work

When invoked, display this reference. One-shot — do not change mode or persist anything.

---

## 1. Natural Language Prompt Instructions

These work in any Claude interface. Add to the start of your prompt.

| Goal | Add to your prompt |
|---|---|
| Short answers | `Be concise. One paragraph max.` |
| Skip reasoning | `Output only. No explanation.` |
| Skip examples | `No examples.` |
| Force format | `Respond in JSON only, no prose.` |
| Skip follow-ups | `Do not suggest follow-up questions.` |
| Target audience | `Assume I'm a senior engineer. Skip basics.` |
| Batch items | `Process all 10 items in one response.` |
| Draft quality | `Draft quality — fast over polished.` |

Combine freely: `Be concise. Output only. JSON format. No examples.`

---

## 2. Claude Code CLI — Real Commands

These actually exist in Claude Code (`claude` CLI):

| Command | What it does |
|---|---|
| `/clear` | Reset conversation context — next prompt starts fresh |
| `/model` | Switch model interactively (Opus/Sonnet/Haiku) |
| `/help` | Show all available commands |
| `/compact` | Compress conversation history to save context |
| `/cost` | Show token usage for the current session |
| `Esc Esc` | Edit last message without regenerating |

**Model cost tiers** (Haiku cheapest → Opus most capable):
```
claude-haiku-4-5       ← cheapest, fast, good for simple tasks
claude-sonnet-4-6      ← balanced (default)
claude-opus-4-8        ← most capable, most expensive
```

Switch for the task: use Haiku for summarization/formatting, Sonnet for coding, Opus for complex reasoning.

---

## 3. Context Window Discipline

Shorter context = fewer input tokens on every message.

- Start a new conversation when topic changes — don't drag old context
- Use `/clear` in Claude Code when context is bloated
- Paste only the relevant code snippet, not entire files
- For long files: specify line range — `lines 40-80 of utils.py`
- Remove boilerplate from pastes (imports, comments) when they're not relevant

---

## 4. Avoid Re-Asking

Each re-ask regenerates full context cost.

- Ask all sub-questions in one message, not sequentially
- Specify format upfront — `Respond as a markdown table` avoids a follow-up reformat
- Give constraints upfront — `Under 200 words` avoids a follow-up trim
- If Claude missed something, edit the original message (`Esc Esc`) instead of adding a new correction message

---

## 5. API / SDK — Prompt Caching

For developers using the Anthropic SDK, prompt caching is the highest-leverage optimization.
Cached input tokens cost ~10% of normal input price.

```python
# Mark large, stable content with cache_control
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": large_system_context,          # stable: documents, rules, schema
                "cache_control": {"type": "ephemeral"} # cache this block
            },
            {
                "type": "text",
                "text": user_query                     # dynamic: changes each call
            }
        ]
    }
]
```

Rules:
- Cache blocks must be ≥1024 tokens to qualify
- Put stable content first, dynamic content last
- Cache TTL is 5 minutes — reuse within the window
- Works on system prompt, tool definitions, long documents

---

## 6. Caveman Skill (This Project)

The `caveman` skill cuts Claude's *output* tokens ~75% by switching to ultra-compressed
prose — useful when you're reading responses in the terminal and don't need polished prose.

```
/caveman          # full compression (default)
/caveman lite     # lighter — keeps sentence structure
/caveman ultra    # extreme — bare fragments, tables over prose
stop caveman      # back to normal
```

Use `/caveman-stats` to see actual session token savings.

---

## 7. Quick Combination Patterns

```
# Fast answer, no fluff
Be concise. Output only. No examples. No follow-up questions.

# Code output only
Return code only. No explanation. Python.

# Structured data
Respond with a JSON array only. No prose. Schema: [{name, value, unit}]

# Long doc summary
Summarize in 5 bullet points. Each bullet ≤15 words.

# Batch processing
Process each item below in one response. Format: item | result. No explanation.
```

---

## What Doesn't Exist

Common viral "slash commands" that **do not work** in Claude.ai or Claude Code:

`/ghost` `/council` `/brief` `/noexplain` `/cache` `/smart-cache` `/batch:10`
`/context:5` `/quiet` `/format:json` `/limit:500` `/quality:draft` `/model:haiku`
`/timeout:10` `/debug` (as token counter) — **none of these are real commands.**

The behaviors they claim to trigger are achievable with plain English instructions (see Section 1).
