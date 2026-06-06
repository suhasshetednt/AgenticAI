"""Unit tests for _doc_phase return value and run_ticket orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

import adl_automated_delivery_pipeline.workflows.adl_automated_delivery_pipeline as wf


@pytest.mark.unit
def test_doc_phase_returns_saved_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeAgent:
        def generate(self, reqs, *a, **k):  # noqa: ANN001
            return Path("X:/Project Documentation/ADL-1.docx")

    monkeypatch.setattr(wf, "DocumentationAgent", _FakeAgent)
    reqs = wf.TicketRequirements(
        ticket_id="ADL-1", summary="s", business_requirement="b",
        source_database="occ", source_tables=[], output_fields=[],
        transformations=[], filter_conditions=[], acceptance_criteria=[],
    )
    assert wf._doc_phase(reqs) == Path("X:/Project Documentation/ADL-1.docx")
