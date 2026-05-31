"""Phase 10a — ADL memory wrapper: non-blocking, degrades, disabled no-op (TDD)."""
import pytest

from adl_automated_delivery_pipeline.shared.memory import Memory

pytestmark = pytest.mark.unit


class FakeClient:
    def __init__(self):
        self.calls = []

    def search(self, **kw):
        self.calls.append(("search", kw))
        return type("R", (), {"injected_context": "PRIOR: always qualify tables", "items": []})()

    def store(self, **kw):
        self.calls.append(("store", kw))
        return type("R", (), {"memory_id": "m1", "status": "raw"})()

    def match_error(self, **kw):
        self.calls.append(("match", kw))
        return {"auto_apply": True, "corrected_query": "SELECT 1", "confidence": 0.9,
                "memory_id": "m9"}

    def reflect(self, ri):
        self.calls.append(("reflect", ri))
        return {"successful": True}

    def promote(self, mid, **kw):
        self.calls.append(("promote", (mid, kw)))
        return {"to": "validated"}


class Boom:
    def search(self, **k): raise RuntimeError("memory down")
    def store(self, **k): raise RuntimeError("memory down")
    def match_error(self, **k): raise RuntimeError("memory down")
    def reflect(self, ri): raise RuntimeError("memory down")
    def promote(self, mid, **k): raise RuntimeError("memory down")


def test_disabled_is_noop():
    fc = FakeClient()
    m = Memory(enabled=False, client=fc)
    assert m.recall(task="x") == ""
    assert m.remember(type="decision", content="x") is None
    assert fc.calls == []  # never touched the client


def test_recall_returns_injected_context():
    fc = FakeClient()
    m = Memory(enabled=True, client=fc)
    assert "qualify tables" in m.recall(task="how to qualify", domain="dremio")
    assert fc.calls[0][0] == "search"


def test_remember_returns_memory_id_with_idempotency_key():
    fc = FakeClient()
    m = Memory(enabled=True, client=fc)
    assert m.remember(type="decision", content="done", idempotency_key="ADL-1:outcome") == "m1"
    assert fc.calls[0][1]["idempotency_key"] == "ADL-1:outcome"


def test_match_passthrough():
    m = Memory(enabled=True, client=FakeClient())
    res = m.match(error={"error_message": "boom"})
    assert res["auto_apply"] is True and res["corrected_query"] == "SELECT 1"


def test_degrades_on_client_error():
    m = Memory(enabled=True, client=Boom())
    assert m.recall(task="x") == ""
    assert m.remember(type="decision", content="x") is None
    assert m.match(error={"error_message": "e"}) is None  # never raises


def test_missing_config_degrades_and_disables():
    def raising_factory():
        raise RuntimeError("MEMORY_API_KEY not set")

    m = Memory(enabled=True, client_factory=raising_factory)
    assert m.recall(task="x") == ""      # degrades, no raise
    assert m.enabled is False            # disabled after the misconfig (logged once)
