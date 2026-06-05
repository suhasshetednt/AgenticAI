"""Dremio-metadata adapter (stub). See adapters/jira.py for the reference impl."""

from __future__ import annotations

from typing import Any

from adl_automated_delivery_pipeline.documentation.context import DocContext


def dremio_to_context(metadata: Any) -> DocContext:
    # TODO: map Dremio VDS/catalog metadata into a DocContext (data dictionaries)
    raise NotImplementedError("dremio_to_context is not implemented yet")
