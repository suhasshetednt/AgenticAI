# Generic Documentation Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the hardcoded `DocumentationAgent` into a generic, source-agnostic, template-driven agent: `context + markdown template → single-pass fill → pluggable renderer (markdown + branded .docx)`.

**Architecture:** New `documentation/` subpackage with four decoupled units — `DocContext` (facts), `Template` (markdown skeleton parser), `Filler` (LLM fills the template), `Renderer` (markdown → output format). A `jira_to_context` adapter feeds the agent today; `agents/doc_agent.py` becomes a backward-compat shim so `adl-doc` and the pipeline keep working.

**Tech Stack:** Python 3.11, `python-docx` (present), `markdown-it-py` (new, pure-Python), `langchain-anthropic` via `adl_automated_delivery_pipeline.llm.make_claude`, `pytest` (`-m unit`).

**Spec:** `docs/superpowers/specs/2026-06-05-generic-documentation-agent-design.md`

**Conventions (enforced):** full type annotations; module logger not `print()` in library code; specific exceptions only; `datetime.now(timezone.utc)`; build LLMs only via `…llm`; `black` line-length 100. All new tests use `from __future__ import annotations` and `@pytest.mark.unit`. `tests/conftest.py` already puts `src/` on `sys.path` and sets dummy Jira env — no extra fixtures needed.

---

## File Structure

**Create:**
- `src/adl_automated_delivery_pipeline/documentation/__init__.py` — public exports + renderer/filler registration
- `src/adl_automated_delivery_pipeline/documentation/context.py` — `DocContext`
- `src/adl_automated_delivery_pipeline/documentation/template.py` — `Section`, `Template`, `resolve_placeholders`
- `src/adl_automated_delivery_pipeline/documentation/brand.py` — ASL colours + python-docx helpers
- `src/adl_automated_delivery_pipeline/documentation/fillers/__init__.py` — registers `single_pass`
- `src/adl_automated_delivery_pipeline/documentation/fillers/base.py` — `Filler` protocol + registry
- `src/adl_automated_delivery_pipeline/documentation/fillers/single_pass.py` — `SinglePassFiller`
- `src/adl_automated_delivery_pipeline/documentation/renderers/__init__.py` — registers `md` + `docx`
- `src/adl_automated_delivery_pipeline/documentation/renderers/base.py` — `Renderer` protocol + registry
- `src/adl_automated_delivery_pipeline/documentation/renderers/markdown.py` — `MarkdownRenderer`
- `src/adl_automated_delivery_pipeline/documentation/renderers/docx.py` — `DocxRenderer`
- `src/adl_automated_delivery_pipeline/documentation/adapters/__init__.py`
- `src/adl_automated_delivery_pipeline/documentation/adapters/jira.py` — `jira_to_context` (implemented)
- `src/adl_automated_delivery_pipeline/documentation/adapters/sprint.py` — stub + TODO
- `src/adl_automated_delivery_pipeline/documentation/adapters/meeting.py` — stub + TODO
- `src/adl_automated_delivery_pipeline/documentation/adapters/dremio.py` — stub + TODO
- `src/adl_automated_delivery_pipeline/documentation/agent.py` — `DocumentationAgent`
- `src/adl_automated_delivery_pipeline/templates/technical_implementation_document.md` — TID skeleton
- `tests/test_documentation_context.py`, `…_template.py`, `…_renderers.py`, `…_filler.py`, `…_adapters.py`, `…_agent.py`

**Modify:**
- `src/adl_automated_delivery_pipeline/agents/doc_agent.py` — replace body with compat shim
- `requirements.txt` — add `markdown-it-py`
- `pyproject.toml:16-28` — add `markdown-it-py>=3.0` to `dependencies`

---

## Task 1: Add the markdown-it-py dependency

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml:16-28`

- [ ] **Step 1: Add to requirements.txt**

Append this line to `requirements.txt`:

```
markdown-it-py>=3.0
```

- [ ] **Step 2: Add to pyproject dependencies**

In `pyproject.toml`, inside the `dependencies = [...]` list (after `"python-docx>=1.2",`), add:

```toml
    "markdown-it-py>=3.0",
```

- [ ] **Step 3: Install it**

Run: `pip install "markdown-it-py>=3.0"`
Expected: `Successfully installed markdown-it-py-3.x mdurl-0.x`

- [ ] **Step 4: Verify import + table rule available**

Run: `python -c "from markdown_it import MarkdownIt; md=MarkdownIt('commonmark').enable('table'); print('ok', len(md.parse('|a|b|\n|-|-|\n|1|2|')))"`
Expected: prints `ok` and a non-zero token count.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt pyproject.toml
git commit -m "build(doc-agent): add markdown-it-py dependency"
```

---

## Task 2: DocContext

**Files:**
- Create: `src/adl_automated_delivery_pipeline/documentation/__init__.py` (empty for now)
- Create: `src/adl_automated_delivery_pipeline/documentation/context.py`
- Test: `tests/test_documentation_context.py`

- [ ] **Step 1: Create the empty package marker**

Create `src/adl_automated_delivery_pipeline/documentation/__init__.py` with a single line (real exports are added in Task 12):

```python
"""Generic, template-driven documentation agent."""
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_documentation_context.py`:

```python
"""Unit tests for DocContext fact resolution."""

from __future__ import annotations

import pytest

from adl_automated_delivery_pipeline.documentation.context import DocContext


@pytest.mark.unit
def test_get_resolves_title_subtitle_dotted_and_bare_keys() -> None:
    ctx = DocContext(
        title="ADL-1729 VDS",
        subtitle="Add carrier codes",
        metadata={"prepared_by": "DnT"},
        data={"vds_path": "dremio-db.occ.aslb_business", "rows": [1, 2]},
    )
    assert ctx.get("title") == "ADL-1729 VDS"
    assert ctx.get("subtitle") == "Add carrier codes"
    assert ctx.get("metadata.prepared_by") == "DnT"
    assert ctx.get("data.vds_path") == "dremio-db.occ.aslb_business"
    assert ctx.get("vds_path") == "dremio-db.occ.aslb_business"  # bare -> data
    assert ctx.get("prepared_by") == "DnT"                       # bare -> metadata
    assert ctx.get("missing", default="-") == "-"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_documentation_context.py -v`
Expected: FAIL — `ModuleNotFoundError: ...documentation.context`.

- [ ] **Step 4: Write minimal implementation**

Create `src/adl_automated_delivery_pipeline/documentation/context.py`:

```python
"""DocContext — a source-agnostic container of facts a document references."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocContext:
    """Facts the documentation agent writes about. Built by adapters; the agent
    itself never imports a specific source (Jira, etc.)."""

    title: str
    subtitle: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, path: str, default: Any = "") -> Any:
        """Resolve a fact by path.

        - ``"title"`` / ``"subtitle"`` -> the attributes.
        - ``"metadata.x"`` / ``"data.y"`` -> dotted lookups into those dicts.
        - a bare key -> ``data`` first, then ``metadata``.
        Returns ``default`` if nothing matches.
        """
        if path == "title":
            return self.title
        if path == "subtitle":
            return self.subtitle

        parts = path.split(".")
        if len(parts) > 1 and parts[0] in ("metadata", "data"):
            cur: Any = getattr(self, parts[0])
            for key in parts[1:]:
                if isinstance(cur, dict) and key in cur:
                    cur = cur[key]
                else:
                    return default
            return cur

        if path in self.data:
            return self.data[path]
        if path in self.metadata:
            return self.metadata[path]
        return default
```

- [ ] **Step 5: Run test + commit**

Run: `pytest tests/test_documentation_context.py -v`
Expected: PASS.

```bash
git add src/adl_automated_delivery_pipeline/documentation/__init__.py \
        src/adl_automated_delivery_pipeline/documentation/context.py \
        tests/test_documentation_context.py
git commit -m "feat(doc-agent): add DocContext fact container"
```

---

## Task 3: Template parsing + placeholder resolution

**Files:**
- Create: `src/adl_automated_delivery_pipeline/documentation/template.py`
- Test: `tests/test_documentation_template.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_documentation_template.py`:

```python
"""Unit tests for Template parsing and placeholder resolution."""

from __future__ import annotations

import pytest

from adl_automated_delivery_pipeline.documentation.context import DocContext
from adl_automated_delivery_pipeline.documentation.template import (
    Template,
    resolve_placeholders,
)

_SKELETON = """# {{title}}

## Risks
<!-- list 3-5 technical risks with mitigation as a table -->

| Risk | Mitigation |
|------|------------|
"""


@pytest.mark.unit
def test_parses_sections_levels_and_instructions() -> None:
    tpl = Template(_SKELETON)
    headings = [(s.heading, s.level) for s in tpl.sections]
    assert ("{{title}}", 1) in headings
    assert ("Risks", 2) in headings
    risks = next(s for s in tpl.sections if s.heading == "Risks")
    assert "technical risks" in risks.instruction
    assert "| Risk | Mitigation |" in risks.body_hint


@pytest.mark.unit
def test_required_keys_finds_placeholders() -> None:
    assert Template(_SKELETON).required_keys() == {"title"}


@pytest.mark.unit
def test_resolve_placeholders_substitutes_from_context() -> None:
    ctx = DocContext(title="ADL-1729", data={"vds": "occ.aslb"})
    out = resolve_placeholders("# {{title}} -> {{data.vds}}", ctx)
    assert out == "# ADL-1729 -> occ.aslb"


@pytest.mark.unit
def test_load_unknown_name_lists_available(tmp_path) -> None:
    (tmp_path / "alpha.md").write_text("# A", encoding="utf-8")
    with pytest.raises(FileNotFoundError) as exc:
        Template.load("does_not_exist", templates_dir=tmp_path)
    assert "alpha" in str(exc.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentation_template.py -v`
Expected: FAIL — module `template` not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/adl_automated_delivery_pipeline/documentation/template.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_documentation_template.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/adl_automated_delivery_pipeline/documentation/template.py \
        tests/test_documentation_template.py
git commit -m "feat(doc-agent): add Template parser + placeholder resolution"
```

---

## Task 4: brand.py (ASL styling helpers)

**Files:**
- Create: `src/adl_automated_delivery_pipeline/documentation/brand.py`
- Test: `tests/test_documentation_renderers.py` (created here, extended in Task 5/6)

These helpers are extracted from the existing `agents/doc_agent.py` so the
branded look is preserved and reusable.

- [ ] **Step 1: Write the failing test**

Create `tests/test_documentation_renderers.py`:

```python
"""Unit tests for brand helpers and renderers (assert on the docx object model)."""

from __future__ import annotations

import pytest
from docx import Document

from adl_automated_delivery_pipeline.documentation import brand


@pytest.mark.unit
def test_add_heading_sets_navy_for_level1() -> None:
    doc = Document()
    brand.add_heading(doc, "Section", level=1)
    para = doc.paragraphs[-1]
    assert para.runs[0].text == "Section"
    assert para.runs[0].font.color.rgb == brand.COLOR_NAVY


@pytest.mark.unit
def test_add_table_builds_header_plus_rows_and_pads_short_rows() -> None:
    doc = Document()
    brand.add_table(doc, ["A", "B"], [["1", "2"], ["3"]])
    table = doc.tables[-1]
    assert len(table.rows) == 3            # header + 2 data rows
    assert table.rows[0].cells[0].text == "A"
    assert table.rows[2].cells[1].text == ""  # short row padded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentation_renderers.py -v`
Expected: FAIL — module `brand` not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/adl_automated_delivery_pipeline/documentation/brand.py`:

```python
"""ASL Airlines brand styling helpers for python-docx documents."""

from __future__ import annotations

from typing import Any

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

COLOR_NAVY = RGBColor(0x00, 0x38, 0x6B)
COLOR_GOLD = RGBColor(0xC8, 0x9A, 0x00)
COLOR_DARK = RGBColor(0x1A, 0x1A, 0x1A)
_HEADER_BG = "00386B"


def _set_cell_bg(cell: Any, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def add_heading(doc: Any, text: str, level: int) -> None:
    para = doc.add_heading(text, level=level)
    for run in para.runs:
        run.font.color.rgb = COLOR_NAVY if level == 1 else COLOR_DARK
        run.font.bold = True


def add_paragraph(doc: Any, text: str, size: int = 10) -> None:
    para = doc.add_paragraph(text)
    if para.runs:
        para.runs[0].font.size = Pt(size)


def add_bullet(doc: Any, text: str) -> None:
    para = doc.add_paragraph(text, style="List Bullet")
    for run in para.runs:
        run.font.size = Pt(10)


def add_code(doc: Any, text: str) -> None:
    para = doc.add_paragraph()
    run = para.add_run(text)
    run.font.name = "Courier New"
    run.font.size = Pt(8)


def add_table(doc: Any, headers: list[str], rows: list[list[str]]) -> None:
    cols = len(headers)
    table = doc.add_table(rows=1 + len(rows), cols=cols)
    table.style = "Table Grid"
    for idx, label in enumerate(headers):
        cell = table.rows[0].cells[idx]
        _set_cell_bg(cell, _HEADER_BG)
        cell.text = ""
        run = cell.paragraphs[0].add_run(label)
        run.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for r_idx, row in enumerate(rows, start=1):
        for c_idx in range(cols):
            value = row[c_idx] if c_idx < len(row) else ""
            cell = table.rows[r_idx].cells[c_idx]
            cell.text = str(value)
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(9)
    doc.add_paragraph()


def set_page_margins(doc: Any) -> None:
    for section in doc.sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_documentation_renderers.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/adl_automated_delivery_pipeline/documentation/brand.py \
        tests/test_documentation_renderers.py
git commit -m "feat(doc-agent): add reusable ASL brand helpers"
```

---

## Task 5: Renderer protocol, registry, and MarkdownRenderer

**Files:**
- Create: `src/adl_automated_delivery_pipeline/documentation/renderers/__init__.py`
- Create: `src/adl_automated_delivery_pipeline/documentation/renderers/base.py`
- Create: `src/adl_automated_delivery_pipeline/documentation/renderers/markdown.py`
- Test: `tests/test_documentation_renderers.py` (extend)

- [ ] **Step 1: Write the failing test (append to the renderers test file)**

Append to `tests/test_documentation_renderers.py`:

```python
from pathlib import Path

from adl_automated_delivery_pipeline.documentation.context import DocContext
from adl_automated_delivery_pipeline.documentation.renderers import (
    base as renderers_base,
)
from adl_automated_delivery_pipeline.documentation import renderers  # noqa: F401  (registers md/docx)


@pytest.mark.unit
def test_get_renderer_unknown_format_lists_registered() -> None:
    with pytest.raises(ValueError) as exc:
        renderers_base.get_renderer("xml")
    assert "md" in str(exc.value)


@pytest.mark.unit
def test_markdown_renderer_writes_file_verbatim(tmp_path: Path) -> None:
    r = renderers_base.get_renderer("md")
    out = r.render("# Hello\n\nBody", tmp_path / "doc.md", DocContext(title="x"))
    assert out.read_text(encoding="utf-8") == "# Hello\n\nBody"
    assert out.suffix == ".md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentation_renderers.py -v`
Expected: FAIL — `renderers` package not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/adl_automated_delivery_pipeline/documentation/renderers/base.py`:

```python
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
```

Create `src/adl_automated_delivery_pipeline/documentation/renderers/markdown.py`:

```python
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
```

Create `src/adl_automated_delivery_pipeline/documentation/renderers/__init__.py`:

```python
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
```

> NOTE: `__init__.py` imports `DocxRenderer`, built in Task 6. Until Task 6
> lands, temporarily comment out the `docx` import + registration lines, or do
> Task 6 before running the package-level import test. The per-module tests in
> this task import `renderers.base`/`renderers.markdown` directly and pass
> independently.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_documentation_renderers.py -k "markdown or unknown_format or add_" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/adl_automated_delivery_pipeline/documentation/renderers/base.py \
        src/adl_automated_delivery_pipeline/documentation/renderers/markdown.py \
        src/adl_automated_delivery_pipeline/documentation/renderers/__init__.py \
        tests/test_documentation_renderers.py
git commit -m "feat(doc-agent): add renderer registry + MarkdownRenderer"
```

---

## Task 6: DocxRenderer (markdown → branded .docx)

**Files:**
- Create: `src/adl_automated_delivery_pipeline/documentation/renderers/docx.py`
- Test: `tests/test_documentation_renderers.py` (extend)

- [ ] **Step 1: Write the failing test (append)**

Append to `tests/test_documentation_renderers.py`:

```python
from docx import Document as _Doc

_MD = """# Title

Intro paragraph.

## Risks

| Risk | Mitigation |
|------|------------|
| Schema drift | Validate with EXPLAIN |
| Large scan | Add filter |

## Steps

- First step
- Second step

```sql
SELECT 1
```
"""


@pytest.mark.unit
def test_docx_renderer_maps_markdown_to_docx_model(tmp_path: Path) -> None:
    r = renderers_base.get_renderer("docx")
    out = r.render(_MD, tmp_path / "doc.docx", DocContext(title="Title"))
    assert out.suffix == ".docx"

    doc = _Doc(str(out))
    texts = [p.text for p in doc.paragraphs]
    assert "Title" in texts
    assert "Intro paragraph." in texts
    assert any("First step" == t for t in texts)
    # one table with header + 2 rows
    assert len(doc.tables) == 1
    assert doc.tables[0].rows[0].cells[0].text == "Risk"
    assert doc.tables[0].rows[1].cells[1].text == "Validate with EXPLAIN"
    assert len(doc.tables[0].rows) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentation_renderers.py::test_docx_renderer_maps_markdown_to_docx_model -v`
Expected: FAIL — `renderers.docx` not found (and the `docx` renderer unregistered).

- [ ] **Step 3: Write minimal implementation**

Create `src/adl_automated_delivery_pipeline/documentation/renderers/docx.py`:

```python
"""DocxRenderer — parse markdown (markdown-it-py) and render a branded .docx."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from markdown_it import MarkdownIt
from markdown_it.token import Token

from adl_automated_delivery_pipeline.documentation import brand
from adl_automated_delivery_pipeline.documentation.context import DocContext

_MD = MarkdownIt("commonmark").enable("table")


def _inline_text(token: Token) -> str:
    if token.children:
        return "".join(child.content for child in token.children)
    return token.content


def _parse_table(tokens: list[Token], start: int) -> tuple[list[str], list[list[str]], int]:
    headers: list[str] = []
    rows: list[list[str]] = []
    current: list[str] = []
    in_body = False
    j = start + 1
    while tokens[j].type != "table_close":
        ttype = tokens[j].type
        if ttype == "thead_open":
            in_body = False
        elif ttype == "tbody_open":
            in_body = True
        elif ttype == "tr_open":
            current = []
        elif ttype == "tr_close" and in_body:
            rows.append(current)
        elif ttype in ("th_open", "td_open"):
            text = _inline_text(tokens[j + 1])
            (headers if ttype == "th_open" else current).append(text)
            j += 2  # skip the inline + its close (loop adds the final +1)
        j += 1
    return headers, rows, j + 1


def _render_tokens(doc: Any, tokens: list[Token]) -> None:
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        ttype = tok.type
        if ttype == "heading_open":
            brand.add_heading(doc, _inline_text(tokens[i + 1]), level=int(tok.tag[1]))
            i += 3
        elif ttype == "paragraph_open":
            brand.add_paragraph(doc, _inline_text(tokens[i + 1]))
            i += 3
        elif ttype == "bullet_list_open":
            i += 1
            while tokens[i].type != "bullet_list_close":
                if tokens[i].type == "inline":
                    brand.add_bullet(doc, _inline_text(tokens[i]))
                i += 1
            i += 1
        elif ttype == "table_open":
            headers, rows, i = _parse_table(tokens, i)
            brand.add_table(doc, headers, rows)
        elif ttype in ("fence", "code_block"):
            brand.add_code(doc, tok.content.rstrip("\n"))
            i += 1
        else:
            i += 1


class DocxRenderer:
    extension = "docx"

    def render(self, markdown: str, out_path: Path, context: DocContext) -> Path:
        out_path = out_path.with_suffix(".docx")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc = Document()
        brand.set_page_margins(doc)
        _render_tokens(doc, _MD.parse(markdown))
        doc.save(str(out_path))
        return out_path
```

- [ ] **Step 4: Run the full renderers test to verify it passes**

Run: `pytest tests/test_documentation_renderers.py -v`
Expected: PASS (all, including the package-level import that registers `docx`).

- [ ] **Step 5: Commit**

```bash
git add src/adl_automated_delivery_pipeline/documentation/renderers/docx.py \
        tests/test_documentation_renderers.py
git commit -m "feat(doc-agent): add markdown->branded docx renderer"
```

---

## Task 7: Filler protocol, registry, and SinglePassFiller

**Files:**
- Create: `src/adl_automated_delivery_pipeline/documentation/fillers/base.py`
- Create: `src/adl_automated_delivery_pipeline/documentation/fillers/single_pass.py`
- Create: `src/adl_automated_delivery_pipeline/documentation/fillers/__init__.py`
- Test: `tests/test_documentation_filler.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_documentation_filler.py`:

```python
"""Unit tests for the filler registry and SinglePassFiller (no real LLM)."""

from __future__ import annotations

import pytest

from adl_automated_delivery_pipeline.documentation.context import DocContext
from adl_automated_delivery_pipeline.documentation.fillers import base as fillers_base
from adl_automated_delivery_pipeline.documentation.fillers.single_pass import SinglePassFiller
from adl_automated_delivery_pipeline.documentation.template import Template


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    """Captures the prompt and returns canned markdown."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_messages = None

    def invoke(self, messages):  # noqa: ANN001
        self.last_messages = messages
        return _FakeResponse(self.reply)


@pytest.mark.unit
def test_single_pass_resolves_placeholders_and_returns_markdown() -> None:
    llm = _FakeLLM("# ADL-1729\n\n## Risks\n\n| Risk | Mitigation |\n|--|--|\n| x | y |")
    filler = SinglePassFiller(llm=llm)
    tpl = Template("# {{title}}\n\n## Risks\n<!-- list risks -->\n")
    ctx = DocContext(title="ADL-1729")

    out = filler.fill(tpl, ctx)

    assert out.startswith("# ADL-1729")
    # the prompt sent to the LLM had placeholders already resolved
    human = str(llm.last_messages[-1].content)
    assert "{{title}}" not in human
    assert "ADL-1729" in human


@pytest.mark.unit
def test_filler_registry_returns_single_pass() -> None:
    import adl_automated_delivery_pipeline.documentation.fillers  # noqa: F401
    assert isinstance(fillers_base.get_filler("single_pass"), SinglePassFiller)


@pytest.mark.unit
def test_get_filler_unknown_raises() -> None:
    with pytest.raises(ValueError):
        fillers_base.get_filler("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentation_filler.py -v`
Expected: FAIL — `fillers` package not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/adl_automated_delivery_pipeline/documentation/fillers/base.py`:

```python
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
```

Create `src/adl_automated_delivery_pipeline/documentation/fillers/single_pass.py`:

```python
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
```

Create `src/adl_automated_delivery_pipeline/documentation/fillers/__init__.py`:

```python
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
```

> NOTE: the registry stores the **class as a factory**. `get_filler("single_pass")`
> returns `SinglePassFiller()`, which is API-key-free because the Claude client is
> built lazily on the first `fill()` call.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_documentation_filler.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/adl_automated_delivery_pipeline/documentation/fillers/ \
        tests/test_documentation_filler.py
git commit -m "feat(doc-agent): add filler registry + SinglePassFiller"
```

---

## Task 8: Jira adapter + source stubs

**Files:**
- Create: `src/adl_automated_delivery_pipeline/documentation/adapters/__init__.py`
- Create: `src/adl_automated_delivery_pipeline/documentation/adapters/jira.py`
- Create: `src/adl_automated_delivery_pipeline/documentation/adapters/sprint.py`
- Create: `src/adl_automated_delivery_pipeline/documentation/adapters/meeting.py`
- Create: `src/adl_automated_delivery_pipeline/documentation/adapters/dremio.py`
- Test: `tests/test_documentation_adapters.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_documentation_adapters.py`:

```python
"""Unit tests for the Jira adapter (TicketRequirements -> DocContext)."""

from __future__ import annotations

import pytest

from adl_automated_delivery_pipeline.documentation.adapters.jira import jira_to_context
from adl_automated_delivery_pipeline.workflows.adl_automated_delivery_pipeline import (
    TicketRequirements,
)


def _reqs() -> TicketRequirements:
    return TicketRequirements(
        ticket_id="ADL-1729",
        summary="Add carrier codes PH/QF",
        business_requirement="Include PH and QF in the ASLB business VDS.",
        source_database="occ",
        source_tables=["occ.aslb_business"],
        output_fields=[{"name": "carrier_code", "description": "IATA carrier"}],
        transformations=["filter carrier in (PH, QF)"],
        filter_conditions=["carrier_code IN ('PH','QF')"],
        acceptance_criteria=["PH and QF rows appear"],
        extra_notes="High priority",
    )


@pytest.mark.unit
def test_jira_to_context_maps_fields() -> None:
    ctx = jira_to_context(_reqs(), sql="SELECT 1", vds_path="dremio-db.occ.aslb_business")
    assert ctx.title == "ADL-1729"
    assert "Add carrier codes" in ctx.subtitle
    assert ctx.metadata["ticket_id"] == "ADL-1729"
    assert ctx.data["source_tables"] == ["occ.aslb_business"]
    assert ctx.data["sql"] == "SELECT 1"
    assert ctx.data["vds_path"] == "dremio-db.occ.aslb_business"


@pytest.mark.unit
def test_source_stubs_raise_not_implemented() -> None:
    from adl_automated_delivery_pipeline.documentation.adapters import (
        dremio,
        meeting,
        sprint,
    )
    for fn in (sprint.sprint_to_context, meeting.meeting_to_context, dremio.dremio_to_context):
        with pytest.raises(NotImplementedError):
            fn(object())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentation_adapters.py -v`
Expected: FAIL — adapters package not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/adl_automated_delivery_pipeline/documentation/adapters/__init__.py`:

```python
"""Context adapters: convert a specific source into a generic DocContext."""
```

Create `src/adl_automated_delivery_pipeline/documentation/adapters/jira.py`:

```python
"""Jira adapter — TicketRequirements (+ optional SQL/VDS) -> DocContext."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from adl_automated_delivery_pipeline.documentation.context import DocContext


def jira_to_context(reqs: Any, sql: str = "", vds_path: str = "") -> DocContext:
    """Map a TicketRequirements dataclass into a generic DocContext."""
    prepared = datetime.now(timezone.utc).strftime("%d %B %Y")
    return DocContext(
        title=reqs.ticket_id,
        subtitle=reqs.summary,
        metadata={
            "ticket_id": reqs.ticket_id,
            "team": "DnT Infotech - DataLake Team",
            "prepared": prepared,
        },
        data={
            "summary": reqs.summary,
            "business_requirement": reqs.business_requirement,
            "source_database": reqs.source_database,
            "source_tables": list(reqs.source_tables),
            "output_fields": list(reqs.output_fields),
            "transformations": list(reqs.transformations),
            "filter_conditions": list(reqs.filter_conditions),
            "acceptance_criteria": list(reqs.acceptance_criteria),
            "extra_notes": reqs.extra_notes,
            "sql": sql,
            "vds_path": vds_path,
        },
    )
```

Create `src/adl_automated_delivery_pipeline/documentation/adapters/sprint.py`:

```python
"""Sprint adapter (stub). See adapters/jira.py for the reference implementation."""

from __future__ import annotations

from typing import Any

from adl_automated_delivery_pipeline.documentation.context import DocContext


def sprint_to_context(sprint: Any) -> DocContext:
    # TODO: map sprint summary/health data into a DocContext for sprint reports
    raise NotImplementedError("sprint_to_context is not implemented yet")
```

Create `src/adl_automated_delivery_pipeline/documentation/adapters/meeting.py`:

```python
"""Meeting-notes adapter (stub). See adapters/jira.py for the reference impl."""

from __future__ import annotations

from typing import Any

from adl_automated_delivery_pipeline.documentation.context import DocContext


def meeting_to_context(notes: Any) -> DocContext:
    # TODO: map meeting notes / action items into a DocContext
    raise NotImplementedError("meeting_to_context is not implemented yet")
```

Create `src/adl_automated_delivery_pipeline/documentation/adapters/dremio.py`:

```python
"""Dremio-metadata adapter (stub). See adapters/jira.py for the reference impl."""

from __future__ import annotations

from typing import Any

from adl_automated_delivery_pipeline.documentation.context import DocContext


def dremio_to_context(metadata: Any) -> DocContext:
    # TODO: map Dremio VDS/catalog metadata into a DocContext (data dictionaries)
    raise NotImplementedError("dremio_to_context is not implemented yet")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_documentation_adapters.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/adl_automated_delivery_pipeline/documentation/adapters/ \
        tests/test_documentation_adapters.py
git commit -m "feat(doc-agent): add jira context adapter + source stubs"
```

---

## Task 9: DocumentationAgent orchestrator

**Files:**
- Create: `src/adl_automated_delivery_pipeline/documentation/agent.py`
- Test: `tests/test_documentation_agent.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_documentation_agent.py`:

```python
"""End-to-end (offline) test of DocumentationAgent using a stub filler."""

from __future__ import annotations

from pathlib import Path

import pytest

from adl_automated_delivery_pipeline.documentation.agent import DocumentationAgent
from adl_automated_delivery_pipeline.documentation.context import DocContext
from adl_automated_delivery_pipeline.documentation.fillers.base import register_filler


class _StubFiller:
    def fill(self, template, context):  # noqa: ANN001
        return "# Title\n\nBody paragraph.\n\n## Steps\n\n- one\n- two\n"


@pytest.mark.unit
def test_generate_writes_requested_formats(tmp_path: Path) -> None:
    register_filler("stub", _StubFiller)  # factory = the class itself
    agent = DocumentationAgent()
    ctx = DocContext(title="ADL-1729")

    paths = agent.generate(
        ctx,
        template=str(_write_template(tmp_path)),
        formats=["md", "docx"],
        out_dir=tmp_path / "out",
        filler="stub",
    )

    suffixes = sorted(p.suffix for p in paths)
    assert suffixes == [".docx", ".md"]
    assert all(p.exists() for p in paths)


def _write_template(tmp_path: Path) -> Path:
    p = tmp_path / "t.md"
    p.write_text("# {{title}}\n\n## Steps\n<!-- list steps -->\n", encoding="utf-8")
    return p


@pytest.mark.unit
def test_generate_unknown_format_raises(tmp_path: Path) -> None:
    register_filler("stub", _StubFiller)  # factory = the class itself
    agent = DocumentationAgent()
    with pytest.raises(ValueError):
        agent.generate(
            DocContext(title="x"),
            template=str(_write_template(tmp_path)),
            formats=["xml"],
            out_dir=tmp_path,
            filler="stub",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentation_agent.py -v`
Expected: FAIL — `agent` module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/adl_automated_delivery_pipeline/documentation/agent.py`:

```python
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
_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(text: str) -> str:
    return _SLUG.sub("_", text).strip("_") or "document"


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

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        stem = f"{_slug(context.title)}_{ts}"

        paths: list[Path] = []
        for fmt in fmts:
            renderer = get_renderer(fmt)  # raises ValueError on unknown format
            out_path = out_dir / f"{stem}.{renderer.extension}"
            paths.append(renderer.render(filled, out_path, context))
            logger.info("Rendered %s", paths[-1])
        return paths
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_documentation_agent.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/adl_automated_delivery_pipeline/documentation/agent.py \
        tests/test_documentation_agent.py
git commit -m "feat(doc-agent): add DocumentationAgent orchestrator"
```

---

## Task 10: TID skeleton template

**Files:**
- Create: `src/adl_automated_delivery_pipeline/templates/technical_implementation_document.md`
- Test: `tests/test_documentation_agent.py` (extend)

This converts the existing hardcoded 12-section TID into a markdown skeleton so
the default behaviour is preserved but now template-driven.

- [ ] **Step 1: Write the failing test (append)**

Append to `tests/test_documentation_agent.py`:

```python
@pytest.mark.unit
def test_default_tid_template_loads_and_has_core_sections() -> None:
    from adl_automated_delivery_pipeline.documentation.template import Template

    tpl = Template.load("technical_implementation_document")
    headings = {s.heading for s in tpl.sections}
    for expected in ("Risks & Mitigation", "Data Dictionary", "Sign-off"):
        assert expected in headings
    assert "title" in tpl.required_keys()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentation_agent.py::test_default_tid_template_loads_and_has_core_sections -v`
Expected: FAIL — `FileNotFoundError` (template absent).

- [ ] **Step 3: Create the template**

Create `src/adl_automated_delivery_pipeline/templates/technical_implementation_document.md`:

```markdown
# {{title}}

{{subtitle}}

Prepared: {{metadata.prepared}}  |  {{metadata.team}}

## 1. Project
<!-- one line: the project this work belongs to (ASL Airlines — ADL DataLake Integration) -->

## 2. Team
<!-- the delivery team name -->

## 3. Stakeholders
<!-- bullet list of stakeholders with role and organisation -->

## 4. Initial Requirements
<!-- a 2-3 sentence narrative of the business context, then a bullet list of what each VDS/output delivers, grounded in data.business_requirement -->

## 5. Additional Requirements
<!-- bullet list of edge cases, null/exclusion handling, data-quality and scope constraints from data.transformations and data.filter_conditions -->

## 6. Risks & Mitigation
<!-- a table of 3-5 technical/data/performance risks and their mitigations -->

| Risk | Mitigation |
|------|------------|

## 7. Process Continuity
<!-- a table: what happens if a source is missing or the VDS is unavailable, and the fallback -->

| Issue | Mitigation |
|-------|------------|

## 8. Implementation

### 8.1 Data Sources
<!-- a table of source tables from data.source_tables: name, full path, description -->

| Table Name | Full Path | Description |
|------------|-----------|-------------|

### 8.2 Interface Process
<!-- for each VDS/component, a short heading then bullet steps describing select, joins, filters, output naming, grounded in data.transformations and data.filter_conditions -->

## 9. Data Dictionary
<!-- one table row per output field in data.output_fields: Dremio field, source field, derivation logic -->

| Dremio Field | Source Field | Logic / Derivation |
|--------------|--------------|--------------------|

## 10. Milestones
<!-- a table of delivery milestones with day estimates summing to 9-14 working days -->

| Milestone | Days |
|-----------|------|

## 11. Reference

### 11.1 VDS Output Path
<!-- state the VDS output path from data.vds_path, or a reasonable default under dremio-db -->

### 11.2 Key Business Rules
<!-- bullet list of the key business rules: date/status filters, null handling, deduplication/grouping -->

### 11.3 Access Control
<!-- one sentence: who has SELECT vs write access to the VDS output -->

## 12. Sign-off
<!-- a table with columns Role, Name, Date and rows for Technical Lead, Development Lead, QA/Tester, Business Owner (leave Date blank) -->

| Role | Name | Date |
|------|------|------|
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_documentation_agent.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/adl_automated_delivery_pipeline/templates/technical_implementation_document.md \
        tests/test_documentation_agent.py
git commit -m "feat(doc-agent): add TID markdown skeleton template"
```

---

## Task 11: Backward-compat shim + package exports

**Files:**
- Modify: `src/adl_automated_delivery_pipeline/agents/doc_agent.py` (replace entirely)
- Modify: `src/adl_automated_delivery_pipeline/documentation/__init__.py`
- Test: `tests/test_documentation_agent.py` (extend) + existing `tests/test_smoke.py` must still pass

- [ ] **Step 1: Write the failing test (append)**

Append to `tests/test_documentation_agent.py`:

```python
@pytest.mark.unit
def test_legacy_doc_agent_shim_delegates(tmp_path, monkeypatch) -> None:
    """The legacy DocumentationAgent(reqs, sql, vds_path) signature still works."""
    import adl_automated_delivery_pipeline.agents.doc_agent as legacy
    from adl_automated_delivery_pipeline.documentation.fillers.base import register_filler

    register_filler("stub", _StubFiller)  # factory = the class itself
    # Force the shim to use the offline stub filler and a temp output dir.
    monkeypatch.setattr(legacy, "_LEGACY_FILLER", "stub", raising=False)

    from adl_automated_delivery_pipeline.workflows.adl_automated_delivery_pipeline import (
        TicketRequirements,
    )
    reqs = TicketRequirements(
        ticket_id="ADL-9999",
        summary="Demo",
        business_requirement="b",
        source_database="occ",
        source_tables=["t"],
        output_fields=[{"name": "f", "description": "d"}],
        transformations=[],
        filter_conditions=[],
        acceptance_criteria=[],
    )
    out = legacy.DocumentationAgent().generate(reqs, out_dir=tmp_path)
    assert out.suffix == ".docx"
    assert out.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_documentation_agent.py::test_legacy_doc_agent_shim_delegates -v`
Expected: FAIL — old `doc_agent` has no `_LEGACY_FILLER` / different signature.

- [ ] **Step 3: Replace doc_agent.py with the shim**

Replace the entire contents of `src/adl_automated_delivery_pipeline/agents/doc_agent.py` with:

```python
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
```

- [ ] **Step 4: Update package exports**

Replace `src/adl_automated_delivery_pipeline/documentation/__init__.py` with:

```python
"""Generic, template-driven documentation agent."""

from __future__ import annotations

from adl_automated_delivery_pipeline.documentation.agent import DocumentationAgent
from adl_automated_delivery_pipeline.documentation.context import DocContext
from adl_automated_delivery_pipeline.documentation.renderers.base import get_renderer
from adl_automated_delivery_pipeline.documentation.template import Template

__all__ = ["DocumentationAgent", "DocContext", "Template", "get_renderer"]
```

- [ ] **Step 5: Run the shim test, the smoke test, and commit**

Run: `pytest tests/test_documentation_agent.py tests/test_smoke.py -v`
Expected: PASS (including `test_module_imports[...agents.doc_agent]`).

```bash
git add src/adl_automated_delivery_pipeline/agents/doc_agent.py \
        src/adl_automated_delivery_pipeline/documentation/__init__.py \
        tests/test_documentation_agent.py
git commit -m "refactor(doc-agent): make doc_agent a shim over the generic agent"
```

---

## Task 12: Full suite + quality gates + end-to-end smoke

**Files:** none new — verification only.

- [ ] **Step 1: Run the full unit suite**

Run: `pytest -m unit -v`
Expected: all green, including the new `test_documentation_*` files and existing tests.

- [ ] **Step 2: Type-check and lint the new package**

Run:
```bash
pyright src/adl_automated_delivery_pipeline/documentation
ruff check src/adl_automated_delivery_pipeline/documentation
black --check src/adl_automated_delivery_pipeline/documentation
```
Expected: no errors. Fix any reported issues and re-run.

- [ ] **Step 3: Manual end-to-end (requires ANTHROPIC_API_KEY + config.env)**

Run: `adl-doc ADL-1721`
Expected: prints `Document saved: .../Project Documentation/ADL-1721_<ts>.docx`; open the file and confirm the 12 sections render with navy headings and styled tables (same look as before, now template-driven). This exercises the real `SinglePassFiller`.

- [ ] **Step 4: Commit any formatting fixes**

```bash
git add -A
git commit -m "chore(doc-agent): formatting + lint fixes" || echo "nothing to commit"
```

- [ ] **Step 5: Finish the branch**

Per `superpowers:finishing-a-development-branch`: open a PR from
`feature/generic-documentation-agent` into `main`, or merge locally. Summarise:
new `documentation/` subpackage, `doc_agent.py` now a shim, `adl-doc` unchanged
for users, PDF/Excel/TXT renderers and `SectionFiller` deferred behind seams.

---

## Self-Review Notes (author)

- **Spec coverage:** §2 layout → Tasks 2-11; §3 contracts → DocContext (T2), Template (T3), Filler (T7), Renderer (T5/T6); §4 adapters incl. stubs → T8; §5 data flow → T9 + manual T12.3; §6 backward-compat → T11; §7 error handling → unknown-format (T5/T9), template-not-found (T3); §8 testing → offline stub filler (T9/T11); §9 deps + deferrals → T1 + stubs. All covered.
- **Type consistency:** `get_renderer`/`get_filler` raise `ValueError`; `Renderer.extension` used for filenames in T9; `DocContext.get` dotted-path used by `resolve_placeholders` (T3) and the TID template (T10); `jira_to_context(reqs, sql, vds_path)` signature identical in T8 and the shim (T11).
- **markdown-it tables:** `MarkdownIt("commonmark").enable("table")` (T6) — verified available in T1.4.
- **Import-time safety:** filler registry stores a `__new__` instance so importing the package needs no API key (T7 note); the agent constructs the real filler at run time.
