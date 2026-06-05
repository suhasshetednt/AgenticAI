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
