"""LangGraph node for graceful error recovery with bounded retries."""
from __future__ import annotations

import logging

from adl_automated_delivery_pipeline.state import AgentState

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2


def error_recovery_node(state: AgentState) -> AgentState:
    """Handle agent errors and attempt graceful recovery up to _MAX_RETRIES times.

    On each invocation the retry counter is incremented. If retries remain,
    the node clears the error flags and routes back to the ANALYZE phase so
    the supervisor graph can retry the intent classification and agent dispatch.
    Once the retry budget is exhausted the node routes to AUDIT phase so the
    session is recorded and terminates cleanly.

    Args:
        state: Current AgentState containing error and retry_count fields.

    Returns:
        Updated AgentState with either a cleared error (retry) or a terminal
        agent_output message (max retries exceeded), plus the correct
        workflow_phase.
    """
    error = state.get("error") or "Unknown error"
    retry = state.get("retry_count", 0)

    logger.error(
        "error_recovery_node: session=%s error=%r retry=%d/%d agent=%s",
        state["session_id"],
        error,
        retry,
        _MAX_RETRIES,
        state.get("current_agent", "unknown"),
    )

    if retry < _MAX_RETRIES:
        new_retry = retry + 1
        logger.info(
            "error_recovery_node: scheduling retry %d/%d for session=%s",
            new_retry,
            _MAX_RETRIES,
            state["session_id"],
        )
        return {
            **state,
            "retry_count": new_retry,
            "error": None,
            "fallback_triggered": False,
            "workflow_phase": "ANALYZE",
        }

    # Max retries exhausted — pass through to audit with a clear failure message
    logger.warning(
        "error_recovery_node: max retries (%d) exhausted for session=%s — routing to AUDIT",
        _MAX_RETRIES,
        state["session_id"],
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
