#!/usr/bin/env python3
"""PreToolUse hook: block obviously destructive commands and protect credentials."""

from __future__ import annotations

import json
import re
import sys

DESTRUCTIVE_PATTERNS = [
    re.compile(r"(^|\s)rm\s+-[rRf]*f[rRf]*(\s|$)"),
    re.compile(r"(^|\s)Remove-Item\s+.*-Recurse.*-Force"),
    re.compile(r"(^|\s)git\s+reset\s+--hard(\s|$)"),
    re.compile(r"(^|\s)git\s+clean\s+-f"),
    re.compile(r"(^|\s)git\s+push\s+.*--force"),
    re.compile(r"(^|\s)drop\s+table", re.IGNORECASE),
    re.compile(r"(^|\s)truncate\s+table", re.IGNORECASE),
]

CREDENTIAL_FILE_PATTERN = re.compile(r"(^|[\\/])(\.env|config\.env)$")


def _ask(reason: str) -> dict:
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

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    if tool_name in {"Write", "Edit"}:
        file_path = tool_input.get("file_path") or tool_input.get("path") or ""
        if CREDENTIAL_FILE_PATTERN.search(str(file_path)):
            print(json.dumps(_ask(
                f"You are about to write to a credentials file: {file_path}. "
                "Confirm this is intentional."
            )))
        return 0

    if tool_name in {"Bash", "PowerShell"}:
        command = tool_input.get("command") if isinstance(tool_input, dict) else ""
        if not isinstance(command, str):
            return 0
        for pattern in DESTRUCTIVE_PATTERNS:
            if pattern.search(command):
                print(json.dumps(_ask(
                    "Potentially destructive command detected. Confirm explicitly."
                )))
                return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
