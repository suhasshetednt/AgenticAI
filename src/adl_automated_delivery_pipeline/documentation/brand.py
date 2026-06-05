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
