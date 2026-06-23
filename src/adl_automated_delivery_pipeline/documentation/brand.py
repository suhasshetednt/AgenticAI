"""ASL Airlines brand styling helpers for python-docx documents."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

logger = logging.getLogger(__name__)

COLOR_NAVY = RGBColor(0x00, 0x38, 0x6B)
COLOR_GOLD = RGBColor(0xC8, 0x9A, 0x00)
COLOR_DARK = RGBColor(0x1A, 0x1A, 0x1A)
# OCC / Eagle Eye design tokens
_OCC_TEAL = RGBColor(0x0F, 0x47, 0x61)       # heading / subtitle colour
_TITLE_NAVY = RGBColor(0x1F, 0x38, 0x64)     # cover title colour (matches reference)
_DIAGRAM_FILL = "D9E2F3"                       # light navy box fill for flow diagrams
_HEADER_BG = "95B3D7"                          # light-blue content table header
_HEADER_BG_DARK = "595959"                     # dark-grey meta / cover table header
_BORDER_COLOR = "4F81BD"                       # OCC blue border


def _set_cell_bg(cell: Any, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _try_paragraph_style(doc: Any, *style_names: str) -> tuple[Any, str]:
    """Try style names in order; return (paragraph, resolved_style_name).

    Falls back to a plain unstyled paragraph if none of the named styles exist
    in the document. Never raises KeyError.
    """
    for style in style_names:
        try:
            para = doc.add_paragraph(style=style)
            return para, style
        except KeyError:
            logger.debug("Style %r not found in document, trying next", style)
    # Last-resort: no style at all
    para = doc.add_paragraph()
    return para, ""


def add_heading(doc: Any, text: str, level: int) -> None:
    try:
        para = doc.add_heading(text, level=level)
        para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        # OCC template defines teal (0F4761) via styles — don't override.
    except (KeyError, ValueError):
        logger.debug("Heading %d style not found, falling back to bold paragraph", level)
        para = doc.add_paragraph()
        run = para.add_run(text)
        run.bold = True
        run.font.size = Pt(max(20 - level * 2, 10))
        run.font.color.rgb = _OCC_TEAL


def add_paragraph(doc: Any, text: str, size: int = 12) -> None:
    para = doc.add_paragraph(text)
    if para.runs:
        para.runs[0].font.size = Pt(size)


def add_bullet(doc: Any, text: str) -> None:
    """Add a bullet paragraph, gracefully handling missing styles.

    Priority order:
      1. "List Bullet"      — standard python-docx built-in
      2. "List Paragraph"   — used by some ASL branded templates
      3. "Normal"           — guaranteed to exist in any .docx
      4. unstyled paragraph — absolute last resort
    """
    para, resolved = _try_paragraph_style(
        doc, "List Bullet", "List Paragraph", "Normal"
    )

    # "List Bullet" provides its own bullet glyph via numbering XML.
    # Every other style needs a manual bullet character prepended.
    bullet_text = text if resolved == "List Bullet" else f"\u2022 {text}"
    run = para.add_run(bullet_text)
    run.font.size = Pt(12)


def add_code(doc: Any, text: str) -> None:
    para = doc.add_paragraph()
    run = para.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(11)


def _apply_occ_borders(table: Any) -> None:
    """Apply OCC-style blue (4F81BD) borders to all table edges."""
    tbl = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    tblBorders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), _BORDER_COLOR)
        tblBorders.append(el)
    tblPr.append(tblBorders)


def add_table(
    doc: Any,
    headers: list[str],
    rows: list[list[str]],
    header_fill: str = _HEADER_BG,
) -> None:
    """Add an OCC-styled table with coloured header row and blue borders.

    Default header fill is light-blue (95B3D7, black text).
    Pass header_fill=_HEADER_BG_DARK for dark-grey (595959, white text) meta tables.
    """
    cols = len(headers)
    table = doc.add_table(rows=1 + len(rows), cols=cols)

    dark_fill = header_fill.upper() in ("595959", "1F3864", "00386B")

    # Header row
    for idx, label in enumerate(headers):
        cell = table.rows[0].cells[idx]
        _set_cell_bg(cell, header_fill)
        cell.text = ""
        run = cell.paragraphs[0].add_run(label)
        run.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF) if dark_fill else RGBColor(0x00, 0x00, 0x00)

    # Data rows
    for r_idx, row in enumerate(rows, start=1):
        for c_idx in range(cols):
            value = row[c_idx] if c_idx < len(row) else ""
            cell = table.rows[r_idx].cells[c_idx]
            cell.text = str(value)
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(9)

    _apply_occ_borders(table)
    doc.add_paragraph()


def set_page_margins(doc: Any) -> None:
    for section in doc.sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)


# ── Cover page (title + meta tables + TOC), matching the ASL reference design ──────

def _set_cell_box_border(cell: Any) -> None:
    """Single navy border on all four edges of one cell (for diagram boxes)."""
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "8")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "1F3864")
        borders.append(el)
    tc_pr.append(borders)


def _add_field(paragraph: Any, instruction: str, placeholder: str = "") -> None:
    """Append a Word field (e.g. TOC, PAGE) to a paragraph."""
    run = paragraph.add_run()
    r = run._r
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    r.append(begin)
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    r.append(instr)
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    r.append(sep)
    if placeholder:
        t = OxmlElement("w:t")
        t.text = placeholder
        r.append(t)
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    r.append(end)


def add_toc(doc: Any) -> None:
    """Insert a real Word Table-of-Contents field (populates on field update)."""
    para = doc.add_paragraph()
    _add_field(
        para,
        'TOC \\o "1-3" \\h \\z \\u',
        'Right-click and choose "Update Field" to build the table of contents.',
    )


def _add_meta_table(
    doc: Any, label: str, headers: list[str] | None, rows: list[list[str]], kv: bool = False
) -> None:
    """Bold label line followed by a meta table (cover Change Control / Approval / Control)."""
    lp = doc.add_paragraph()
    lr = lp.add_run(label)
    lr.bold = True
    lr.font.size = Pt(12)
    if kv:
        table = doc.add_table(rows=len(rows), cols=2)
        for ri, row in enumerate(rows):
            c0 = table.rows[ri].cells[0]
            c1 = table.rows[ri].cells[1]
            _set_cell_bg(c0, _HEADER_BG)
            c0.text = ""
            run = c0.paragraphs[0].add_run(str(row[0]))
            run.bold = True
            run.font.size = Pt(10)
            c1.text = str(row[1])
            for rn in c1.paragraphs[0].runs:
                rn.font.size = Pt(10)
        _apply_occ_borders(table)
        doc.add_paragraph()
    else:
        add_table(doc, headers or [], rows)


def add_cover(doc: Any, context: Any) -> None:
    """Render the branded cover: title, subtitle (no ticket), meta tables, TOC."""
    title = str(context.get("title") or "Technical Implementation").strip()

    p = doc.add_paragraph()
    run = p.add_run(title.upper())
    run.font.name = "Aptos Display"
    run.font.size = Pt(28)
    run.bold = True
    run.font.color.rgb = _TITLE_NAVY

    sub = doc.add_paragraph()
    sr = sub.add_run("Technical Implementation")
    sr.font.name = "Aptos Display"
    sr.font.size = Pt(14)
    sr.font.color.rgb = _OCC_TEAL

    prepared = str(context.get("metadata.prepared") or "").strip()
    team = str(context.get("metadata.team") or "").strip()
    parts = [f"Prepared: {prepared}" if prepared else "", team]
    meta_line = "  |  ".join(x for x in parts if x)
    if meta_line:
        mp = doc.add_paragraph()
        mr = mp.add_run(meta_line)
        mr.italic = True
        mr.font.size = Pt(10)
    doc.add_paragraph()

    today = datetime.now(timezone.utc).strftime("%d-%m-%Y")
    _add_meta_table(
        doc,
        "Document Change Control",
        ["Version", "Date", "Reason for issue", "Changes Made", "Issued By", "Reviewed By"],
        [["0.1", today, "Initial technical implementation", "Initial draft", "DnT-DL Team", ""]],
    )
    _add_meta_table(doc, "Document Approval", ["Name", "Role", "Date"], [["", "", ""]])
    _add_meta_table(
        doc,
        "Document Control",
        None,
        [
            ["Classification", "Internal"],
            ["Document Location", "SharePoint IT Operations"],
            ["Approval owner", ""],
            ["Release Date", ""],
            ["Next Review Date", ""],
        ],
        kv=True,
    )
    doc.add_paragraph()

    toc_label = doc.add_paragraph()
    tr = toc_label.add_run("Table of contents")
    tr.font.name = "Aptos Display"
    tr.font.size = Pt(18)
    tr.bold = True
    add_toc(doc)
    doc.add_page_break()


def set_footer(doc: Any, title: str) -> None:
    """Rewrite the footer to 'ASL Technical Implementation — <title>' + page number,
    dropping any ticket id baked into the template footer."""
    text = f"ASL Technical Implementation — {title}"
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        paras = footer.paragraphs
        para = paras[0] if paras else footer.add_paragraph()
        for r in list(para.runs):
            r._r.getparent().remove(r._r)
        run = para.add_run(text + "\t")
        run.font.size = Pt(9)
        page_lbl = para.add_run("Page ")
        page_lbl.font.size = Pt(9)
        _add_field(para, "PAGE")
        for extra in paras[1:]:
            extra._p.getparent().remove(extra._p)


# ── Flow diagrams (native python-docx: shaded boxes + arrow connectors) ───────────

def add_flow_diagram(doc: Any, boxes: list[str]) -> None:
    """Render a left-to-right flow as a borderless table of shaded box cells joined
    by arrow cells. No external dependencies — boxes are cells, arrows are glyphs."""
    boxes = [b for b in boxes if b]
    if not boxes:
        return
    ncols = 2 * len(boxes) - 1
    table = doc.add_table(rows=1, cols=ncols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    cells = table.rows[0].cells
    for ci in range(ncols):
        cell = cells[ci]
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if ci % 2 == 0:  # box
            cell.width = Inches(1.7)
            _set_cell_bg(cell, _DIAGRAM_FILL)
            _set_cell_box_border(cell)
            for li, line in enumerate(str(boxes[ci // 2]).split("\n")):
                run = para.add_run(line)
                run.bold = True
                run.font.size = Pt(10)
                run.font.color.rgb = _TITLE_NAVY
                if li < len(str(boxes[ci // 2]).split("\n")) - 1:
                    run.add_break()
        else:  # arrow connector
            cell.width = Inches(0.4)
            run = para.add_run("▶")
            run.bold = True
            run.font.size = Pt(14)
            run.font.color.rgb = _OCC_TEAL
    doc.add_paragraph()


def add_logical_diagram(doc: Any, context: Any) -> None:
    """Logical data-flow: source tables → transform → VDS → output fields."""
    sources = list(context.get("data.source_tables") or context.get("source_tables") or [])
    vds_path = str(context.get("data.vds_path") or context.get("vds_path") or "").strip()
    fields = list(context.get("data.output_fields") or context.get("output_fields") or [])

    src_box = "Source Tables\n" + ("\n".join(sources) if sources else "(source tables)")
    transform_box = "Transform\njoin · filter · dedup"
    vds_name = vds_path.split(".")[-1] if vds_path else "Virtual Dataset"
    vds_box = f"VDS\n{vds_name}"
    out_box = f"Output\n{len(fields)} fields" if fields else "Output"
    add_flow_diagram(doc, [src_box, transform_box, vds_box, out_box])


def add_technical_diagram(doc: Any, context: Any) -> None:
    """Technical architecture: source system → Dremio Cloud (VDS) → consumers."""
    source_db = str(context.get("data.source_database") or context.get("source_database") or "").strip()
    vds_path = str(context.get("data.vds_path") or context.get("vds_path") or "").strip()
    vds_name = vds_path.split(".")[-1] if vds_path else "VDS"
    src_box = f"Source System\n{source_db}" if source_db else "Source Systems\nAMOS / MM / SAP"
    dremio_box = f"Dremio Cloud (EU)\n{vds_name}"
    consumer_box = "Consumers\nQlik Sense · Engineering"
    add_flow_diagram(doc, [src_box, dremio_box, consumer_box])