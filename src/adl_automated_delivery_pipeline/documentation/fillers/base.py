"""Filler protocol and registry: (Template, DocContext) -> filled markdown.

The registry stores **factories** (zero-arg callables returning a Filler), not
instances, so importing the package never constructs an LLM client and each
``get_filler`` call yields a fresh instance.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from adl_automated_delivery_pipeline.documentation.context import DocContext
from adl_automated_delivery_pipeline.documentation.template import Template


@runtime_checkable
class Filler(Protocol):
    def fill(self, template: Template, context: DocContext) -> str: ...


_FILLERS: dict[str, Callable[[], "Filler"]] = {}


def register_filler(name: str, factory: Callable[[], "Filler"]) -> None:
    """Register a zero-arg factory (e.g. the Filler class itself)."""
    _FILLERS[name] = factory


def get_filler(name: str) -> "Filler":
    try:
        factory = _FILLERS[name]
    except KeyError:
        raise ValueError(
            f"Unknown filler {name!r}. Registered: {sorted(_FILLERS)}"
        ) from None
    return factory()
