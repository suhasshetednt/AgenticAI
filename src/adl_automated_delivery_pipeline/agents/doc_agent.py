"""Backward-compatibility shim for the Documentation Agent.

The real implementation now lives in
``adl_automated_delivery_pipeline.documentation``. This module preserves the
legacy ``DocumentationAgent().generate(reqs, sql, vds_path)`` call used by
``workflows/generate_doc.py`` and the pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from adl_automated_delivery_pipeline.documentation.adapters.jira import jira_to_context
from adl_automated_delivery_pipeline.documentation.agent import (
    DocumentationAgent as _GenericDocumentationAgent,
)

# Allows tests to swap in an offline stub filler.
_LEGACY_FILLER = "single_pass"


class DocumentationAgent:
    """Legacy facade. Delegates to the generic, template-driven agent."""

    def __init__(self) -> None:
        self._agent = _GenericDocumentationAgent()

    def generate(
        self,
        reqs: Any,
        sql: str = "",
        vds_path: str = "",
        out_dir: Path | None = None,
    ) -> Path:
        """Generate a branded .docx Technical Implementation Document.

        Returns the single output Path (legacy contract).
        """
        context = jira_to_context(reqs, sql=sql, vds_path=vds_path)
        paths = self._agent.generate(
            context,
            template="technical_implementation_document",
            formats=["docx"],
            out_dir=out_dir,
            filler=_LEGACY_FILLER,
        )
        return paths[0]
