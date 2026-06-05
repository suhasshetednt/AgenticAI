"""Meeting-notes adapter (stub). See adapters/jira.py for the reference impl."""

from __future__ import annotations

from typing import Any

from adl_automated_delivery_pipeline.documentation.context import DocContext


def meeting_to_context(notes: Any) -> DocContext:
    # TODO: map meeting notes / action items into a DocContext
    raise NotImplementedError("meeting_to_context is not implemented yet")
