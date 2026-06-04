# Spec: Generic, Template-Driven Documentation Agent

**Date:** 2026-06-05
**Status:** Approved (design) — ready for implementation plan
**Project:** `adl_automated_delivery_pipeline` (ASL Airlines ADL — DnT Infotech)

## 1. Goal & Scope

Refactor the current **hardcoded** `DocumentationAgent` into a **generic,
source-agnostic, template-driven** agent. It takes a **context (facts)** plus a
**markdown skeleton template**, fills the template (single-pass LLM call), and
exports through **pluggable renderers** — Word (`.docx`) now, PDF/Excel/TXT
later.

This is step 2 of a larger agentic workflow (Jira Agent → **Documentation
Agent** → Dremio Agent). Only the Documentation Agent is in scope here.

### Why

The existing `agents/doc_agent.py` couples the document structure across two
places: `_build_doc_prompt()` (a fixed 12-section JSON schema baked into an
f-string) and `_assemble_document()` (Python that renders those exact sections
to `.docx`). Changing the document requires editing both, and the agent is
hard-wired to a Jira VDS ticket. We decouple **template** (what sections exist),
**context** (the facts), **filler** (LLM that writes content), and **renderer**
(output format) so the agent can document anything in any format.

### Non-goals (this step)

- No changes to the Jira Agent or Dremio Agent behaviour.
- No new output formats beyond `.docx` and `.md` (seams only for PDF/Excel/TXT).
- No section-wise filler implementation (interface seam only).

## 2. Module Layout

New `documentation/` subpackage inside the existing `src/` package:

```
src/adl_automated_delivery_pipeline/
  documentation/
    __init__.py          # exports DocumentationAgent, get_renderer
    agent.py             # DocumentationAgent (orchestrator)
    context.py           # DocContext — typed, source-agnostic bag of facts
    template.py          # Template loader + section parser
    brand.py             # ASL colours + python-docx style helpers (moved from doc_agent)
    fillers/
      __init__.py        # get_filler() registry
      base.py            # Filler protocol: fill(template, context) -> markdown
      single_pass.py     # SinglePassFiller (built now)
    renderers/
      __init__.py        # get_renderer(fmt) registry
      base.py            # Renderer protocol
      markdown.py        # MarkdownRenderer (passthrough .md)
      docx.py            # DocxRenderer (markdown -> branded .docx)
    adapters/
      __init__.py
      jira.py            # jira_to_context(reqs, sql, vds_path) -> DocContext  [IMPLEMENTED]
      sprint.py          # sprint_to_context(...) -> DocContext                [STUB + TODO]
      meeting.py         # meeting_to_context(...) -> DocContext               [STUB + TODO]
      dremio.py          # dremio_to_context(...) -> DocContext                [STUB + TODO]
  templates/
    technical_implementation_document.md   # current 12-section TID, as a skeleton
  agents/doc_agent.py    # thin backward-compat shim -> documentation.DocumentationAgent
```

## 3. Core Contracts

### 3.1 DocContext (`context.py`)

A source-agnostic container of facts the document can reference. The agent
**never imports Jira** — adapters build this.

```python
@dataclass
class DocContext:
    title: str                       # document title / subject
    subtitle: str = ""               # e.g. "ADL-1729 | <summary>"
    metadata: dict[str, Any] = field(default_factory=dict)  # prepared-by, date, team, project
    data: dict[str, Any] = field(default_factory=dict)      # arbitrary facts referenced by template
```

`data` holds whatever the template needs (requirements, tables, SQL, VDS paths,
etc.). Keys used by `{{placeholders}}` and by the filler must live in `data`,
`metadata`, or be `title`/`subtitle`.

### 3.2 Template (`template.py`)

A markdown skeleton file. **Authoring rules** (the template contract):

- **Headings** (`#`, `##`, `###`, …) define structure and are preserved verbatim.
- **`<!-- instruction -->`** HTML comments are per-section guidance to the LLM
  (e.g. `<!-- list 3-5 technical/data risks with mitigation as a table -->`).
  They are stripped from the final output.
- **`{{key}}`** placeholders are resolved **deterministically** from the context
  (no LLM) — `{{title}}`, `{{ticket_id}}`, `{{data.vds_path}}`. Dotted paths
  index into `metadata`/`data`.
- A **markdown table header** present in the skeleton signals "fill this as a
  table" — the filler emits pipe-table rows under it.

`Template` parses the file into an ordered list of `Section` objects
(`heading`, `level`, `instruction`, `body_hint`). Single-pass filling uses the
whole text; the parsed sections exist so a future `SectionFiller` can iterate.

```python
@dataclass
class Section:
    heading: str
    level: int
    instruction: str = ""   # text from the <!-- ... --> comment, if any
    body_hint: str = ""     # any literal body the author left (e.g. table header)

class Template:
    raw: str
    sections: list[Section]
    @classmethod
    def load(cls, name_or_path: str | Path) -> "Template": ...
    def required_keys(self) -> set[str]: ...    # {{key}} names found
```

Templates resolve by **name** from the package `templates/` directory, or by an
explicit path.

### 3.3 Filler (`fillers/base.py`)

```python
class Filler(Protocol):
    def fill(self, template: Template, context: DocContext) -> str:
        """Return the template filled in, as valid markdown."""
```

`SinglePassFiller` (`fillers/single_pass.py`):

1. Resolve `{{key}}` placeholders from context (deterministic).
2. One **low-temperature** `make_claude()` call. System prompt instructs:
   *preserve every heading and their order exactly; replace each `<!-- ... -->`
   instruction with real content immediately following its heading; emit valid
   markdown only; render any requested tables as GitHub pipe tables; no preamble
   or code fences around the whole document.*
3. Return the filled markdown string.

Swappable via `get_filler(strategy="single_pass")`; `SectionFiller` is a later
drop-in with the same interface.

### 3.4 Renderer (`renderers/base.py`)

```python
class Renderer(Protocol):
    extension: str
    def render(self, markdown: str, out_path: Path, context: DocContext) -> Path: ...
```

Registry: `get_renderer(fmt: str) -> Renderer` over `{"md", "docx"}` now.

- **MarkdownRenderer** (`markdown.py`): write the filled markdown as-is.
- **DocxRenderer** (`docx.py`): parse markdown with **`markdown-it-py`** (pure
  Python, no binary) into a token stream, then map tokens → `python-docx` using
  `brand.py`:
  - `heading_open` level 1 → navy `Heading 1`; deeper levels → dark headings.
  - `bullet_list` / `list_item` → `List Bullet` paragraphs.
  - `table` → navy/gold styled table via the brand table helper.
  - `fence` / `code_block` → Courier New monospace paragraph.
  - `paragraph` → 10pt body.
  - Title block (title, subtitle, prepared-by/date) from `context`.

### 3.5 DocumentationAgent (`agent.py`)

```python
class DocumentationAgent:
    def generate(
        self,
        context: DocContext,
        template: str | Path = "technical_implementation_document",
        formats: Sequence[str] | None = None,   # None -> ("docx",); no mutable default
        out_dir: Path | None = None,
        filler: str = "single_pass",
    ) -> list[Path]:
        ...
```

(`formats` uses a `None` sentinel resolved to `("docx",)` inside the body —
no mutable default argument, per the repo lint rules.)

Flow: `Template.load` → `get_filler(filler).fill(template, context)` → for each
format `get_renderer(fmt).render(filled_md, out_path, context)` → return paths.
Default `out_dir` = `./Project Documentation`. Filename pattern:
`{slug(title)}_{YYYYMMDD_HHMMSS}.{ext}`.

## 4. Adapters (`adapters/`)

The seam where new content sources plug in. **Implemented now:**

```python
# adapters/jira.py
def jira_to_context(reqs: Any, sql: str = "", vds_path: str = "") -> DocContext:
    """Map a TicketRequirements dataclass (+ optional SQL/VDS) into a DocContext."""
```

It maps the existing `TicketRequirements` fields (`ticket_id`, `summary`,
`business_requirement`, `source_database`, `source_tables`, `output_fields`,
`transformations`, `filter_conditions`, `acceptance_criteria`, `extra_notes`)
plus `sql`/`vds_path` into `DocContext.title/subtitle/metadata/data`.

**Stubs (signature + `# TODO` only)** so teammates see exactly where to add a
source without reading this spec:

```python
# adapters/sprint.py
def sprint_to_context(sprint: Any) -> "DocContext":
    # TODO: map sprint summary/health data into a DocContext for sprint reports
    raise NotImplementedError

# adapters/meeting.py
def meeting_to_context(notes: Any) -> "DocContext":
    # TODO: map meeting notes / action items into a DocContext
    raise NotImplementedError

# adapters/dremio.py
def dremio_to_context(metadata: Any) -> "DocContext":
    # TODO: map Dremio VDS/catalog metadata into a DocContext for data dictionaries
    raise NotImplementedError
```

## 5. Data Flow (Jira path, end-to-end)

```
Jira ticket → _extract_requirements → TicketRequirements
  → jira_to_context → DocContext
  + Template("technical_implementation_document")
  → SinglePassFiller (Claude, low temp) → filled.md
  → DocxRenderer (brand) → ADL-1729_<ts>.docx   (+ optional .md / future .pdf)
```

## 6. Backward Compatibility

The new `documentation.DocumentationAgent` has the clean new signature
(`generate(context, ...)`). To avoid a signature clash, `agents/doc_agent.py`
keeps a **separate compatibility class** — also named `DocumentationAgent` for
import-path stability — that exposes the **legacy** signature and delegates:

```python
# agents/doc_agent.py — compat wrapper, legacy call still works unchanged
class DocumentationAgent:
    def generate(self, reqs, sql: str = "", vds_path: str = "") -> Path:
        ctx = jira_to_context(reqs, sql, vds_path)
        paths = _NewDocumentationAgent().generate(ctx, formats=["docx"])
        return paths[0]   # legacy returns a single Path
```

The legacy path uses the default TID template + `docx` renderer and writes to
`Project Documentation/{ticket_id}_{ts}.docx` (filename keyed on `ticket_id`
from `context.metadata`, preserving today's naming). The `adl-doc` console script
(`workflows/generate_doc.py`) and the supervisor pipeline are **untouched**. The
current branded TID look is preserved because the 12-section structure is moved
verbatim into `templates/technical_implementation_document.md` and the brand
helpers are reused by `DocxRenderer`.

## 7. Error Handling

- Template not found → error that **lists available template names**.
- Unknown format → `ValueError` listing registered renderer formats.
- LLM call failure → `RuntimeError` (audited), matching today's behaviour.
- Filled markdown missing an expected template heading → **warn** (structure
  drift) but still render.
- Reuse the existing `AuditLogger` to record `{ticket/title, template, formats,
  output_paths}` per generation.

## 8. Testing (offline-first, `-m unit`)

- **Template parsing:** headings, `<!-- instruction -->` extraction, `{{key}}`
  discovery and dotted-path resolution.
- **Filler:** a **stub Filler** returning fixed markdown so the render path is
  fully testable without an LLM.
- **DocxRenderer:** assert on the `python-docx` object model — headings at right
  levels, a styled table built from a markdown pipe-table, bullets, code block
  font, title block from context.
- **Renderer registry:** `get_renderer` returns correct types; unknown format
  raises.
- **jira_to_context:** field mapping from a sample `TicketRequirements`.
- One optional `-m integration` test exercises the real Claude single-pass call.

## 9. Built Now vs. Deferred (YAGNI)

**Built now:**
- `DocContext`, `Template` (+ `Section` parsing), `SinglePassFiller`,
  `MarkdownRenderer`, `DocxRenderer`, registries.
- **Adapters skeleton:** `adapters/jira.py` fully implemented, plus empty stubs
  `sprint.py`, `meeting.py`, `dremio.py` (signature + `# TODO`) so the seam
  exists and teammates know where to add new sources.
- `templates/technical_implementation_document.md` (current TID as a skeleton).
- Backward-compat shim in `agents/doc_agent.py`.
- Unit tests (offline) per §8.

**Deferred (seams only):**
- `SectionFiller` (section-by-section filling).
- PDF / Excel / TXT renderers.
- `sprint` / `meeting` / `dremio` adapter bodies.

**New dependency:** `markdown-it-py` (pure-Python). `python-docx` already
present.

## 10. Conventions (enforced)

Per the repo's `CLAUDE.md` / engineering rules: full type annotations; module
logger not `print()` in library code; specific exceptions only;
`datetime.now(timezone.utc)`; construct LLMs only via
`adl_automated_delivery_pipeline.llm`; `black` (100) / `ruff` / `pyright`.
