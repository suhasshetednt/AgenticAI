"""DocumentationAgent — orchestrates template -> fill -> render."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from adl_automated_delivery_pipeline.documentation.context import DocContext
from adl_automated_delivery_pipeline.documentation.fillers.base import get_filler
from adl_automated_delivery_pipeline.documentation.renderers.base import get_renderer
from adl_automated_delivery_pipeline.documentation.template import Template

# Importing these packages registers the built-in fillers/renderers.
import adl_automated_delivery_pipeline.documentation.fillers  # noqa: F401,E402
import adl_automated_delivery_pipeline.documentation.renderers  # noqa: F401,E402

logger = logging.getLogger(__name__)

_DEFAULT_OUT = Path.cwd() / "Project Documentation"
_INVALID_WIN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _doc_prefix(template_name: str) -> str:
    """Map a template name to the ASL document prefix."""
    n = template_name.lower()
    if "technical" in n or "implementation" in n or "tid" in n or "api" in n or "runbook" in n:
        return "ASL Technical Implementation"
    if "requirement" in n or "brd" in n:
        return "ASL Requirements Document"
    if "uat" in n:
        return "ASL UAT"
    return "ASL Production Documentation"


def _safe_filename(text: str) -> str:
    """Strip Windows-invalid filename characters while preserving spaces."""
    return _INVALID_WIN.sub("", str(text)).strip()


class DocumentationAgent:
    """Fill a markdown template from a DocContext and render to output formats."""

    def generate(
        self,
        context: DocContext,
        template: str | Path = "technical_implementation_document",
        formats: Sequence[str] | None = None,
        out_dir: Path | None = None,
        filler: str = "single_pass",
    ) -> list[Path]:
        fmts = list(formats) if formats else ["docx"]
        out_dir = out_dir or _DEFAULT_OUT
        out_dir.mkdir(parents=True, exist_ok=True)

        tpl = Template.load(template)
        filled = get_filler(filler).fill(tpl, context)

        # Tell the docx renderer which branded template to load.
        context.metadata["_docx_template"] = str(template)

        prefix = _doc_prefix(str(template))
        name = _safe_filename(context.subtitle or context.title)
        stem = f"{prefix} - {name}" if name else prefix

        paths: list[Path] = []
        for fmt in fmts:
            renderer = get_renderer(fmt)  # raises ValueError on unknown format
            out_path = out_dir / f"{stem}.{renderer.extension}"
            paths.append(renderer.render(filled, out_path, context))
            logger.info("Rendered %s", paths[-1])
        return paths
