"""LangGraph node for human-in-the-loop approval of staged JIRA mutations."""
from __future__ import annotations

import logging
import sys

from langgraph.types import interrupt

from adl_automated_delivery_pipeline.approval import ApprovalStore
from adl_automated_delivery_pipeline.state import AgentState, ApprovalRecord, JiraMutation

logger = logging.getLogger(__name__)


def approval_gate_node(state: AgentState) -> AgentState:
    """Suspend the graph for human approval of all pending staged mutations.

    Behaviour differs by execution context:
    - Interactive TTY (CLI): calls cli_approval_gate() synchronously for each
      pending record and continues execution immediately.
    - Non-interactive (API / test): persists each record to ApprovalStore and
      calls interrupt() with approval metadata, yielding control to an external
      approval service. Execution resumes when the graph is resumed with a
      human-provided decision dict.

    The node clears pending_approvals on exit and sets workflow_phase to
    "EXECUTE" (all approved) or "AUDIT" (any rejected).

    Args:
        state: Current AgentState with pending_approvals and jira_mutations.

    Returns:
        Updated AgentState with approval_decision, updated jira_mutations,
        empty pending_approvals, and the next workflow_phase.
    """
    pending: list[ApprovalRecord] = state.get("pending_approvals", [])

    if not pending:
        logger.info(
            "approval_gate_node: no pending approvals — skipping to EXECUTE. session=%s",
            state["session_id"],
        )
        return {**state, "workflow_phase": "EXECUTE"}

    mutations: list[JiraMutation] = list(state.get("jira_mutations", []))
    updated_mutations = mutations
    updated_approvals: list[ApprovalRecord] = []
    decision = "APPROVED"

    for record in pending:
        logger.info(
            "approval_gate_node: processing approval_id=%s operation=%s risk=%s",
            record.approval_id,
            record.operation_type,
            record.risk_level,
        )

        # Persist to file store regardless of mode so the record is durable
        try:
            ApprovalStore.enqueue(record)
        except Exception as exc:
            logger.error(
                "Failed to enqueue approval record %s: %s", record.approval_id, exc
            )

        if sys.stdout.isatty():
            # ── Interactive CLI mode ──────────────────────────────────
            from adl_automated_delivery_pipeline.approval import cli_approval_gate

            try:
                approved = cli_approval_gate(record)
            except Exception as exc:
                logger.error(
                    "cli_approval_gate error for approval_id=%s: %s",
                    record.approval_id,
                    exc,
                )
                approved = False

            if approved:
                try:
                    updated_mutations = ApprovalStore.mark_mutations_approved(
                        updated_mutations, record.approval_id
                    )
                except Exception as exc:
                    logger.error(
                        "mark_mutations_approved failed for approval_id=%s: %s",
                        record.approval_id,
                        exc,
                    )
            else:
                decision = "REJECTED"

        else:
            # ── API / non-interactive mode ────────────────────────────
            # Yield control to an external approval service.  The graph will be
            # resumed by calling graph.invoke() again with the human decision.
            human_input: dict = interrupt(
                {
                    "approval_id": record.approval_id,
                    "operation": record.operation_type,
                    "label": record.operation_label,
                    "risk_level": record.risk_level,
                    "requested_by": record.requested_by,
                    "session_id": state["session_id"],
                    "trace_id": state["trace_id"],
                }
            )

            if isinstance(human_input, dict) and human_input.get("decision") == "APPROVED":
                approver = human_input.get("approver", "api_user")
                try:
                    ApprovalStore.approve(record.approval_id, approver)
                    updated_mutations = ApprovalStore.mark_mutations_approved(
                        updated_mutations, record.approval_id
                    )
                    logger.info(
                        "API approval GRANTED: approval_id=%s approver=%s",
                        record.approval_id,
                        approver,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to persist API approval for approval_id=%s: %s",
                        record.approval_id,
                        exc,
                    )
                    decision = "REJECTED"
            else:
                rejection_reason = (
                    human_input.get("reason", "Rejected via API.")
                    if isinstance(human_input, dict)
                    else "Rejected via API."
                )
                rejector = (
                    human_input.get("approver", "api_user")
                    if isinstance(human_input, dict)
                    else "api_user"
                )
                try:
                    ApprovalStore.reject(
                        record.approval_id, rejector, rejection_reason
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to persist API rejection for approval_id=%s: %s",
                        record.approval_id,
                        exc,
                    )
                decision = "REJECTED"
                logger.info(
                    "API approval REJECTED: approval_id=%s", record.approval_id
                )

        updated_approvals.append(record)

    next_phase = "EXECUTE" if decision == "APPROVED" else "AUDIT"
    logger.info(
        "approval_gate_node complete: decision=%s phase=%s session=%s",
        decision,
        next_phase,
        state["session_id"],
    )

    return {
        **state,
        "approval_decision": decision,
        "jira_mutations": updated_mutations,
        "pending_approvals": [],
        "workflow_phase": next_phase,
    }
