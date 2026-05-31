"""Pytest configuration and shared fixtures.

Ensures the ``src`` layout package is importable when running tests without an
editable install, and provides dummy required credentials so importing
``config`` never fails in a clean CI environment (no real secrets needed).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Provide harmless defaults for the required Jira settings so ``config.Settings``
# can be constructed in CI. ``setdefault`` means a real config.env / process env
# still wins (config loads env files with override=False).
os.environ.setdefault("JIRA_INSTANCE_URL", "https://example.atlassian.net")
os.environ.setdefault("JIRA_USERNAME", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "dummy-token")
