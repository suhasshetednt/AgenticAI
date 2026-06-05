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


@pytest.mark.unit
def test_default_tid_template_loads_and_has_core_sections() -> None:
    from adl_automated_delivery_pipeline.documentation.template import Template

    tpl = Template.load("technical_implementation_document")
    headings = {s.heading for s in tpl.sections}
    # headings are numbered (e.g. "6. Risks & Mitigation"), so match by substring
    for expected in ("Risks & Mitigation", "Data Dictionary", "Sign-off"):
        assert any(expected in h for h in headings), f"missing section containing {expected!r}"
    assert "title" in tpl.required_keys()


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
