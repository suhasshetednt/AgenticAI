"""Renderer protocol and registry: markdown string -> output file."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from adl_automated_delivery_pipeline.documentation.context import DocContext


@runtime_checkable
class Renderer(Protocol):
    extension: str

    def render(self, markdown: str, out_path: Path, context: DocContext) -> Path: ...


_RENDERERS: dict[str, Renderer] = {}


def register_renderer(fmt: str, renderer: Any) -> None:
    _RENDERERS[fmt] = renderer


def get_renderer(fmt: str) -> Renderer:
    try:
        return _RENDERERS[fmt]
    except KeyError:
        raise ValueError(
            f"Unknown format {fmt!r}. Registered: {sorted(_RENDERERS)}"
        ) from None
