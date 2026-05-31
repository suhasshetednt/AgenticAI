"""Approval Governance Agent — manages human approval records for staged mutations."""
from __future__ import annotations

import logging

from adl_automated_delivery_pipeline.approval import ApprovalStore, cli_approval_gate
from adl_automated_delivery_pipeline.rbac import RBACEnforcer
from adl_automated_delivery_pipeline.state import AgentState, ApprovalRecord, JiraMutation

logger = logging.getLogger(__name__)


class ApprovalGovernanceAgent:
    """Orchestrates human-in-the-loop approval for all staged JIRA mutations.

    This agent does NOT use ReAct or an LLM. It processes pending approval
    records from state, enforces RBAC checks, presents each record to the
    operator via the CLI gate (or API interrupt), and updates approval status
    and mutation flags accordingly.

    It is intentionally kept separate from BaseJiraAgent because it has no
    LLM dependency and its logic is deterministic.
    """

    name = "approval_governance"

    def run(self, state: AgentState) -> AgentState:
        """Process all pending approvals in state and return an updated state.

        For each PENDING ApprovalRecord:
        1. Verify RBAC — the requesting user must meet minimum role requirements.
        2. Enqueue to file store.
        3. Present to operator (CLI or API mode).
        4. Persist approval/rejection and mark mutations accordingly.

        Args:
            state: Current AgentState containing pending_approvals and jira_mutations.

        Returns:
            Updated AgentState with approval_decision, updated jira_mutations,
            and cleared pending_approvals.
        """
        pending: list[ApprovalRecord] = state.get("pending_approvals", [])

        if not pending:
            logger.info(
                "ApprovalGovernanceAgent: no pending approvals for session %s",
                state["session_id"],
            )
            return {**state, "workflow_phase": "EXECUTE"}

        mutations: list[JiraMutation] = list(state.get("jira_mutations", []))
        updated_mutations = mutations
        processed_approvals: list[ApprovalRecord] = []
        overall_decision = "APPROVED"

        for record in pending:
            logger.info(
                "Processing approval: approval_id=%s operation=%s risk=%s",
                record.approval_id,
                record.operation_type,
                record.risk_level,
            )

            # RBAC check — verify the requesting user has sufficient role to
            # even initiate this operation. Approval role enforcement happens
            # at the gate itself (cli_approval_gate / interrupt).
            if state.get("role") and not RBACEnforcer.can_initiate(
                state["role"], record.operation_type
            ):
                logger.warning(
                    "RBAC: role=%s may not initiate operation=%s — auto-rejecting approval_id=%s",
                    state["role"],
                    record.operation_type,
                    record.approval_id,
                )
                try:
                    ApprovalStore.enqueue(record)
                    ApprovalStore.reject(
                        record.approval_id,
                        rejected_by="approval_governance",
                        reason=(
                            f"Role '{state['role']}' is not permitted to initiate "
                            f"operation '{record.operation_type}'."
                        ),
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to persist RBAC auto-rejection for approval_id=%s: %s",
                        record.approval_id,
                        exc,
                    )
                overall_decision = "REJECTED"
                processed_approvals.append(record)
                continue

            # Enqueue to persistent store before presenting to operator
            try:
                ApprovalStore.enqueue(record)
            except Exception as exc:
                logger.error(
                    "Failed to enqueue approval_id=%s: %s", record.approval_id, exc
                )
                # Treat enqueue failure as a rejection to be safe
                overall_decision = "REJECTED"
                processed_approvals.append(record)
                continue

            # Present to operator and handle decision
            try:
                approved = cli_approval_gate(record)
            except Exception as exc:
                logger.error(
                    "cli_approval_gate raised unexpectedly for approval_id=%s: %s",
                    record.approval_id,
                    exc,
                )
                approved = False

            if approved:
                try:
                    updated_mutations = ApprovalStore.mark_mutations_approved(
                        updated_mutations, record.approval_id
                    )
                    logger.info(
                        "Approval GRANTED: approval_id=%s", record.approval_id
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to mark mutations approved for approval_id=%s: %s",
                        record.approval_id,
                        exc,
                    )
            else:
                overall_decision = "REJECTED"
                logger.info("Approval REJECTED: approval_id=%s", record.approval_id)

            processed_approvals.append(record)

        next_phase = "EXECUTE" if overall_decision == "APPROVED" else "AUDIT"
        logger.info(
            "ApprovalGovernanceAgent complete: decision=%s phase=%s session=%s",
            overall_decision,
            next_phase,
            state["session_id"],
        )

        return {
            **state,
            "approval_decision": overall_decision,
            "jira_mutations": updated_mutations,
            "pending_approvals": [],
            "workflow_phase": next_phase,
            "current_agent": self.name,
        }
