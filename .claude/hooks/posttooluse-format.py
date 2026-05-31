#!/usr/bin/env python3
"""PostToolUse hook: auto-format edited Python files with black and ruff."""

from __future__ import annotations

import json
import subprocess
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    if tool_name not in {"Edit", "Write"}:
        return 0

    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not file_path or not str(file_path).endswith(".py"):
        return 0

    for cmd in [
        ["black", "--quiet", str(file_path)],
        ["ruff", "check", "--fix", "--quiet", str(file_path)],
    ]:
        try:
            subprocess.run(cmd, capture_output=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
