"""LangGraph node that writes a final session-complete audit entry."""
from __future__ import annotations

import logging

from adl_automated_delivery_pipeline.audit import AuditLogger
from adl_automated_delivery_pipeline.state import AgentState, JiraMutation

logger = logging.getLogger(__name__)


def audit_commit_node(state: AgentState) -> AgentState:
    """Write a session-complete audit entry and mark workflow as COMPLETE.

    Summarises the entire session: intent, number of mutations executed,
    approval decision, and any error. Always succeeds — audit failures are
    logged but never surface as graph errors.

    Args:
        state: Final AgentState for the session.

    Returns:
        Updated AgentState with workflow_phase set to "COMPLETE".
    """
    mutations: list[JiraMutation] = state.get("jira_mutations", [])
    executed = [m for m in mutations if m.executed]
    approved = [m for m in mutations if m.approved]
    staged = [m for m in mutations if not m.approved and not m.executed]

    output_parts = [
        f"Executed {len(executed)} mutation(s).",
        f"Approved: {len(approved)}, Staged-only: {len(staged)}.",
        f"Approval decision: {state.get('approval_decision') or 'N/A'}.",
    ]
    if state.get("error"):
        output_parts.append(f"Error: {state['error']}")

    output_summary = " ".join(output_parts)

    try:
        AuditLogger.log_action(
            trace_id=state["trace_id"],
            session_id=state["session_id"],
            agent="audit_node",
            action="session_complete",
            user_id=state["user_id"],
            role=state["role"],
            project_key=state["project_key"],
            input_summary=f"Intent: {state.get('intent', 'GENERAL')} | Agent: {state.get('current_agent', 'unknown')}",
            output_summary=output_summary,
            mutation_ids=[m.mutation_id for m in executed],
            status="SUCCESS" if not state.get("error") else "PARTIAL",
            error=state.get("error"),
        )
        logger.info(
            "audit_commit_node: session complete. session=%s executed=%d decision=%s",
            state["session_id"],
            len(executed),
            state.get("approval_decision"),
        )
    except Exception as exc:
        # Audit failures must never crash the graph
        logger.error(
            "audit_commit_node: failed to write audit entry for session=%s: %s",
            state["session_id"],
            exc,
        )

    return {**state, "workflow_phase": "COMPLETE"}
