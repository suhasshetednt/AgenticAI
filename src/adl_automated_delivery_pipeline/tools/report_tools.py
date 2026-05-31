"""Report generation tools — compose readable reports from Jira data.

These tools call the underlying read-tool functions directly (not via LangChain
tool invocation) to avoid double-wrapping.  They return structured dicts plus
pre-formatted text ready for the LLM to present to the user.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool

# Import the underlying callable functions (not the @tool wrappers).
# Because @tool wraps the function as a BaseTool, we access the original
# via the .func attribute exposed by LangChain's @tool decorator.
from adl_automated_delivery_pipeline.tools.jira_read_tools import (
    get_blockers,
    get_critical_defects,
    get_overdue_issues,
    get_sprint_health,
    get_sprint_issues,
    get_velocity_data,
    get_workload_distribution,
    search_issues,
)

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────


def _invoke(tool_fn, **kwargs) -> dict:
    """Call a LangChain @tool's underlying function, handling both .func and direct callable."""
    try:
        fn = getattr(tool_fn, "func", tool_fn)
        return fn(**kwargs)
    except Exception as exc:  # noqa: BLE001 — report tools must not crash the caller
        logger.error("Report tool internal call failed (%s): %s", getattr(tool_fn, "name", str(tool_fn)), exc)
        return {"status": "FAILED", "error": str(exc)}


def _safe_list(result: dict, key: str) -> list:
    """Extract a list from a tool result, returning [] on failure."""
    if result.get("status") != "SUCCESS":
        return []
    return result.get(key, []) or []


# ── Report tools ──────────────────────────────────────────────────────


@tool
def generate_sprint_summary(project_key: str) -> dict:
    """Generate a comprehensive sprint summary report for a project.

    Internally fetches sprint health, blockers, overdue issues, and workload
    distribution to compose a human-readable summary.

    Args:
        project_key: Jira project key, e.g. "ADL".

    Returns:
        Dict with status="SUCCESS", structured data, and formatted summary_text.
    """
    health = _invoke(get_sprint_health, project_key=project_key)
    blockers_result = _invoke(get_blockers, project_key=project_key)
    overdue_result = _invoke(get_overdue_issues, project_key=project_key)
    workload_result = _invoke(get_workload_distribution, project_key=project_key)

    # Extract data
    health_score = health.get("health_score", "UNKNOWN")
    completion_pct = health.get("completion_pct", 0.0)
    counts = health.get("counts", {})
    total_issues = health.get("total_issues", 0)

    blockers = _safe_list(blockers_result, "blockers")
    overdue = _safe_list(overdue_result, "overdue_issues")
    distribution = _safe_list(workload_result, "distribution")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        f"# Sprint Summary — {project_key}",
        f"_Generated: {now_iso}_",
        "",
        f"## Health Status: {health_score}",
        f"- Total issues: {total_issues}",
        f"- Completion: {completion_pct}%",
        f"- Done: {counts.get('Done', 0)}  |  In Progress: {counts.get('In Progress', 0)}"
        f"  |  To Do: {counts.get('To Do', 0)}  |  Blocked: {counts.get('Blocked', 0)}",
        "",
        f"## Blockers ({len(blockers)})",
    ]
    if blockers:
        for b in blockers[:10]:
            lines.append(f"- [{b['key']}] {b['summary']} — assigned to {b.get('assignee') or 'Unassigned'}")
    else:
        lines.append("- No blockers detected.")

    lines += [
        "",
        f"## Overdue Issues ({len(overdue)})",
    ]
    if overdue:
        for o in overdue[:10]:
            lines.append(
                f"- [{o['key']}] {o['summary']} (due: {o.get('due_date', 'unknown')}) "
                f"— {o.get('assignee') or 'Unassigned'}"
            )
    else:
        lines.append("- No overdue issues.")

    lines += [
        "",
        "## Workload Distribution (Active Sprint, Open Issues)",
    ]
    if distribution:
        for d in distribution[:8]:
            lines.append(
                f"- {d['assignee']}: {d['ticket_count']} tickets, {d['story_points']} SP"
            )
    else:
        lines.append("- No workload data available.")

    summary_text = "\n".join(lines)

    return {
        "status": "SUCCESS",
        "project_key": project_key,
        "generated_at": now_iso,
        "health_score": health_score,
        "completion_pct": completion_pct,
        "total_issues": total_issues,
        "blocker_count": len(blockers),
        "overdue_count": len(overdue),
        "distribution": distribution,
        "summary_text": summary_text,
    }


@tool
def generate_standup_report(
    project_key: str,
    assignee: Optional[str] = None,
) -> dict:
    """Generate a daily standup report showing in-progress and recently-done tickets.

    If *assignee* is specified, filters to only that person's tickets.

    Args:
        project_key: Jira project key, e.g. "ADL".
        assignee: Optional display name or email to filter by (case-insensitive partial match).

    Returns:
        Dict with status="SUCCESS", in_progress list, done_recently list, and standup_text.
    """
    # JQL for in-progress tickets
    assignee_filter = f' AND assignee="{assignee}"' if assignee else ""
    jql_in_progress = (
        f"project={project_key} AND sprint in openSprints() "
        f"AND status in ('In Progress', 'In Review', 'Testing'){assignee_filter} "
        "ORDER BY updated DESC"
    )
    jql_done = (
        f"project={project_key} AND sprint in openSprints() "
        f"AND status in (Done, Resolved, Closed){assignee_filter} "
        "AND updated >= -2d ORDER BY updated DESC"
    )

    in_progress_result = _invoke(search_issues, jql=jql_in_progress, max_results=20)
    done_result = _invoke(search_issues, jql=jql_done, max_results=20)

    in_progress = _safe_list(in_progress_result, "issues")
    done_recently = _safe_list(done_result, "issues")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title_suffix = f" — {assignee}" if assignee else ""

    lines: list[str] = [
        f"# Daily Standup — {project_key}{title_suffix}",
        f"_Generated: {now_iso}_",
        "",
        "## In Progress",
    ]
    if in_progress:
        for issue in in_progress:
            lines.append(
                f"- [{issue['key']}] {issue['summary']}"
                f" (assigned: {issue.get('assignee') or 'Unassigned'})"
            )
    else:
        lines.append("- Nothing currently in progress.")

    lines += ["", "## Completed Recently (last 2 days)"]
    if done_recently:
        for issue in done_recently:
            lines.append(
                f"- [{issue['key']}] {issue['summary']}"
                f" (completed by: {issue.get('assignee') or 'Unassigned'})"
            )
    else:
        lines.append("- Nothing completed in the last 2 days.")

    if not in_progress and not done_recently:
        lines += ["", "_No sprint activity found for this filter._"]

    standup_text = "\n".join(lines)

    return {
        "status": "SUCCESS",
        "project_key": project_key,
        "assignee_filter": assignee,
        "generated_at": now_iso,
        "in_progress_count": len(in_progress),
        "done_recently_count": len(done_recently),
        "in_progress": in_progress,
        "done_recently": done_recently,
        "standup_text": standup_text,
    }


@tool
def generate_retrospective_data(project_key: str) -> dict:
    """Generate retrospective data for the most recently closed sprint.

    Includes completion stats, velocity, blockers encountered, and a
    formatted retrospective summary.

    Args:
        project_key: Jira project key, e.g. "ADL".

    Returns:
        Dict with status="SUCCESS", metrics, and retrospective_text.
    """
    # Closed sprint issues
    closed_issues_result = _invoke(
        get_sprint_issues, project_key=project_key, sprint_state="closed"
    )
    velocity_result = _invoke(get_velocity_data, project_key=project_key, num_sprints=1)

    all_issues = _safe_list(closed_issues_result, "issues")

    # Count by status category
    completed = [
        i for i in all_issues
        if str(i.get("status", "")).lower() in {"done", "closed", "resolved"}
    ]
    incomplete = [
        i for i in all_issues
        if str(i.get("status", "")).lower() not in {"done", "closed", "resolved"}
    ]

    total = len(all_issues)
    completed_count = len(completed)
    incomplete_count = len(incomplete)
    completion_rate = round((completed_count / total * 100) if total > 0 else 0.0, 1)

    # Velocity for last sprint
    velocity_list = velocity_result.get("velocity_by_sprint", []) if velocity_result.get("status") == "SUCCESS" else []
    last_sprint_velocity = velocity_list[-1]["story_points"] if velocity_list else 0.0
    last_sprint_name = velocity_list[-1]["sprint"] if velocity_list else "Last sprint"

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        f"# Retrospective Data — {project_key}",
        f"_Generated: {now_iso}_",
        "",
        f"## Sprint: {last_sprint_name}",
        "",
        "## Sprint Performance",
        f"- Total planned: {total}",
        f"- Completed: {completed_count} ({completion_rate}%)",
        f"- Incomplete / carried over: {incomplete_count}",
        f"- Velocity: {last_sprint_velocity} story points",
        "",
        "## What Went Well (Completed Tickets)",
    ]
    for issue in completed[:5]:
        lines.append(f"- [{issue['key']}] {issue['summary']}")
    if len(completed) > 5:
        lines.append(f"  ... and {len(completed) - 5} more.")

    lines += ["", "## What Needs Improvement (Incomplete / Carried Over)"]
    for issue in incomplete[:5]:
        lines.append(
            f"- [{issue['key']}] {issue['summary']} (status: {issue.get('status', 'Unknown')})"
        )
    if len(incomplete) > 5:
        lines.append(f"  ... and {len(incomplete) - 5} more.")

    lines += [
        "",
        "## Action Items Recommended",
        "- Review and close any incomplete tickets or move to next sprint backlog.",
        "- Identify root causes for incomplete work.",
        "- Adjust capacity planning if completion rate < 70%.",
    ]

    retro_text = "\n".join(lines)

    return {
        "status": "SUCCESS",
        "project_key": project_key,
        "generated_at": now_iso,
        "sprint_name": last_sprint_name,
        "total_planned": total,
        "completed_count": completed_count,
        "incomplete_count": incomplete_count,
        "completion_rate": completion_rate,
        "velocity": last_sprint_velocity,
        "retrospective_text": retro_text,
    }


@tool
def generate_release_notes(
    project_key: str,
    sprint_name: Optional[str] = None,
) -> dict:
    """Generate release notes from completed tickets in the current or specified sprint.

    Tickets are grouped by issue type (Bug, Story, Task, etc.).

    Args:
        project_key: Jira project key, e.g. "ADL".
        sprint_name: Optional exact sprint name to filter by.  Defaults to the
                     active sprint.

    Returns:
        Dict with status="SUCCESS", grouped issues, and release_notes_text.
    """
    if sprint_name:
        sprint_filter = f'sprint = "{sprint_name}"'
    else:
        sprint_filter = "sprint in openSprints()"

    jql = (
        f"project={project_key} AND {sprint_filter} "
        "AND statusCategory=Done ORDER BY issuetype ASC, priority ASC"
    )
    result = _invoke(search_issues, jql=jql, max_results=100)
    issues = _safe_list(result, "issues")

    # Group by issue type
    by_type: dict[str, list[dict]] = {}
    for issue in issues:
        itype = issue.get("issue_type") or "Other"
        by_type.setdefault(itype, []).append(issue)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sprint_label = sprint_name or "Current Sprint"

    lines: list[str] = [
        f"# Release Notes — {project_key} ({sprint_label})",
        f"_Generated: {now_iso}_",
        "",
    ]

    if not issues:
        lines.append("_No completed tickets found for this sprint._")
    else:
        # Preferred order for release notes readability
        type_order = ["Story", "Feature", "Bug", "Task", "Sub-task", "Improvement", "Epic"]
        sorted_types = sorted(
            by_type.keys(),
            key=lambda t: type_order.index(t) if t in type_order else 99,
        )
        for itype in sorted_types:
            group = by_type[itype]
            section_emoji = {
                "Bug": "Bug Fixes",
                "Story": "Stories / Features",
                "Feature": "New Features",
                "Task": "Tasks",
                "Improvement": "Improvements",
                "Sub-task": "Sub-tasks",
                "Epic": "Epics",
            }.get(itype, itype)
            lines.append(f"## {section_emoji}")
            for issue in group:
                labels_str = (
                    " [" + ", ".join(issue.get("labels", [])) + "]"
                    if issue.get("labels")
                    else ""
                )
                lines.append(f"- **{issue['key']}**: {issue['summary']}{labels_str}")
            lines.append("")

    release_notes_text = "\n".join(lines)

    return {
        "status": "SUCCESS",
        "project_key": project_key,
        "sprint_label": sprint_label,
        "generated_at": now_iso,
        "total_completed": len(issues),
        "by_type": {k: len(v) for k, v in by_type.items()},
        "release_notes_text": release_notes_text,
    }


@tool
def generate_risk_report(project_key: str) -> dict:
    """Generate a comprehensive risk report combining blockers, overdue, and defect data.

    Args:
        project_key: Jira project key, e.g. "ADL".

    Returns:
        Dict with status="SUCCESS", risk metrics, and risk_report_text.
    """
    blockers_result = _invoke(get_blockers, project_key=project_key)
    overdue_result = _invoke(get_overdue_issues, project_key=project_key)
    defects_result = _invoke(get_critical_defects, project_key=project_key)
    health_result = _invoke(get_sprint_health, project_key=project_key)

    blockers = _safe_list(blockers_result, "blockers")
    overdue = _safe_list(overdue_result, "overdue_issues")
    defects = _safe_list(defects_result, "defects")

    total_issues = health_result.get("total_issues", 0)
    health_score = health_result.get("health_score", "UNKNOWN")
    completion_pct = health_result.get("completion_pct", 0.0)

    # Compute composite risk score inline (mirrors calculate_risk_score logic)
    blocked_count = len(blockers)
    overdue_count = len(overdue)
    defect_count = len(defects)

    if total_issues > 0:
        blocked_score = round(min(blocked_count / total_issues, 1.0) * 40)
        overdue_score = round(min(overdue_count / total_issues, 1.0) * 35)
    else:
        blocked_score = 0
        overdue_score = 0
    defect_score = round(min(defect_count, 5) / 5 * 25)
    composite_score = min(blocked_score + overdue_score + defect_score, 100)

    if composite_score <= 25:
        risk_level = "LOW"
    elif composite_score <= 50:
        risk_level = "MEDIUM"
    elif composite_score <= 75:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        f"# Risk Report — {project_key}",
        f"_Generated: {now_iso}_",
        "",
        f"## Overall Risk: {risk_level} (Score: {composite_score}/100)",
        f"Sprint health: {health_score} | Completion: {completion_pct}%",
        "",
        f"## Blockers ({blocked_count})",
    ]
    if blockers:
        for b in blockers[:8]:
            lines.append(
                f"- [{b['key']}] {b['summary']}"
                f" — {b.get('assignee') or 'Unassigned'}"
            )
        if len(blockers) > 8:
            lines.append(f"  ... and {len(blockers) - 8} more.")
    else:
        lines.append("- No blockers.")

    lines += [f"", f"## Overdue Issues ({overdue_count})"]
    if overdue:
        for o in overdue[:8]:
            lines.append(
                f"- [{o['key']}] {o['summary']}"
                f" (due: {o.get('due_date', 'unknown')})"
                f" — {o.get('assignee') or 'Unassigned'}"
            )
        if len(overdue) > 8:
            lines.append(f"  ... and {len(overdue) - 8} more.")
    else:
        lines.append("- No overdue issues.")

    lines += [f"", f"## Critical / High Defects ({defect_count})"]
    if defects:
        for d in defects[:8]:
            lines.append(
                f"- [{d['key']}] {d['summary']}"
                f" (priority: {d.get('priority', 'Unknown')})"
                f" — {d.get('assignee') or 'Unassigned'}"
            )
        if len(defects) > 8:
            lines.append(f"  ... and {len(defects) - 8} more.")
    else:
        lines.append("- No critical defects.")

    lines += [
        "",
        "## Recommendations",
    ]
    if risk_level == "CRITICAL":
        lines.append("- IMMEDIATE ACTION required — escalate to management.")
        lines.append("- Hold blocker resolution meeting today.")
    elif risk_level == "HIGH":
        lines.append("- Schedule blocker triage meeting this week.")
        lines.append("- Re-prioritise overdue items with assignees.")
    elif risk_level == "MEDIUM":
        lines.append("- Monitor blockers and overdue items daily.")
        lines.append("- Ensure critical defects are prioritised in next sprint planning.")
    else:
        lines.append("- Sprint is on track. Continue monitoring.")

    risk_report_text = "\n".join(lines)

    return {
        "status": "SUCCESS",
        "project_key": project_key,
        "generated_at": now_iso,
        "risk_score": composite_score,
        "risk_level": risk_level,
        "health_score": health_score,
        "completion_pct": completion_pct,
        "blocker_count": blocked_count,
        "overdue_count": overdue_count,
        "defect_count": defect_count,
        "risk_report_text": risk_report_text,
    }
