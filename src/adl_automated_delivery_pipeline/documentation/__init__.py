"""Generic, template-driven documentation agent."""

from __future__ import annotations

from adl_automated_delivery_pipeline.documentation.agent import DocumentationAgent
from adl_automated_delivery_pipeline.documentation.context import DocContext
from adl_automated_delivery_pipeline.documentation.renderers.base import get_renderer
from adl_automated_delivery_pipeline.documentation.template import Template

__all__ = ["DocumentationAgent", "DocContext", "Template", "get_renderer"]
