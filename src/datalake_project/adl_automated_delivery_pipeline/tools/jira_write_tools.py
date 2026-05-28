"""LangChain @tool functions for WRITE operations against Jira.

IMPORTANT: These tools NEVER call the Jira API directly.
They stage a JiraMutation + ApprovalRecord for human approval, then return
both as a serialised dict.  The LangGraph execute-node is responsible for
actually applying approved mutations.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from langchain_core.tools import tool

from adl_automated_delivery_pipeline.state import ApprovalRecord, JiraMutation

logger = logging.getLogger(__name__)

# ── Risk classification helpers ───────────────────────────────────────

_OPERATION_RISK: dict[str, str] = {
    "CREATE_TICKET": "MEDIUM",
    "UPDATE_TICKET": "MEDIUM",
    "TRANSITION": "MEDIUM",
    "ASSIGN": "LOW",
    "ADD_COMMENT": "LOW",
    "CREATE_SPRINT": "HIGH",
    "ADD_TO_SPRINT": "MEDIUM",
    "SET_PRIORITY": "LOW",
    "CREATE_SUBTASK": "MEDIUM",
    "LINK_ISSUES": "LOW",
}

_OPERATION_REQUIRES_ROLE: dict[str, str] = {
    "CREATE_TICKET": "tech_lead",
    "UPDATE_TICKET": "tech_lead",
    "TRANSITION": "tech_lead",
    "ASSIGN": "tech_lead",
    "ADD_COMMENT": "developer",
    "CREATE_SPRINT": "scrum_master",
    "ADD_TO_SPRINT": "scrum_master",
    "SET_PRIORITY": "tech_lead",
    "CREATE_SUBTASK": "tech_lead",
    "LINK_ISSUES": "tech_lead",
}


def _make_mutation(
    operation: str,
    project_key: str,
    payload: dict,
    issue_key: Optional[str] = None,
) -> JiraMutation:
    """Construct a JiraMutation with a fresh mutation_id."""
    return JiraMutation(
        operation=operation,
        project_key=project_key,
        issue_key=issue_key,
        payload=payload,
    )


def _make_approval(
    mutation: JiraMutation,
    operation_type: str,
    operation_label: str,
    session_id: str = "",
    trace_id: str = "",
    requested_by: str = "",
) -> ApprovalRecord:
    """Construct an ApprovalRecord linked to a mutation."""
    return ApprovalRecord(
        session_id=session_id,
        trace_id=trace_id,
        operation_type=operation_type,
        operation_label=operation_label,
        payload={**mutation.payload, "mutation_ids": [mutation.mutation_id]},
        risk_level=_OPERATION_RISK.get(operation_type, "MEDIUM"),
        requires_role=_OPERATION_REQUIRES_ROLE.get(operation_type, "tech_lead"),
        requested_by=requested_by,
    )


def _staged_response(mutation: JiraMutation, approval: ApprovalRecord) -> dict:
    """Build the standard STAGED response dict."""
    return {
        "status": "STAGED",
        "approval_needed": True,
        "mutation": mutation.model_dump(mode="json"),
        "approval": approval.model_dump(mode="json"),
    }


# ── Write tools ───────────────────────────────────────────────────────


@tool
def stage_create_ticket(
    project_key: str,
    summary: str,
    description: str,
    issue_type: str = "Story",
    priority: str = "Medium",
    story_points: Optional[int] = None,
    labels: Optional[list[str]] = None,
    epic_key: Optional[str] = None,
) -> dict:
    """Stage a new Jira ticket creation for approval.

    This tool does NOT write to Jira.  It creates a staged mutation that must
    be approved by a Tech Lead or higher before execution.

    Args:
        project_key: Jira project key, e.g. "ADL".
        summary: One-line summary for the new ticket.
        description: Detailed description / acceptance criteria.
        issue_type: Issue type name, e.g. "Story", "Bug", "Task" (default "Story").
        priority: Priority name — "Highest", "High", "Medium", "Low", "Lowest".
        story_points: Optional story point estimate (integer).
        labels: Optional list of label strings.
        epic_key: Optional parent epic key, e.g. "ADL-50".

    Returns:
        Dict with status="STAGED", mutation details, and approval record.
    """
    if not summary.strip():
        return {"status": "FAILED", "error": "summary must not be empty."}
    if not project_key.strip():
        return {"status": "FAILED", "error": "project_key must not be empty."}

    payload: dict = {
        "project_key": project_key,
        "summary": summary.strip(),
        "description": description,
        "issue_type": issue_type,
        "priority": priority,
    }
    if story_points is not None:
        payload["story_points"] = story_points
    if labels:
        payload["labels"] = labels
    if epic_key:
        payload["epic_key"] = epic_key

    mutation = _make_mutation("CREATE_TICKET", project_key, payload)
    approval = _make_approval(
        mutation,
        operation_type="TICKET_CREATE",
        operation_label=f"Create {issue_type}: {summary[:80]}",
    )
    logger.info(
        "Staged CREATE_TICKET mutation_id=%s project=%s summary='%s'",
        mutation.mutation_id, project_key, summary[:60],
    )
    return _staged_response(mutation, approval)


@tool
def stage_update_ticket(
    issue_key: str,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    story_points: Optional[int] = None,
    labels: Optional[list[str]] = None,
) -> dict:
    """Stage an update to an existing Jira ticket for approval.

    Only fields that are explicitly provided (non-None) will be updated.
    Requires Tech Lead approval.

    Args:
        issue_key: Jira issue key, e.g. "ADL-123".
        summary: New summary text (optional).
        description: New description text (optional).
        priority: New priority name (optional).
        story_points: New story point estimate (optional).
        labels: New complete label list — replaces existing labels (optional).

    Returns:
        Dict with status="STAGED", mutation details, and approval record.
    """
    if not issue_key.strip():
        return {"status": "FAILED", "error": "issue_key must not be empty."}

    # Derive project_key from issue_key (everything before the last hyphen)
    parts = issue_key.rsplit("-", 1)
    project_key = parts[0] if len(parts) == 2 else issue_key

    payload: dict = {"issue_key": issue_key}
    if summary is not None:
        payload["summary"] = summary.strip()
    if description is not None:
        payload["description"] = description
    if priority is not None:
        payload["priority"] = priority
    if story_points is not None:
        payload["story_points"] = story_points
    if labels is not None:
        payload["labels"] = labels

    if len(payload) == 1:
        return {
            "status": "FAILED",
            "error": "At least one field to update must be provided.",
        }

    mutation = _make_mutation("UPDATE_TICKET", project_key, payload, issue_key=issue_key)
    changed_fields = [k for k in payload if k != "issue_key"]
    approval = _make_approval(
        mutation,
        operation_type="TICKET_UPDATE",
        operation_label=f"Update {issue_key}: {', '.join(changed_fields)}",
    )
    logger.info(
        "Staged UPDATE_TICKET mutation_id=%s issue=%s fields=%s",
        mutation.mutation_id, issue_key, changed_fields,
    )
    return _staged_response(mutation, approval)


@tool
def stage_transition_ticket(issue_key: str, target_status: str) -> dict:
    """Stage a status transition for a Jira ticket for approval.

    The execute node will look up the transition ID from the target_status name
    at execution time.  Requires Tech Lead approval.

    Args:
        issue_key: Jira issue key, e.g. "ADL-123".
        target_status: Target status name, e.g. "In Progress", "Done", "Blocked".

    Returns:
        Dict with status="STAGED", mutation details, and approval record.
    """
    if not issue_key.strip():
        return {"status": "FAILED", "error": "issue_key must not be empty."}
    if not target_status.strip():
        return {"status": "FAILED", "error": "target_status must not be empty."}

    parts = issue_key.rsplit("-", 1)
    project_key = parts[0] if len(parts) == 2 else issue_key

    payload = {
        "issue_key": issue_key,
        "target_status": target_status.strip(),
    }
    mutation = _make_mutation("TRANSITION", project_key, payload, issue_key=issue_key)
    approval = _make_approval(
        mutation,
        operation_type="TRANSITION",
        operation_label=f"Transition {issue_key} -> {target_status}",
    )
    logger.info(
        "Staged TRANSITION mutation_id=%s issue=%s target='%s'",
        mutation.mutation_id, issue_key, target_status,
    )
    return _staged_response(mutation, approval)


@tool
def stage_assign_ticket(issue_key: str, assignee_email: str) -> dict:
    """Stage an assignee change on a Jira ticket for approval.

    Requires Tech Lead approval.

    Args:
        issue_key: Jira issue key, e.g. "ADL-123".
        assignee_email: Email address of the new assignee.

    Returns:
        Dict with status="STAGED", mutation details, and approval record.
    """
    if not issue_key.strip():
        return {"status": "FAILED", "error": "issue_key must not be empty."}
    if not assignee_email.strip():
        return {"status": "FAILED", "error": "assignee_email must not be empty."}

    parts = issue_key.rsplit("-", 1)
    project_key = parts[0] if len(parts) == 2 else issue_key

    payload = {
        "issue_key": issue_key,
        "assignee_email": assignee_email.strip().lower(),
    }
    mutation = _make_mutation("ASSIGN", project_key, payload, issue_key=issue_key)
    approval = _make_approval(
        mutation,
        operation_type="ASSIGNMENT_CHANGE",
        operation_label=f"Assign {issue_key} to {assignee_email}",
    )
    logger.info(
        "Staged ASSIGN mutation_id=%s issue=%s assignee=%s",
        mutation.mutation_id, issue_key, assignee_email,
    )
    return _staged_response(mutation, approval)


@tool
def stage_add_comment(issue_key: str, comment_body: str) -> dict:
    """Stage adding a comment to a Jira issue for approval.

    Comments are LOW risk and require only Developer role to initiate.
    Approval is still recorded for audit purposes.

    Args:
        issue_key: Jira issue key, e.g. "ADL-123".
        comment_body: The text of the comment to add (supports Jira markdown).

    Returns:
        Dict with status="STAGED", mutation details, and approval record.
    """
    if not issue_key.strip():
        return {"status": "FAILED", "error": "issue_key must not be empty."}
    if not comment_body.strip():
        return {"status": "FAILED", "error": "comment_body must not be empty."}

    parts = issue_key.rsplit("-", 1)
    project_key = parts[0] if len(parts) == 2 else issue_key

    payload = {
        "issue_key": issue_key,
        "comment_body": comment_body.strip(),
    }
    mutation = _make_mutation("ADD_COMMENT", project_key, payload, issue_key=issue_key)
    # Comments are low-risk — override the default approval record risk level
    approval = ApprovalRecord(
        operation_type="TICKET_UPDATE",
        operation_label=f"Add comment to {issue_key}",
        payload={**payload, "mutation_ids": [mutation.mutation_id]},
        risk_level="LOW",
        requires_role="developer",
    )
    logger.info(
        "Staged ADD_COMMENT mutation_id=%s issue=%s",
        mutation.mutation_id, issue_key,
    )
    return _staged_response(mutation, approval)


@tool
def stage_create_sprint(
    project_key: str,
    sprint_name: str,
    start_date: str,
    end_date: str,
) -> dict:
    """Stage the creation of a new sprint for approval.

    Sprint creation is HIGH risk and requires Scrum Master approval.

    Args:
        project_key: Jira project key, e.g. "ADL".
        sprint_name: Name for the new sprint, e.g. "ADL Sprint 12".
        start_date: Sprint start date in ISO format, e.g. "2025-06-01".
        end_date: Sprint end date in ISO format, e.g. "2025-06-14".

    Returns:
        Dict with status="STAGED", mutation details, and approval record.
    """
    if not project_key.strip():
        return {"status": "FAILED", "error": "project_key must not be empty."}
    if not sprint_name.strip():
        return {"status": "FAILED", "error": "sprint_name must not be empty."}
    if not start_date.strip() or not end_date.strip():
        return {"status": "FAILED", "error": "start_date and end_date must not be empty."}

    payload = {
        "project_key": project_key,
        "sprint_name": sprint_name.strip(),
        "start_date": start_date.strip(),
        "end_date": end_date.strip(),
    }
    mutation = _make_mutation("CREATE_SPRINT", project_key, payload)
    # CREATE_SPRINT is HIGH risk
    approval = ApprovalRecord(
        operation_type="SPRINT_CREATE",
        operation_label=f"Create sprint '{sprint_name}' ({start_date} – {end_date})",
        payload={**payload, "mutation_ids": [mutation.mutation_id]},
        risk_level="HIGH",
        requires_role="scrum_master",
    )
    logger.info(
        "Staged CREATE_SPRINT mutation_id=%s project=%s sprint='%s'",
        mutation.mutation_id, project_key, sprint_name,
    )
    return _staged_response(mutation, approval)


@tool
def stage_add_to_sprint(issue_key: str, sprint_name: str) -> dict:
    """Stage moving an issue into a named sprint for approval.

    Requires Scrum Master approval.

    Args:
        issue_key: Jira issue key to add to the sprint, e.g. "ADL-200".
        sprint_name: Exact name of the target sprint, e.g. "ADL Sprint 12".

    Returns:
        Dict with status="STAGED", mutation details, and approval record.
    """
    if not issue_key.strip():
        return {"status": "FAILED", "error": "issue_key must not be empty."}
    if not sprint_name.strip():
        return {"status": "FAILED", "error": "sprint_name must not be empty."}

    parts = issue_key.rsplit("-", 1)
    project_key = parts[0] if len(parts) == 2 else issue_key

    payload = {
        "issue_key": issue_key,
        "sprint_name": sprint_name.strip(),
    }
    mutation = _make_mutation("ADD_TO_SPRINT", project_key, payload, issue_key=issue_key)
    approval = _make_approval(
        mutation,
        operation_type="ADD_TO_SPRINT",
        operation_label=f"Add {issue_key} to sprint '{sprint_name}'",
    )
    logger.info(
        "Staged ADD_TO_SPRINT mutation_id=%s issue=%s sprint='%s'",
        mutation.mutation_id, issue_key, sprint_name,
    )
    return _staged_response(mutation, approval)


@tool
def stage_set_priority(issue_key: str, priority: str) -> dict:
    """Stage a priority change on a Jira ticket for approval.

    Requires Tech Lead approval.

    Args:
        issue_key: Jira issue key, e.g. "ADL-123".
        priority: New priority — "Highest", "High", "Medium", "Low", "Lowest".

    Returns:
        Dict with status="STAGED", mutation details, and approval record.
    """
    valid_priorities = {"Highest", "High", "Medium", "Low", "Lowest"}
    if not issue_key.strip():
        return {"status": "FAILED", "error": "issue_key must not be empty."}
    if priority not in valid_priorities:
        return {
            "status": "FAILED",
            "error": f"Invalid priority '{priority}'. Valid values: {sorted(valid_priorities)}",
        }

    parts = issue_key.rsplit("-", 1)
    project_key = parts[0] if len(parts) == 2 else issue_key

    payload = {"issue_key": issue_key, "priority": priority}
    mutation = _make_mutation("SET_PRIORITY", project_key, payload, issue_key=issue_key)
    approval = _make_approval(
        mutation,
        operation_type="TICKET_UPDATE",
        operation_label=f"Set priority of {issue_key} to {priority}",
    )
    logger.info(
        "Staged SET_PRIORITY mutation_id=%s issue=%s priority=%s",
        mutation.mutation_id, issue_key, priority,
    )
    return _staged_response(mutation, approval)


@tool
def stage_create_subtask(
    parent_issue_key: str,
    summary: str,
    description: str = "",
) -> dict:
    """Stage creation of a sub-task under an existing Jira issue for approval.

    Requires Tech Lead approval.

    Args:
        parent_issue_key: Key of the parent issue, e.g. "ADL-123".
        summary: Sub-task summary line.
        description: Optional description for the sub-task.

    Returns:
        Dict with status="STAGED", mutation details, and approval record.
    """
    if not parent_issue_key.strip():
        return {"status": "FAILED", "error": "parent_issue_key must not be empty."}
    if not summary.strip():
        return {"status": "FAILED", "error": "summary must not be empty."}

    parts = parent_issue_key.rsplit("-", 1)
    project_key = parts[0] if len(parts) == 2 else parent_issue_key

    payload = {
        "parent_issue_key": parent_issue_key,
        "project_key": project_key,
        "summary": summary.strip(),
        "description": description,
        "issue_type": "Sub-task",
    }
    mutation = _make_mutation(
        "CREATE_SUBTASK", project_key, payload, issue_key=parent_issue_key
    )
    approval = _make_approval(
        mutation,
        operation_type="TICKET_CREATE",
        operation_label=f"Create sub-task under {parent_issue_key}: {summary[:60]}",
    )
    logger.info(
        "Staged CREATE_SUBTASK mutation_id=%s parent=%s summary='%s'",
        mutation.mutation_id, parent_issue_key, summary[:50],
    )
    return _staged_response(mutation, approval)


@tool
def stage_link_issues(
    inward_key: str,
    outward_key: str,
    link_type: str = "blocks",
) -> dict:
    """Stage linking two Jira issues with a given relationship type for approval.

    Requires Tech Lead approval.

    Args:
        inward_key: The key of the issue that is the inward end of the link (e.g. "ADL-10").
        outward_key: The key of the issue that is the outward end (e.g. "ADL-20").
        link_type: Link type name, e.g. "blocks", "is blocked by", "relates to",
                   "duplicates" (default "blocks").

    Returns:
        Dict with status="STAGED", mutation details, and approval record.
    """
    if not inward_key.strip():
        return {"status": "FAILED", "error": "inward_key must not be empty."}
    if not outward_key.strip():
        return {"status": "FAILED", "error": "outward_key must not be empty."}
    if not link_type.strip():
        return {"status": "FAILED", "error": "link_type must not be empty."}

    parts = inward_key.rsplit("-", 1)
    project_key = parts[0] if len(parts) == 2 else inward_key

    payload = {
        "inward_key": inward_key.strip(),
        "outward_key": outward_key.strip(),
        "link_type": link_type.strip(),
    }
    mutation = _make_mutation("LINK_ISSUES", project_key, payload, issue_key=inward_key)
    approval = _make_approval(
        mutation,
        operation_type="TICKET_UPDATE",
        operation_label=f"Link {inward_key} '{link_type}' {outward_key}",
    )
    logger.info(
        "Staged LINK_ISSUES mutation_id=%s inward=%s outward=%s type='%s'",
        mutation.mutation_id, inward_key, outward_key, link_type,
    )
    return _staged_response(mutation, approval)
