"""Filler registration. Importing this package registers all fillers."""

from __future__ import annotations

from adl_automated_delivery_pipeline.documentation.fillers.base import (
    get_filler,
    register_filler,
)
from adl_automated_delivery_pipeline.documentation.fillers.single_pass import SinglePassFiller

# Register the class itself as the factory; SinglePassFiller() is cheap (lazy LLM).
register_filler("single_pass", SinglePassFiller)

__all__ = ["get_filler", "register_filler", "SinglePassFiller"]
