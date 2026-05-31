"""LangGraph node for graceful error recovery with bounded retries.

Consults the centralized Memory Platform for a known fix before retrying (best-effort:
no-op when MEMORY_ENABLED is false, so behaviour is unchanged by default). Trusted matches
(``auto_apply`` and a corrected_query, unless MEMORY_AUTO_APPLY is off) are surfaced to the
retry and **recorded in the audit log** with memory_id + confidence + the suggested fix.
"""
from __future__ import annotations

import logging

from adl_automated_delivery_pipeline.audit import AuditLogger
from adl_automated_delivery_pipeline.shared.memory import Memory
from adl_automated_delivery_pipeline.state import AgentState

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2


def _get_memory() -> Memory:
    """Seam for tests to inject a Memory wrapper."""
    return Memory()


def _consult_memory(state: AgentState, error: str) -> dict | None:
    """Ask the error engine for a known fix; audit any hit. Returns a suggestion dict or None."""
    mem = _get_memory()
    match = mem.match(error={"error_message": error})
    if not match:
        return None
    corrected = match.get("corrected_query")
    auto_apply = bool(match.get("auto_apply")) and mem.auto_apply and bool(corrected)
    AuditLogger.log_action(
        trace_id=state.get("trace_id", ""),
        session_id=state.get("session_id", ""),
        agent="error_recovery",
        action="memory.match",
        user_id=state.get("user_id", ""),
        role=state.get("role", ""),
        project_key=state.get("project_key", ""),
        input_summary=f"error: {error[:200]}",
        output_summary=(
            f"memory_id={match.get('memory_id')} confidence={match.get('confidence')} "
            f"auto_apply={auto_apply} fix={(corrected or match.get('resolution') or '')[:200]}"
        ),
        status="SUCCESS",
    )
    return {
        "memory_id": match.get("memory_id"),
        "confidence": match.get("confidence"),
        "auto_apply": auto_apply,
        "corrected_query": corrected,
        "resolution": match.get("resolution"),
    }


def error_recovery_node(state: AgentState) -> AgentState:
    """Handle agent errors and attempt graceful recovery up to _MAX_RETRIES times.

    Before retrying, consult the Memory Platform: a trusted fix is surfaced into the retried
    state (``memory_suggestion``) and audited so the next agent pass can apply it. The retry
    budget is unchanged — memory only informs the retry, it never adds attempts.
    """
    error = state.get("error") or "Unknown error"
    retry = state.get("retry_count", 0)

    logger.error(
        "error_recovery_node: session=%s error=%r retry=%d/%d agent=%s",
        state["session_id"], error, retry, _MAX_RETRIES, state.get("current_agent", "unknown"),
    )

    suggestion = _consult_memory(state, error)
    if suggestion:
        logger.info(
            "error_recovery_node: memory %s (memory_id=%s conf=%s) for session=%s",
            "auto-apply" if suggestion["auto_apply"] else "suggestion",
            suggestion.get("memory_id"), suggestion.get("confidence"), state["session_id"],
        )

    if retry < _MAX_RETRIES:
        new_retry = retry + 1
        logger.info(
            "error_recovery_node: scheduling retry %d/%d for session=%s",
            new_retry, _MAX_RETRIES, state["session_id"],
        )
        retried: AgentState = {
            **state,
            "retry_count": new_retry,
            "error": None,
            "fallback_triggered": False,
            "workflow_phase": "ANALYZE",
        }
        if suggestion:
            retried["memory_suggestion"] = suggestion
        return retried

    logger.warning(
        "error_recovery_node: max retries (%d) exhausted for session=%s — routing to AUDIT",
        _MAX_RETRIES, state["session_id"],
    )
    terminal_message = (
        f"Operation could not be completed after {retry} attempt(s). "
        f"Last error: {error}. "
        "Please review the audit log and retry with a more specific request."
    )
    return {
        **state,
        "workflow_phase": "AUDIT",
        "agent_output": terminal_message,
    }
