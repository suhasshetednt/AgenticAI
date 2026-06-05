"""Sprint adapter (stub). See adapters/jira.py for the reference implementation."""

from __future__ import annotations

from typing import Any

from adl_automated_delivery_pipeline.documentation.context import DocContext


def sprint_to_context(sprint: Any) -> DocContext:
    # TODO: map sprint summary/health data into a DocContext for sprint reports
    raise NotImplementedError("sprint_to_context is not implemented yet")
