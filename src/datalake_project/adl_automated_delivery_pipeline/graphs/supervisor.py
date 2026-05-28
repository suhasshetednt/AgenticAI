"""Root supervisor graph — routes intents to specialised agent subgraphs."""
from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from adl_automated_delivery_pipeline.nodes.approval_node import approval_gate_node
from adl_automated_delivery_pipeline.nodes.audit_node import audit_commit_node
from adl_automated_delivery_pipeline.nodes.error_node import error_recovery_node
from adl_automated_delivery_pipeline.nodes.execute_node import execute_mutations_node
from adl_automated_delivery_pipeline.state import AgentState

logger = logging.getLogger(__name__)

# ── Intent keyword mapping ────────────────────────────────────────────────────
# Ordered by specificity — first match wins.
_INTENT_MAP: dict[str, list[str]] = {
    "SPRINT_MANAGEMENT": [
        "sprint",
        "velocity",
        "capacity",
        "plan sprint",
        "sprint health",
        "sprint report",
        "burndown",
    ],
    "BACKLOG_GROOMING": [
        "backlog",
        "priority",
        "groom",
        "rank",
        "prioritize",
        "prioritise",
        "technical debt",
    ],
    "QA_RELEASE": [
        "release",
        "qa ",
        "quality assurance",
        "test",
        "deploy",
        "release notes",
        "done criteria",
        "definition of done",
        "dod",
    ],
    "DEV_PRODUCTIVITY": [
        "standup",
        "workload",
        "assign",
        "productivity",
        "daily",
        "balance",
        "overloaded",
    ],
    "DEPENDENCY_RISK": [
        "risk",
        "blocker",
        "dependency",
        "escalat",
        "critical path",
        "overdue",
        "blocked",
    ],
    "TICKET_INTELLIGENCE": [
        "ticket",
        "story",
        "create",
        "bug",
        "epic",
        "subtask",
        "acceptance criteria",
        "user story",
        "defect",
        "task",
    ],
}


# ── Classifier node ───────────────────────────────────────────────────────────


def classify_intent_node(state: AgentState) -> AgentState:
    """Classify the user's intent from the last message and advance to PLAN phase.

    Uses keyword matching against _INTENT_MAP (first match wins). Defaults to
    TICKET_INTELLIGENCE for general/unrecognised requests.

    Args:
        state: Current AgentState with at least one message.

    Returns:
        Updated AgentState with intent and workflow_phase="PLAN".
    """
    last = state["messages"][-1]
    text = (last.content if hasattr(last, "content") else str(last)).lower()

    intent = "GENERAL"
    for candidate, keywords in _INTENT_MAP.items():
        if any(kw in text for kw in keywords):
            intent = candidate
            break

    logger.info(
        "classify_intent_node: session=%s intent=%s", state["session_id"], intent
    )
    return {**state, "intent": intent, "workflow_phase": "PLAN"}


# ── Routing functions ─────────────────────────────────────────────────────────


def route_by_intent(state: AgentState) -> str:
    """Map the classified intent to the corresponding agent node name."""
    mapping: dict[str, str] = {
        "SPRINT_MANAGEMENT": "sprint_agent_node",
        "TICKET_INTELLIGENCE": "ticket_agent_node",
        "BACKLOG_GROOMING": "priority_agent_node",
        "QA_RELEASE": "qa_agent_node",
        "DEV_PRODUCTIVITY": "productivity_agent_node",
        "DEPENDENCY_RISK": "risk_agent_node",
        "GENERAL": "ticket_agent_node",
    }
    target = mapping.get(state.get("intent", "GENERAL"), "ticket_agent_node")
    logger.debug(
        "route_by_intent: intent=%s -> node=%s session=%s",
        state.get("intent"),
        target,
        state["session_id"],
    )
    return target


def route_after_agent(state: AgentState) -> str:
    """Route from any agent node based on error status and pending mutations.

    Decision priority:
    1. Hard error + not already in fallback -> error_recovery.
    2. Pending approvals OR staged mutations -> approval_gate.
    3. Otherwise -> audit_commit.
    """
    if state.get("error") and not state.get("fallback_triggered"):
        return "error_recovery"
    if state.get("pending_approvals") or state.get("jira_mutations"):
        return "approval_gate"
    return "audit_commit"


def route_after_approval(state: AgentState) -> str:
    """Route after the approval gate: execute if approved, else audit."""
    if state.get("approval_decision") == "APPROVED":
        return "execute_mutations"
    return "audit_commit"


# ── Agent node wrappers ───────────────────────────────────────────────────────
# Each wrapper is a plain function (not a method) so LangGraph can register it
# as a named node. Agents are instantiated fresh per invocation to remain
# stateless (consistent with the project's per-call connection pattern).


def sprint_agent_node(state: AgentState) -> AgentState:
    """Instantiate SprintManagerAgent and run it against the current state."""
    from adl_automated_delivery_pipeline.agents.sprint_manager import SprintManagerAgent

    return SprintManagerAgent().run(state)


def ticket_agent_node(state: AgentState) -> AgentState:
    """Instantiate TicketIntelligenceAgent and run it against the current state."""
    from adl_automated_delivery_pipeline.agents.ticket_intelligence import TicketIntelligenceAgent

    return TicketIntelligenceAgent().run(state)


def priority_agent_node(state: AgentState) -> AgentState:
    """Instantiate PrioritizationAgent and run it against the current state."""
    from adl_automated_delivery_pipeline.agents.prioritization import PrioritizationAgent

    return PrioritizationAgent().run(state)


def qa_agent_node(state: AgentState) -> AgentState:
    """Instantiate QAReleaseAgent and run it against the current state."""
    from adl_automated_delivery_pipeline.agents.qa_release import QAReleaseAgent

    return QAReleaseAgent().run(state)


def productivity_agent_node(state: AgentState) -> AgentState:
    """Instantiate DeveloperProductivityAgent and run it against the current state."""
    from adl_automated_delivery_pipeline.agents.developer_productivity import DeveloperProductivityAgent

    return DeveloperProductivityAgent().run(state)


def risk_agent_node(state: AgentState) -> AgentState:
    """Instantiate DependencyRiskAgent and run it against the current state."""
    from adl_automated_delivery_pipeline.agents.dependency_risk import DependencyRiskAgent

    return DependencyRiskAgent().run(state)


# ── Graph builder ─────────────────────────────────────────────────────────────

_AGENT_NODES = [
    "sprint_agent_node",
    "ticket_agent_node",
    "priority_agent_node",
    "qa_agent_node",
    "productivity_agent_node",
    "risk_agent_node",
]


def build_supervisor_graph(checkpointer=None):
    """Build and compile the root supervisor StateGraph.

    The graph structure:
        START -> classify_intent -> [agent_node] -> approval_gate -> execute_mutations -> audit_commit -> END
                                                  |                                                     ^
                                                  -> audit_commit --------------------------------->    |
                                                  -> error_recovery -> audit_commit                     |

    Args:
        checkpointer: Optional LangGraph checkpointer. Uses MemorySaver if None.

    Returns:
        A compiled LangGraph CompiledGraph ready for invocation.
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    builder: StateGraph = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────
    builder.add_node("classify_intent", classify_intent_node)
    builder.add_node("sprint_agent_node", sprint_agent_node)
    builder.add_node("ticket_agent_node", ticket_agent_node)
    builder.add_node("priority_agent_node", priority_agent_node)
    builder.add_node("qa_agent_node", qa_agent_node)
    builder.add_node("productivity_agent_node", productivity_agent_node)
    builder.add_node("risk_agent_node", risk_agent_node)
    builder.add_node("approval_gate", approval_gate_node)
    builder.add_node("execute_mutations", execute_mutations_node)
    builder.add_node("audit_commit", audit_commit_node)
    builder.add_node("error_recovery", error_recovery_node)

    # ── Entry edge ────────────────────────────────────────────────────
    builder.add_edge(START, "classify_intent")

    # ── Classifier -> agent dispatch ──────────────────────────────────
    builder.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {node: node for node in _AGENT_NODES},
    )

    # ── Each agent -> approval / audit / error ────────────────────────
    for agent_node in _AGENT_NODES:
        builder.add_conditional_edges(
            agent_node,
            route_after_agent,
            {
                "approval_gate": "approval_gate",
                "audit_commit": "audit_commit",
                "error_recovery": "error_recovery",
            },
        )

    # ── Approval -> execute or audit ──────────────────────────────────
    builder.add_conditional_edges(
        "approval_gate",
        route_after_approval,
        {
            "execute_mutations": "execute_mutations",
            "audit_commit": "audit_commit",
        },
    )

    # ── Linear terminal edges ─────────────────────────────────────────
    builder.add_edge("execute_mutations", "audit_commit")
    builder.add_edge("error_recovery", "audit_commit")
    builder.add_edge("audit_commit", END)

    logger.info("Supervisor graph compiled with %d nodes.", len(_AGENT_NODES) + 5)
    return builder.compile(checkpointer=checkpointer)
