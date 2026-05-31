#!/usr/bin/env python3
"""SessionStart hook: show project context on session start."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    project_root = Path(__file__).resolve().parents[2]
    config_exists = (project_root / "config.env").exists() or (project_root / ".env").exists()
    venv_exists = (project_root / "venv" / "Scripts" / "python.exe").exists()

    lines = ["[Jira Agent] ASL Airlines — ADL project (aslairlines.atlassian.net)"]

    if not config_exists:
        lines.append("  ⚠ No config.env found — create it with JIRA_* and GOOGLE_API_KEY vars")
    if not venv_exists:
        lines.append("  ⚠ No venv found — run: python -m venv venv && .\\venv\\Scripts\\Activate.ps1 && pip install -r requirements.txt")

    if config_exists and venv_exists:
        lines.append("  Ready — activate venv: .\\venv\\Scripts\\Activate.ps1")

    context = "\n".join(lines)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
