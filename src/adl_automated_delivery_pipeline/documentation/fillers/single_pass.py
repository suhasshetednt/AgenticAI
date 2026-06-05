"""SinglePassFiller — one low-temperature LLM call fills the whole template."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from adl_automated_delivery_pipeline.config import settings
from adl_automated_delivery_pipeline.documentation.context import DocContext
from adl_automated_delivery_pipeline.documentation.template import (
    Template,
    resolve_placeholders,
)
from adl_automated_delivery_pipeline.llm import make_claude

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a precise technical documentation writer. You are given a markdown "
    "TEMPLATE and a CONTEXT of facts. Fill the template in place. Rules: preserve "
    "every heading and their order exactly; replace each HTML comment instruction "
    "(<!-- ... -->) with real content placed immediately under its heading; output "
    "valid markdown only, no surrounding code fences and no preamble; render any "
    "section that asks for a table as a GitHub pipe table; never invent facts that "
    "are not supported by the context."
)


class SinglePassFiller:
    def __init__(self, llm: Any | None = None) -> None:
        # Lazy: the real client is only built on first fill(), so constructing
        # this filler (e.g. via the registry) needs no API key.
        self._llm = llm

    def _client(self) -> Any:
        if self._llm is None:
            self._llm = make_claude(model=settings.CLAUDE_MODEL, temperature=0.1)
        return self._llm

    def fill(self, template: Template, context: DocContext) -> str:
        skeleton = resolve_placeholders(template.raw, context)
        prompt = (
            f"--- CONTEXT (facts) ---\n{context.data}\n\n"
            f"--- TITLE ---\n{context.title}\n{context.subtitle}\n\n"
            f"--- TEMPLATE TO FILL ---\n{skeleton}\n"
        )
        logger.info("SinglePassFiller: filling template (%d sections)", len(template.sections))
        response = self._client().invoke(
            [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
        )
        return _strip_fences(str(response.content).strip())


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text
