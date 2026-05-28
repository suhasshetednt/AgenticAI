"""LangChain @tool functions for READ-ONLY Jira operations.

Each tool creates its own JIRA() connection (stateless per-call pattern).
No writes are performed here — all mutation tools live in jira_write_tools.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from jira import JIRA, JIRAError
from langchain_core.tools import tool

from adl_automated_delivery_pipeline.config import settings

logger = logging.getLogger(__name__)


def _get_jira() -> JIRA:
    """Create and return a JIRA client using credentials from settings."""
    return JIRA(
        server=settings.JIRA_INSTANCE_URL,
        basic_auth=(settings.JIRA_USERNAME, settings.JIRA_API_TOKEN),
    )


def _safe_str(value: Any) -> str:
    """Return str(value) or empty string if value is None."""
    return str(value) if value is not None else ""


def _issue_to_dict(issue: Any) -> dict:
    """Convert a jira.Issue object to a plain serialisable dict."""
    fields = issue.fields
    assignee = getattr(fields, "assignee", None)
    priority = getattr(fields, "priority", None)
    status = getattr(fields, "status", None)
    comments = getattr(getattr(fields, "comment", None), "comments", []) or []
    components = [c.name for c in (getattr(fields, "components", None) or [])]
    labels = list(getattr(fields, "labels", None) or [])

    # Issue links
    raw_links = getattr(fields, "issuelinks", None) or []
    links: list[dict] = []
    for lnk in raw_links:
        link_type = getattr(lnk, "type", None)
        inward = getattr(lnk, "inwardIssue", None)
        outward = getattr(lnk, "outwardIssue", None)
        links.append(
            {
                "type": _safe_str(getattr(link_type, "name", None)) if link_type else "",
                "inward_issue": _safe_str(getattr(inward, "key", None)) if inward else None,
                "outward_issue": _safe_str(getattr(outward, "key", None)) if outward else None,
            }
        )

    return {
        "key": issue.key,
        "summary": _safe_str(getattr(fields, "summary", None)),
        "description": _safe_str(getattr(fields, "description", None)),
        "status": _safe_str(getattr(status, "name", None)) if status else "",
        "assignee": _safe_str(getattr(assignee, "displayName", None)) if assignee else None,
        "assignee_email": _safe_str(getattr(assignee, "emailAddress", None)) if assignee else None,
        "priority": _safe_str(getattr(priority, "name", None)) if priority else "",
        "story_points": getattr(fields, "customfield_10016", None),
        "labels": labels,
        "components": components,
        "created": _safe_str(getattr(fields, "created", None)),
        "updated": _safe_str(getattr(fields, "updated", None)),
        "comment_count": len(comments),
        "issue_links": links,
        "issue_type": _safe_str(
            getattr(getattr(fields, "issuetype", None), "name", None)
        ),
    }


# ── Tools ─────────────────────────────────────────────────────────────


@tool
def get_issue(issue_key: str) -> dict:
    """Fetch full details for a single Jira issue by its key (e.g. ADL-123).

    Returns summary, description, status, assignee, priority, story points,
    labels, components, timestamps, comment count, and issue links.

    Args:
        issue_key: The Jira issue key, e.g. "ADL-123".

    Returns:
        Dict with status="SUCCESS" and issue details, or status="FAILED" with error.
    """
    try:
        jira = _get_jira()
        issue = jira.issue(issue_key)
        return {"status": "SUCCESS", "issue": _issue_to_dict(issue)}
    except JIRAError as exc:
        logger.error("get_issue JIRAError for %s: %s", issue_key, exc)
        return {"status": "FAILED", "error": str(exc), "issue_key": issue_key}
    except ValueError as exc:
        logger.error("get_issue ValueError for %s: %s", issue_key, exc)
        return {"status": "FAILED", "error": str(exc), "issue_key": issue_key}


@tool
def search_issues(jql: str, max_results: int = 50) -> dict:
    """Run a JQL query against Jira and return matching issues.

    Args:
        jql: A valid JQL string, e.g. 'project=ADL AND status="In Progress"'.
        max_results: Maximum number of results to return (default 50, max 100).

    Returns:
        Dict with status="SUCCESS", total count, and list of issues with key fields.
    """
    max_results = min(max_results, 100)
    try:
        jira = _get_jira()
        issues = jira.search_issues(jql, maxResults=max_results)
        return {
            "status": "SUCCESS",
            "jql": jql,
            "total": len(issues),
            "issues": [_issue_to_dict(i) for i in issues],
        }
    except JIRAError as exc:
        logger.error("search_issues JIRAError jql='%s': %s", jql, exc)
        return {"status": "FAILED", "error": str(exc), "jql": jql}
    except ValueError as exc:
        logger.error("search_issues ValueError jql='%s': %s", jql, exc)
        return {"status": "FAILED", "error": str(exc), "jql": jql}


@tool
def get_sprint_issues(
    project_key: str, sprint_state: str = "active"
) -> dict:
    """Fetch all issues in the active or most-recent closed sprint for a project.

    Args:
        project_key: Jira project key, e.g. "ADL".
        sprint_state: "active" (default) or "closed".

    Returns:
        Dict with status="SUCCESS", sprint_state, and list of sprint issues.
    """
    state = sprint_state.lower()
    if state == "active":
        sprint_filter = "sprint in openSprints()"
    elif state == "closed":
        sprint_filter = "sprint in closedSprints()"
    else:
        return {
            "status": "FAILED",
            "error": f"Invalid sprint_state '{sprint_state}'. Use 'active' or 'closed'.",
        }

    jql = f"project={project_key} AND {sprint_filter} ORDER BY priority ASC"
    try:
        jira = _get_jira()
        issues = jira.search_issues(jql, maxResults=200)
        return {
            "status": "SUCCESS",
            "project_key": project_key,
            "sprint_state": sprint_state,
            "total": len(issues),
            "issues": [_issue_to_dict(i) for i in issues],
        }
    except JIRAError as exc:
        logger.error(
            "get_sprint_issues JIRAError project=%s state=%s: %s",
            project_key, sprint_state, exc,
        )
        return {"status": "FAILED", "error": str(exc), "project_key": project_key}


@tool
def get_backlog(project_key: str, max_results: int = 100) -> dict:
    """Return backlog issues (not assigned to any sprint) for a project.

    Args:
        project_key: Jira project key, e.g. "ADL".
        max_results: Maximum issues to return (default 100).

    Returns:
        Dict with status="SUCCESS" and list of backlog issues.
    """
    jql = (
        f"project={project_key} "
        "AND sprint is EMPTY "
        "AND statusCategory != Done "
        "ORDER BY priority ASC, created ASC"
    )
    try:
        jira = _get_jira()
        issues = jira.search_issues(jql, maxResults=max_results)
        return {
            "status": "SUCCESS",
            "project_key": project_key,
            "total": len(issues),
            "issues": [_issue_to_dict(i) for i in issues],
        }
    except JIRAError as exc:
        logger.error("get_backlog JIRAError project=%s: %s", project_key, exc)
        return {"status": "FAILED", "error": str(exc), "project_key": project_key}


@tool
def get_sprint_health(project_key: str) -> dict:
    """Compute sprint health metrics for the active sprint in a project.

    Counts issues by status category, calculates completion percentage, and
    assigns a health score (HEALTHY / AT_RISK / CRITICAL).

    Args:
        project_key: Jira project key, e.g. "ADL".

    Returns:
        Dict with status="SUCCESS", counts by status, completion_pct, and health_score.
    """
    jql = f"project={project_key} AND sprint in openSprints()"
    try:
        jira = _get_jira()
        issues = jira.search_issues(jql, maxResults=500)
    except JIRAError as exc:
        logger.error("get_sprint_health JIRAError project=%s: %s", project_key, exc)
        return {"status": "FAILED", "error": str(exc), "project_key": project_key}

    counts: dict[str, int] = {
        "Done": 0,
        "In Progress": 0,
        "To Do": 0,
        "Blocked": 0,
        "Other": 0,
    }
    total = len(issues)

    for issue in issues:
        status_name: str = _safe_str(
            getattr(getattr(issue.fields, "status", None), "name", None)
        )
        lower_status = status_name.lower()
        if lower_status in {"done", "closed", "resolved"}:
            counts["Done"] += 1
        elif lower_status in {"in progress", "in review", "testing"}:
            counts["In Progress"] += 1
        elif lower_status in {"blocked", "impediment"}:
            counts["Blocked"] += 1
        elif lower_status in {"to do", "open", "backlog", "selected for development"}:
            counts["To Do"] += 1
        else:
            counts["Other"] += 1

    completion_pct = round((counts["Done"] / total * 100) if total > 0 else 0.0, 1)

    # Health scoring heuristics
    blocked_ratio = counts["Blocked"] / total if total > 0 else 0
    if completion_pct >= 70 and blocked_ratio < 0.1:
        health_score = "HEALTHY"
    elif completion_pct >= 40 and blocked_ratio < 0.25:
        health_score = "AT_RISK"
    else:
        health_score = "CRITICAL"

    return {
        "status": "SUCCESS",
        "project_key": project_key,
        "total_issues": total,
        "counts": counts,
        "completion_pct": completion_pct,
        "health_score": health_score,
    }


@tool
def get_blockers(project_key: str) -> dict:
    """Find blocked issues in the active sprint for a project.

    An issue is considered blocked if its status is 'Blocked' or if it has
    outward 'blocks' issue links.

    Args:
        project_key: Jira project key, e.g. "ADL".

    Returns:
        Dict with status="SUCCESS" and list of blocked issues with block details.
    """
    jql = (
        f"project={project_key} AND sprint in openSprints() "
        "AND (status=Blocked OR issueFunction in linkedIssuesOf('project={project_key}', 'blocks'))"
    ).replace("{project_key}", project_key)

    # Fallback JQL without issueFunction plugin (may not be available)
    jql_simple = (
        f"project={project_key} AND sprint in openSprints() "
        "AND status=Blocked"
    )

    try:
        jira = _get_jira()
        try:
            issues = jira.search_issues(jql, maxResults=200)
        except JIRAError:
            logger.debug("Falling back to simple blocker JQL for project=%s", project_key)
            issues = jira.search_issues(jql_simple, maxResults=200)

        blockers: list[dict] = []
        for issue in issues:
            details = _issue_to_dict(issue)
            blocking_links = [
                lnk for lnk in details["issue_links"]
                if lnk.get("type", "").lower() in {"blocks", "is blocked by"}
            ]
            details["blocking_links"] = blocking_links
            blockers.append(details)

        return {
            "status": "SUCCESS",
            "project_key": project_key,
            "blocker_count": len(blockers),
            "blockers": blockers,
        }
    except JIRAError as exc:
        logger.error("get_blockers JIRAError project=%s: %s", project_key, exc)
        return {"status": "FAILED", "error": str(exc), "project_key": project_key}


@tool
def get_workload_distribution(project_key: str) -> dict:
    """Return ticket counts per assignee for the active sprint.

    Args:
        project_key: Jira project key, e.g. "ADL".

    Returns:
        Dict with status="SUCCESS" and workload breakdown per assignee.
    """
    jql = (
        f"project={project_key} AND sprint in openSprints() "
        "AND statusCategory != Done"
    )
    try:
        jira = _get_jira()
        issues = jira.search_issues(jql, maxResults=500)
    except JIRAError as exc:
        logger.error(
            "get_workload_distribution JIRAError project=%s: %s", project_key, exc
        )
        return {"status": "FAILED", "error": str(exc), "project_key": project_key}

    distribution: dict[str, dict] = {}
    for issue in issues:
        fields = issue.fields
        assignee_obj = getattr(fields, "assignee", None)
        if assignee_obj is None:
            name = "Unassigned"
            email = ""
        else:
            name = _safe_str(getattr(assignee_obj, "displayName", "Unknown"))
            email = _safe_str(getattr(assignee_obj, "emailAddress", ""))

        if name not in distribution:
            distribution[name] = {
                "assignee": name,
                "email": email,
                "ticket_count": 0,
                "story_points": 0,
                "issues": [],
            }
        sp = getattr(fields, "customfield_10016", None) or 0
        distribution[name]["ticket_count"] += 1
        distribution[name]["story_points"] += int(sp) if sp else 0
        distribution[name]["issues"].append(issue.key)

    sorted_dist = sorted(
        distribution.values(), key=lambda x: x["ticket_count"], reverse=True
    )
    return {
        "status": "SUCCESS",
        "project_key": project_key,
        "total_open_issues": len(issues),
        "team_members": len(distribution),
        "distribution": sorted_dist,
    }


@tool
def get_overdue_issues(project_key: str) -> dict:
    """Find issues that are past their due date and not yet Done.

    Args:
        project_key: Jira project key, e.g. "ADL".

    Returns:
        Dict with status="SUCCESS" and list of overdue issues.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    jql = (
        f'project={project_key} AND due < "{today}" '
        "AND statusCategory != Done ORDER BY due ASC"
    )
    try:
        jira = _get_jira()
        issues = jira.search_issues(jql, maxResults=200)
        overdue = []
        for issue in issues:
            details = _issue_to_dict(issue)
            details["due_date"] = _safe_str(getattr(issue.fields, "duedate", None))
            overdue.append(details)

        return {
            "status": "SUCCESS",
            "project_key": project_key,
            "overdue_count": len(overdue),
            "as_of_date": today,
            "overdue_issues": overdue,
        }
    except JIRAError as exc:
        logger.error("get_overdue_issues JIRAError project=%s: %s", project_key, exc)
        return {"status": "FAILED", "error": str(exc), "project_key": project_key}


@tool
def get_critical_defects(project_key: str) -> dict:
    """Fetch unresolved bugs with Critical or High priority.

    Args:
        project_key: Jira project key, e.g. "ADL".

    Returns:
        Dict with status="SUCCESS" and list of critical/high-priority bugs.
    """
    jql = (
        f"project={project_key} AND issuetype=Bug "
        "AND priority in (Critical, High) "
        "AND statusCategory != Done "
        "ORDER BY priority ASC, created ASC"
    )
    try:
        jira = _get_jira()
        issues = jira.search_issues(jql, maxResults=200)
        return {
            "status": "SUCCESS",
            "project_key": project_key,
            "defect_count": len(issues),
            "defects": [_issue_to_dict(i) for i in issues],
        }
    except JIRAError as exc:
        logger.error(
            "get_critical_defects JIRAError project=%s: %s", project_key, exc
        )
        return {"status": "FAILED", "error": str(exc), "project_key": project_key}


@tool
def get_project_info(project_key: str) -> dict:
    """Fetch metadata for a Jira project: name, lead, issue types, and components.

    Args:
        project_key: Jira project key, e.g. "ADL".

    Returns:
        Dict with status="SUCCESS" and project metadata fields.
    """
    try:
        jira = _get_jira()
        project = jira.project(project_key)
        lead = getattr(project, "lead", None)
        issue_types_raw = getattr(project, "issueTypes", None) or []
        components_raw = jira.project_components(project_key)

        return {
            "status": "SUCCESS",
            "project_key": project_key,
            "name": _safe_str(getattr(project, "name", None)),
            "description": _safe_str(getattr(project, "description", None)),
            "lead": _safe_str(getattr(lead, "displayName", None)) if lead else None,
            "url": _safe_str(getattr(project, "self", None)),
            "issue_types": [
                {
                    "name": _safe_str(getattr(it, "name", None)),
                    "subtask": bool(getattr(it, "subtask", False)),
                }
                for it in issue_types_raw
            ],
            "components": [
                {"id": _safe_str(getattr(c, "id", None)), "name": _safe_str(getattr(c, "name", None))}
                for c in components_raw
            ],
        }
    except JIRAError as exc:
        logger.error("get_project_info JIRAError project=%s: %s", project_key, exc)
        return {"status": "FAILED", "error": str(exc), "project_key": project_key}


@tool
def get_issue_comments(issue_key: str) -> dict:
    """Fetch all comments for a Jira issue.

    Args:
        issue_key: The Jira issue key, e.g. "ADL-123".

    Returns:
        Dict with status="SUCCESS" and list of comments (author, body, created).
    """
    try:
        jira = _get_jira()
        issue = jira.issue(issue_key, fields="comment")
        comment_list = getattr(
            getattr(issue.fields, "comment", None), "comments", []
        ) or []

        comments = []
        for c in comment_list:
            author_obj = getattr(c, "author", None)
            comments.append(
                {
                    "id": _safe_str(getattr(c, "id", None)),
                    "author": _safe_str(getattr(author_obj, "displayName", None))
                    if author_obj
                    else "Unknown",
                    "author_email": _safe_str(getattr(author_obj, "emailAddress", None))
                    if author_obj
                    else "",
                    "body": _safe_str(getattr(c, "body", None)),
                    "created": _safe_str(getattr(c, "created", None)),
                    "updated": _safe_str(getattr(c, "updated", None)),
                }
            )

        return {
            "status": "SUCCESS",
            "issue_key": issue_key,
            "comment_count": len(comments),
            "comments": comments,
        }
    except JIRAError as exc:
        logger.error(
            "get_issue_comments JIRAError issue=%s: %s", issue_key, exc
        )
        return {"status": "FAILED", "error": str(exc), "issue_key": issue_key}


@tool
def get_epic_issues(epic_key: str) -> dict:
    """Fetch all issues that belong to a given epic.

    Args:
        epic_key: The Jira key of the epic, e.g. "ADL-100".

    Returns:
        Dict with status="SUCCESS" and list of issues under the epic.
    """
    # Try both the modern "Epic Link" field and the parent field (next-gen projects)
    jql_epic_link = f'"Epic Link"={epic_key}'
    jql_parent = f"issueFunction in subtasksOf('issue = {epic_key}') OR parent={epic_key}"

    try:
        jira = _get_jira()
        try:
            issues = jira.search_issues(jql_epic_link, maxResults=200)
        except JIRAError:
            logger.debug(
                "Epic Link JQL failed for %s, trying parent JQL", epic_key
            )
            try:
                issues = jira.search_issues(jql_parent, maxResults=200)
            except JIRAError as exc2:
                logger.error(
                    "get_epic_issues both JQL attempts failed for %s: %s",
                    epic_key, exc2,
                )
                return {"status": "FAILED", "error": str(exc2), "epic_key": epic_key}

        return {
            "status": "SUCCESS",
            "epic_key": epic_key,
            "total": len(issues),
            "issues": [_issue_to_dict(i) for i in issues],
        }
    except JIRAError as exc:
        logger.error("get_epic_issues JIRAError epic=%s: %s", epic_key, exc)
        return {"status": "FAILED", "error": str(exc), "epic_key": epic_key}


@tool
def get_velocity_data(project_key: str, num_sprints: int = 6) -> dict:
    """Calculate velocity from the last N closed sprints (completed story points).

    Args:
        project_key: Jira project key, e.g. "ADL".
        num_sprints: Number of closed sprints to analyse (default 6).

    Returns:
        Dict with status="SUCCESS", per-sprint velocity, average, and trend.
    """
    num_sprints = max(1, min(num_sprints, 20))
    jql = (
        f"project={project_key} AND sprint in closedSprints() "
        "AND statusCategory=Done ORDER BY sprint DESC"
    )
    try:
        jira = _get_jira()
        issues = jira.search_issues(jql, maxResults=500)
    except JIRAError as exc:
        logger.error(
            "get_velocity_data JIRAError project=%s: %s", project_key, exc
        )
        return {"status": "FAILED", "error": str(exc), "project_key": project_key}

    # Group story points by sprint name
    sprint_points: dict[str, float] = {}
    for issue in issues:
        fields = issue.fields
        sp_raw = getattr(fields, "customfield_10016", None)
        sp = float(sp_raw) if sp_raw is not None else 0.0

        sprints_raw = getattr(fields, "customfield_10020", None) or []
        if not isinstance(sprints_raw, list):
            sprints_raw = [sprints_raw]
        for sprint_obj in sprints_raw:
            if sprint_obj is None:
                continue
            sprint_name = _safe_str(getattr(sprint_obj, "name", None) or sprint_obj)
            if sprint_name:
                sprint_points[sprint_name] = sprint_points.get(sprint_name, 0.0) + sp

    # Take the most recent N sprints
    recent_sprints = list(sprint_points.items())[-num_sprints:]
    velocity_list = [
        {"sprint": name, "story_points": round(pts, 1)}
        for name, pts in recent_sprints
    ]

    total_points = sum(v["story_points"] for v in velocity_list)
    average_velocity = round(total_points / len(velocity_list), 1) if velocity_list else 0.0

    # Simple trend: compare last sprint to average
    if len(velocity_list) >= 2:
        last_sprint_pts = velocity_list[-1]["story_points"]
        trend = "UP" if last_sprint_pts > average_velocity else (
            "DOWN" if last_sprint_pts < average_velocity else "STABLE"
        )
    else:
        trend = "INSUFFICIENT_DATA"

    return {
        "status": "SUCCESS",
        "project_key": project_key,
        "sprints_analysed": len(velocity_list),
        "average_velocity": average_velocity,
        "trend": trend,
        "velocity_by_sprint": velocity_list,
    }
