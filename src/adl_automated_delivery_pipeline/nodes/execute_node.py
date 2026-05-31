"""LangGraph node that executes approved JIRA mutations against the live API."""
from __future__ import annotations
from typing import Any, cast

import logging

import requests
from jira import JIRA, JIRAError

from adl_automated_delivery_pipeline.audit import AuditLogger
from adl_automated_delivery_pipeline.config import settings
from adl_automated_delivery_pipeline.state import AgentState, JiraMutation

logger = logging.getLogger(__name__)


def _get_jira() -> Any:
    """Create a new JIRA client using configured credentials."""
    return JIRA(
        server=settings.JIRA_INSTANCE_URL,
        basic_auth=(settings.JIRA_USERNAME, settings.JIRA_API_TOKEN),
    )


def execute_mutations_node(state: AgentState) -> AgentState:
    """Execute all approved JiraMutations against the real JIRA API.

    Only runs when approval_decision == "APPROVED". Iterates over mutations
    that are approved but not yet executed, dispatches each to the appropriate
    JIRA API call, and records audit entries for each result.

    Execution failures are captured per-mutation and stored in jira_context
    under "execution_results". A single mutation failure does not abort
    subsequent mutations.

    Args:
        state: Current AgentState with approval_decision and jira_mutations.

    Returns:
        Updated AgentState with executed mutations flagged and results in
        jira_context["execution_results"]. workflow_phase set to "AUDIT".
    """
    if state.get("approval_decision") != "APPROVED":
        logger.info(
            "execute_mutations_node: approval_decision=%s — skipping execution. session=%s",
            state.get("approval_decision"),
            state["session_id"],
        )
        return {**state, "workflow_phase": "AUDIT"}

    mutations: list[JiraMutation] = state.get("jira_mutations", [])
    approved = [m for m in mutations if m.approved and not m.executed]

    if not approved:
        logger.info(
            "execute_mutations_node: no approved+unexecuted mutations. session=%s",
            state["session_id"],
        )
        return {**state, "workflow_phase": "AUDIT"}

    logger.info(
        "execute_mutations_node: executing %d mutation(s). session=%s",
        len(approved),
        state["session_id"],
    )

    jira = _get_jira()
    executed_results: list[dict] = []

    # Work on a mutable copy so we can flag executed=True
    mutations_copy = list(mutations)

    for idx, mutation in enumerate(mutations_copy):
        if not mutation.approved or mutation.executed:
            continue

        try:
            result = _execute_single(jira, mutation)
            # Pydantic models are immutable — replace with updated copy
            mutations_copy[idx] = mutation.model_copy(update={"executed": True})
            executed_results.append(
                {
                    "mutation_id": mutation.mutation_id,
                    "operation": mutation.operation,
                    "result": result,
                    "status": "SUCCESS",
                }
            )
            AuditLogger.log_action(
                trace_id=state["trace_id"],
                session_id=state["session_id"],
                agent="execute_node",
                action=mutation.operation,
                user_id=state["user_id"],
                role=state["role"],
                project_key=mutation.project_key,
                input_summary=str(mutation.payload)[:200],
                output_summary=str(result)[:200],
                mutation_ids=[mutation.mutation_id],
                status="SUCCESS",
            )
            logger.info(
                "Mutation executed: mutation_id=%s operation=%s result=%s",
                mutation.mutation_id,
                mutation.operation,
                result,
            )
        except JIRAError as exc:
            logger.error(
                "JIRA mutation failed mutation_id=%s operation=%s: %s",
                mutation.mutation_id,
                mutation.operation,
                exc,
            )
            executed_results.append(
                {
                    "mutation_id": mutation.mutation_id,
                    "operation": mutation.operation,
                    "error": str(exc),
                    "status": "FAILED",
                }
            )
            AuditLogger.log_action(
                trace_id=state["trace_id"],
                session_id=state["session_id"],
                agent="execute_node",
                action=mutation.operation,
                user_id=state["user_id"],
                role=state["role"],
                project_key=mutation.project_key,
                input_summary=str(mutation.payload)[:200],
                output_summary="",
                mutation_ids=[mutation.mutation_id],
                status="FAILED",
                error=str(exc),
            )
        except requests.RequestException as exc:
            logger.error(
                "HTTP error during mutation mutation_id=%s: %s",
                mutation.mutation_id,
                exc,
            )
            executed_results.append(
                {
                    "mutation_id": mutation.mutation_id,
                    "operation": mutation.operation,
                    "error": str(exc),
                    "status": "FAILED",
                }
            )

    updated_context = {
        **state.get("jira_context", {}),
        "execution_results": executed_results,
    }

    return {
        **state,
        "jira_mutations": mutations_copy,
        "jira_context": updated_context,
        "workflow_phase": "AUDIT",
    }


def _execute_single(jira: JIRA, mutation: JiraMutation) -> dict:
    """Dispatch a single mutation to the appropriate JIRA API call.

    Args:
        jira: An authenticated JIRA client.
        mutation: The JiraMutation to execute.

    Returns:
        A dict describing the outcome (e.g. {"issue_key": "ADL-42"}).

    Raises:
        JIRAError: On Jira API errors.
        requests.RequestException: On HTTP-level errors (for Agile REST calls).
        ValueError: If the operation type is unrecognised.
    """
    op = mutation.operation.upper()
    p = mutation.payload

    if op == "CREATE_TICKET":
        issue = jira.create_issue(fields=p.get("fields", p))
        return {"issue_key": issue.key}

    if op == "UPDATE_TICKET":
        issue = jira.issue(str(mutation.issue_key))
        issue.update(fields=p)
        return {"updated": mutation.issue_key}

    if op == "TRANSITION":
        transitions = jira.transitions(str(mutation.issue_key))
        target = p.get("target_status", "").lower()
        matched = next(
            (t for t in transitions if t["name"].lower() == target), None
        )
        if not matched:
            raise JIRAError(
                f"Transition '{target}' not found on {mutation.issue_key}. "
                f"Available: {[t['name'] for t in transitions]}"
            )
        jira.transition_issue(str(mutation.issue_key), matched["id"])
        return {"transitioned": mutation.issue_key, "to": target}

    if op == "ASSIGN":
        jira.assign_issue(str(mutation.issue_key), p.get("assignee_email"))
        return {"assigned": mutation.issue_key, "to": p.get("assignee_email")}

    if op == "ADD_COMMENT":
        comment = jira.add_comment(str(mutation.issue_key), p.get("comment_body", ""))
        return {"comment_added": mutation.issue_key, "comment_id": comment.id}

    if op == "CREATE_SPRINT":
        url = f"{settings.JIRA_INSTANCE_URL}/rest/agile/1.0/sprint"
        resp = requests.post(
            url,
            json=p,
            auth=(settings.JIRA_USERNAME, settings.JIRA_API_TOKEN),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    if op == "ADD_TO_SPRINT":
        sprint_id = p.get("sprint_id")
        url = f"{settings.JIRA_INSTANCE_URL}/rest/agile/1.0/sprint/{sprint_id}/issue"
        resp = requests.post(
            url,
            json={"issues": [str(mutation.issue_key)]},
            auth=(settings.JIRA_USERNAME, settings.JIRA_API_TOKEN),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        return {"added_to_sprint": mutation.issue_key, "sprint_id": sprint_id}

    if op == "SET_PRIORITY":
        issue = jira.issue(str(mutation.issue_key))
        issue.update(fields={"priority": {"name": p.get("priority")}})
        return {"priority_set": mutation.issue_key, "priority": p.get("priority")}

    if op == "CREATE_SUBTASK":
        fields = p.get("fields", p)
        issue = jira.create_issue(fields=fields)
        return {"subtask_key": issue.key}

    if op == "LINK_ISSUES":
        jira.create_issue_link(
            type=p.get("link_type", "blocks"),
            inwardIssue=p.get("inward_key"),
            outwardIssue=p.get("outward_key"),
        )
        return {
            "linked": f"{p.get('inward_key')} -> {p.get('outward_key')}",
            "link_type": p.get("link_type", "blocks"),
        }

    raise ValueError(
        f"Unknown mutation operation: '{op}'. "
        f"Supported: CREATE_TICKET, UPDATE_TICKET, TRANSITION, ASSIGN, "
        f"ADD_COMMENT, CREATE_SPRINT, ADD_TO_SPRINT, SET_PRIORITY, "
        f"CREATE_SUBTASK, LINK_ISSUES."
    )



