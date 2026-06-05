"""Template — load and parse a markdown skeleton into ordered sections.

Authoring contract:
  * Headings (``#``..``######``) define structure and are preserved verbatim.
  * ``<!-- instruction -->`` HTML comments are per-section guidance to the LLM.
  * ``{{key}}`` placeholders are resolved deterministically from a DocContext.
  * A markdown table header in a section signals "fill this as a table".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from adl_automated_delivery_pipeline.documentation.context import DocContext

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
_PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


@dataclass
class Section:
    heading: str
    level: int
    instruction: str = ""
    body_hint: str = ""


@dataclass
class Template:
    raw: str
    sections: list[Section] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.sections:
            self.sections = self._parse(self.raw)

    @classmethod
    def load(cls, name_or_path: str | Path, templates_dir: Path | None = None) -> "Template":
        """Load by explicit path, or by name from the templates directory."""
        directory = templates_dir or _TEMPLATES_DIR
        candidate = Path(name_or_path)
        if candidate.suffix == ".md" and candidate.exists():
            return cls(candidate.read_text(encoding="utf-8"))
        named = directory / f"{name_or_path}.md"
        if named.exists():
            return cls(named.read_text(encoding="utf-8"))
        available = sorted(p.stem for p in directory.glob("*.md")) if directory.exists() else []
        raise FileNotFoundError(
            f"Template {name_or_path!r} not found in {directory}. Available: {available}"
        )

    def required_keys(self) -> set[str]:
        return set(_PLACEHOLDER.findall(self.raw))

    @staticmethod
    def _parse(raw: str) -> list[Section]:
        sections: list[Section] = []
        current: Section | None = None
        body_lines: list[str] = []

        def flush() -> None:
            if current is not None:
                body = "\n".join(body_lines).strip()
                comment = _COMMENT.search(body)
                current.instruction = comment.group(1).strip() if comment else ""
                current.body_hint = _COMMENT.sub("", body).strip()
                sections.append(current)

        for line in raw.splitlines():
            match = _HEADING.match(line)
            if match:
                flush()
                current = Section(heading=match.group(2).strip(), level=len(match.group(1)))
                body_lines = []
            elif current is not None:
                body_lines.append(line)
        flush()
        return sections


def resolve_placeholders(text: str, context: DocContext) -> str:
    """Replace every ``{{key}}`` with ``context.get(key)``."""
    return _PLACEHOLDER.sub(lambda m: str(context.get(m.group(1))), text)
