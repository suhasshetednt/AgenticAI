"""Shared state schema for all LangGraph agents and graphs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ── Domain models ────────────────────────────────────────────────────


class JiraMutation(BaseModel):
    """A staged (not-yet-executed) JIRA write operation."""

    mutation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    operation: str  # CREATE_TICKET | UPDATE_TICKET | TRANSITION | ASSIGN | CREATE_SPRINT | etc.
    project_key: str
    issue_key: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False
    executed: bool = False
    rollback_snapshot: Optional[dict[str, Any]] = None


class ApprovalRecord(BaseModel):
    """Human approval request record."""

    approval_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    trace_id: str = ""
    operation_type: str
    operation_label: str
    payload: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "MEDIUM"          # LOW | MEDIUM | HIGH | CRITICAL
    requires_role: str = "tech_lead"    # minimum role to approve
    requested_by: str = ""
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    status: str = "PENDING"             # PENDING | APPROVED | REJECTED | EXPIRED | ESCALATED
    rejection_reason: Optional[str] = None


class AuditEntry(BaseModel):
    """Single audit trail entry."""

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = ""
    session_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent: str = ""
    action: str = ""
    user_id: str = ""
    role: str = ""
    project_key: str = ""
    input_summary: str = ""
    output_summary: str = ""
    mutation_ids: list[str] = Field(default_factory=list)
    latency_ms: Optional[int] = None
    status: str = "SUCCESS"
    error: Optional[str] = None


# ── Master agent state ───────────────────────────────────────────────


class AgentState(TypedDict):
    # Session identity
    session_id: str
    trace_id: str
    user_id: str
    role: str           # developer | tech_lead | scrum_master | product_owner | admin
    project_key: str

    # Conversation messages (accumulated via add_messages reducer)
    messages: Annotated[list, add_messages]

    # Intent routing
    intent: str         # SPRINT_MANAGEMENT | TICKET_INTELLIGENCE | BACKLOG_GROOMING |
                        # QA_RELEASE | DEV_PRODUCTIVITY | DEPENDENCY_RISK | GENERAL
    sub_intent: Optional[str]

    # Workflow control
    current_agent: str
    workflow_phase: str  # ANALYZE | PLAN | APPROVE | EXECUTE | AUDIT
    next_action: Optional[str]
    retry_count: int

    # JIRA context (fetched live data)
    jira_context: dict[str, Any]

    # Staged write operations (queued for approval)
    jira_mutations: list[JiraMutation]

    # Approval
    pending_approvals: list[ApprovalRecord]
    approval_decision: Optional[str]  # APPROVED | REJECTED

    # Generated outputs
    agent_output: Optional[str]

    # Error handling
    error: Optional[str]
    fallback_triggered: bool


def make_initial_state(
    user_id: str,
    role: str,
    project_key: str,
    message: str,
) -> AgentState:
    """Create a fresh AgentState for a new session."""
    from langchain_core.messages import HumanMessage

    return AgentState(
        session_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
        user_id=user_id,
        role=role,
        project_key=project_key,
        messages=[HumanMessage(content=message)],
        intent="GENERAL",
        sub_intent=None,
        current_agent="supervisor",
        workflow_phase="ANALYZE",
        next_action=None,
        retry_count=0,
        jira_context={},
        jira_mutations=[],
        pending_approvals=[],
        approval_decision=None,
        agent_output=None,
        error=None,
        fallback_triggered=False,
    )
