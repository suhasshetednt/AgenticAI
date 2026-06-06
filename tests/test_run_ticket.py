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


@pytest.mark.unit
def test_run_ticket_happy_path_emits_markers_in_order(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reqs = wf.TicketRequirements(
        ticket_id="ADL-1", summary="s", business_requirement="b",
        source_database="occ", source_tables=[], output_fields=[],
        transformations=[], filter_conditions=[], acceptance_criteria=[],
    )
    monkeypatch.setattr(wf, "_fetch_ticket", lambda key: {"status": "SUCCESS", "id": key})
    monkeypatch.setattr(wf, "_extract_requirements", lambda ticket: reqs)
    monkeypatch.setattr(wf, "_display_requirements", lambda r: None)
    monkeypatch.setattr(wf, "_doc_phase", lambda r: Path("Project Documentation/ADL-1.docx"))
    monkeypatch.setattr(wf, "_dremio_phase", lambda r: "dremio-db.occ.aslb_business")
    monkeypatch.setattr(wf, "_qlik_phase", lambda r, v: None)
    answers = iter(["y", "y"])  # approve dremio, approve qlik
    monkeypatch.setattr(wf, "_inp", lambda *a, **k: next(answers))

    wf.run_ticket("ADL-1")

    markers = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert markers == [
        "::STAGE jira start::", "::STAGE jira done::",
        "::STAGE reqs start::", "::STAGE reqs done::",
        "::STAGE doc start::",
        "::ARTIFACT docx=Project Documentation/ADL-1.docx::",
        "::STAGE doc done::",
        "::APPROVE dremio=ADL-1: s::",
        "::STAGE dremio start::",
        "::ARTIFACT vds=dremio-db.occ.aslb_business::",
        "::STAGE dremio done::",
        "::APPROVE qlik=dremio-db.occ.aslb_business::",
        "::STAGE qlik start::", "::STAGE qlik done::",
        "::DONE::",
    ]


@pytest.mark.unit
def test_run_ticket_reject_dremio_stops(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reqs = wf.TicketRequirements(
        ticket_id="ADL-1", summary="s", business_requirement="b",
        source_database="occ", source_tables=[], output_fields=[],
        transformations=[], filter_conditions=[], acceptance_criteria=[],
    )
    monkeypatch.setattr(wf, "_fetch_ticket", lambda key: {"status": "SUCCESS", "id": key})
    monkeypatch.setattr(wf, "_extract_requirements", lambda ticket: reqs)
    monkeypatch.setattr(wf, "_display_requirements", lambda r: None)
    monkeypatch.setattr(wf, "_doc_phase", lambda r: Path("d.docx"))
    monkeypatch.setattr(wf, "_dremio_phase", lambda r: (_ for _ in ()).throw(AssertionError("dremio ran")))
    monkeypatch.setattr(wf, "_inp", lambda *a, **k: "n")  # reject dremio

    wf.run_ticket("ADL-1")

    markers = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert "::STAGE dremio start::" not in markers
    assert markers[-1] == "::DONE::"


@pytest.mark.unit
def test_run_ticket_jira_fail_stops(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(wf, "_fetch_ticket", lambda key: {"status": "FAILED", "error": "nope"})
    wf.run_ticket("ADL-X")
    markers = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert markers == ["::STAGE jira start::", "::STAGE jira fail::", "::DONE::"]
