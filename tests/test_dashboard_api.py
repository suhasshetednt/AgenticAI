"""Unit tests for the dashboard API: start-payload resolution and GET /."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from adl_automated_delivery_pipeline.api.app import app, _resolve_start


@pytest.mark.unit
def test_resolve_start_ticket_browse_and_default() -> None:
    assert _resolve_start({"mode": "ticket", "key": "ADL-1"}) == ("ticket", "ADL-1")
    assert _resolve_start({"mode": "browse"}) == ("browse", None)
    assert _resolve_start({}) == ("browse", None)


@pytest.mark.unit
def test_root_serves_html() -> None:
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
