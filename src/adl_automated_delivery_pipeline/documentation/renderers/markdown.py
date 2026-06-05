"""MarkdownRenderer — writes the filled markdown verbatim."""

from __future__ import annotations

from pathlib import Path

from adl_automated_delivery_pipeline.documentation.context import DocContext


class MarkdownRenderer:
    extension = "md"

    def render(self, markdown: str, out_path: Path, context: DocContext) -> Path:
        out_path = out_path.with_suffix(".md")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        return out_path
