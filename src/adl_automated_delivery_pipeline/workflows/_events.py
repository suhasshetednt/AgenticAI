"""Sentinel markers for the live dashboard.

These print one machine-readable line each on stdout, so they ride the existing
websocket log bridge in ``api/app.py``. The browser dashboard parses them to
drive the stage timeline, artifact chips, and approval cards. ``print`` is the
intended contract here (this is the CLI/bridge layer), so it is not a logging
violation.
"""

from __future__ import annotations


def stage(name: str, status: str) -> None:
    """Emit a stage status marker. status is one of: start, done, fail."""
    print(f"::STAGE {name} {status}::")


def artifact(kind: str, value: str) -> None:
    """Emit a produced-artifact marker. kind: docx, sql, vds, qlik."""
    print(f"::ARTIFACT {kind}={value}::")


def approve(kind: str, detail: str) -> None:
    """Emit an approval-needed marker. kind: dremio, qlik."""
    print(f"::APPROVE {kind}={detail}::")


def done() -> None:
    """Emit the run-finished marker."""
    print("::DONE::")
