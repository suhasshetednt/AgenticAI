"""Phase 10b/10c — outcomes migration + error_recovery_node memory hook (TDD)."""
import pytest

from adl_automated_delivery_pipeline import memory as memory_mod
from adl_automated_delivery_pipeline.nodes import error_node
from adl_automated_delivery_pipeline.shared.memory import Memory

pytestmark = pytest.mark.unit


# ── outcomes migration ───────────────────────────────────────────────
class _FakeMem:
    def __init__(self, mid):
        self.mid = mid
        self.calls = []

    def remember(self, **kw):
        self.calls.append(kw)
        return self.mid


def test_outcome_routes_to_platform_no_jsonl(tmp_path):
    mgr = memory_mod.MemoryManager(memory=_FakeMem("m1"))
    mgr._outcomes_path = tmp_path / "out.jsonl"
    mgr.store_outcome("s1", {"summary": "delivered ADL-1"})
    assert mgr._memory.calls[0]["idempotency_key"] == "s1:outcome"
    assert not mgr._outcomes_path.exists()  # platform path → no local write


def test_outcome_falls_back_to_jsonl_when_platform_unavailable(tmp_path):
    mgr = memory_mod.MemoryManager(memory=_FakeMem(None))  # platform down/disabled → None
    mgr._outcomes_path = tmp_path / "out.jsonl"
    mgr.store_outcome("s2", {"summary": "delivered ADL-2"})
    assert mgr._outcomes_path.exists()                      # fallback write happened
    assert "ADL-2" in mgr._outcomes_path.read_text(encoding="utf-8")


# ── error_recovery_node memory hook ──────────────────────────────────
class _MatchClient:
    def match_error(self, **kw):
        return {"auto_apply": True, "corrected_query": "SELECT 1",
                "confidence": 0.91, "memory_id": "m9"}


def _state(error="amos table not qualified", retry=0):
    return {
        "session_id": "S", "trace_id": "T", "user_id": "u", "role": "admin",
        "project_key": "ADL", "current_agent": "dremio_agent", "retry_count": retry,
        "error": error, "workflow_phase": "EXECUTE",
    }


def test_error_node_audits_and_surfaces_trusted_fix(monkeypatch):
    monkeypatch.setattr(error_node, "_get_memory",
                        lambda: Memory(enabled=True, auto_apply=True, client=_MatchClient()))
    captured = {}
    monkeypatch.setattr(error_node.AuditLogger, "log_action",
                        lambda **kw: captured.update(kw))

    out = error_node.error_recovery_node(_state())

    # clarification #1 — the AUDIT ENTRY is asserted, not just that match ran
    assert captured["action"] == "memory.match"
    assert "memory_id=m9" in captured["output_summary"]
    assert "confidence=0.91" in captured["output_summary"]
    assert "auto_apply=True" in captured["output_summary"]
    # trusted fix surfaced into the retry
    assert out["memory_suggestion"]["corrected_query"] == "SELECT 1"
    assert out["memory_suggestion"]["auto_apply"] is True
    assert out["retry_count"] == 1


def test_kill_switch_downgrades_to_suggestion(monkeypatch):
    monkeypatch.setattr(error_node, "_get_memory",
                        lambda: Memory(enabled=True, auto_apply=False, client=_MatchClient()))
    monkeypatch.setattr(error_node.AuditLogger, "log_action", lambda **kw: None)
    out = error_node.error_recovery_node(_state())
    assert out["memory_suggestion"]["auto_apply"] is False  # MEMORY_AUTO_APPLY=false


def test_disabled_memory_leaves_node_behaviour_unchanged(monkeypatch):
    monkeypatch.setattr(error_node, "_get_memory", lambda: Memory(enabled=False))
    calls = []
    monkeypatch.setattr(error_node.AuditLogger, "log_action", lambda **kw: calls.append(kw))
    out = error_node.error_recovery_node(_state())
    assert calls == []                       # no audit when disabled
    assert "memory_suggestion" not in out    # behaviour identical to pre-integration
    assert out["error"] is None and out["retry_count"] == 1
