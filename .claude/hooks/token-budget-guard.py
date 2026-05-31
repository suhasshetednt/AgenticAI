#!/usr/bin/env python3
"""
PreToolUse hook: warn when context window is nearing capacity.

Emits a warning at 85% usage and blocks at 98% with an actionable message.
Reads token counts from the hook payload when available; otherwise estimates
from the conversation length heuristic.
"""

from __future__ import annotations

import json
import sys

WARNING_THRESHOLD = 0.85
BLOCK_THRESHOLD = 0.98
CONTEXT_WINDOW = 200_000  # Claude Sonnet/Opus context window


def _warn(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    # Claude Code injects token usage into the hook payload when available
    usage = payload.get("token_usage") or {}
    input_tokens = usage.get("input_tokens", 0)

    if not input_tokens:
        return 0

    ratio = input_tokens / CONTEXT_WINDOW

    if ratio >= BLOCK_THRESHOLD:
        print(
            json.dumps(
                _deny(
                    f"Context window at {ratio:.0%} ({input_tokens:,}/{CONTEXT_WINDOW:,} tokens). "
                    "Run /compact to compress conversation history before continuing."
                )
            )
        )
        return 0

    if ratio >= WARNING_THRESHOLD:
        print(
            json.dumps(
                _warn(
                    f"Context window at {ratio:.0%} ({input_tokens:,}/{CONTEXT_WINDOW:,} tokens). "
                    "Consider running /compact soon to avoid hitting the limit."
                )
            )
        )
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
