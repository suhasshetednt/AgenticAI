"""Unit tests for the dashboard sentinel emitter."""

from __future__ import annotations

import pytest

from adl_automated_delivery_pipeline.workflows import _events as ev


@pytest.mark.unit
def test_markers_have_exact_format(capsys: pytest.CaptureFixture[str]) -> None:
    ev.stage("dremio", "start")
    ev.artifact("vds", "dremio-db.occ.aslb_business")
    ev.approve("dremio", "ADL-1729: carrier codes")
    ev.done()
    out = capsys.readouterr().out.splitlines()
    assert out == [
        "::STAGE dremio start::",
        "::ARTIFACT vds=dremio-db.occ.aslb_business::",
        "::APPROVE dremio=ADL-1729: carrier codes::",
        "::DONE::",
    ]
