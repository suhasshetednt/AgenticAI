"""Renderer registration. Importing this package registers all renderers."""

from __future__ import annotations

from adl_automated_delivery_pipeline.documentation.renderers.base import (
    get_renderer,
    register_renderer,
)
from adl_automated_delivery_pipeline.documentation.renderers.docx import DocxRenderer
from adl_automated_delivery_pipeline.documentation.renderers.markdown import MarkdownRenderer

register_renderer("md", MarkdownRenderer())
register_renderer("docx", DocxRenderer())

__all__ = ["get_renderer", "register_renderer", "MarkdownRenderer", "DocxRenderer"]
