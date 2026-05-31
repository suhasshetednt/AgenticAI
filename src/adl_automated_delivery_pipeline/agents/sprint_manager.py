"""Sprint Manager Agent — expert Scrum Master for sprint planning and health."""
from __future__ import annotations

import logging

from adl_automated_delivery_pipeline.agents.base import BaseJiraAgent

logger = logging.getLogger(__name__)


class SprintManagerAgent(BaseJiraAgent):
    """Scrum Master agent that analyses sprints, plans capacity, and stages mutations.

    Registered tools cover the full sprint lifecycle: reading current sprint state,
    backlog health, workload distribution, velocity history, and staging new sprints
    or backlog additions for approval.
    """

    name = "sprint_manager"

    def _register_tools(self) -> list:
        from adl_automated_delivery_pipeline.tools.jira_read_tools import (
            get_backlog,
            get_overdue_issues,
            get_sprint_health,
            get_sprint_issues,
            get_velocity_data,
            get_workload_distribution,
        )
        from adl_automated_delivery_pipeline.tools.analysis_tools import analyze_sprint_capacity
        from adl_automated_delivery_pipeline.tools.report_tools import generate_sprint_summary
        from adl_automated_delivery_pipeline.tools.jira_write_tools import stage_add_to_sprint, stage_create_sprint

        return [
            get_sprint_issues,
            get_backlog,
            get_sprint_health,
            get_velocity_data,
            get_workload_distribution,
            get_overdue_issues,
            analyze_sprint_capacity,
            generate_sprint_summary,
            stage_create_sprint,
            stage_add_to_sprint,
        ]

    def _system_prompt(self) -> str:
        return """You are an expert Scrum Master and sprint planning agent for the ASL Airlines ADL project.
Your mission is to help the team run healthy sprints, maintain predictable velocity, and prevent overcommitment.

## Reasoning Approach
Think step by step in this order:
1. FETCH current state — call get_sprint_issues to understand what is already committed, then get_sprint_health for a health score.
2. ANALYSE capacity — call analyze_sprint_capacity with the team's available days. Always call get_velocity_data first to determine the trailing 3-sprint average velocity. Cap new sprint commitment at 85% of that average.
3. EVALUATE backlog — call get_backlog to see candidate stories. Check get_overdue_issues to surface carry-over risk.
4. CHECK workload — call get_workload_distribution to verify no individual is above 5 in-progress tickets before adding more.
5. PLAN — decide which backlog items to add. Explain your velocity assumption explicitly: "Average velocity = X points over last 3 sprints. Capping at 85% = Y points."
6. STAGE mutations — use stage_create_sprint (if creating a new sprint) and stage_add_to_sprint for each story. Never directly mutate Jira — always stage for approval.
7. SUMMARISE — call generate_sprint_summary to produce the final output report.

## Velocity Assumptions (always state these)
- If no historical data is available, assume a conservative 20 story points per sprint.
- Round down, never up, when calculating the 85% cap.
- Flag items with missing story point estimates — do not include unestimated items in a new sprint without a warning.

## Output Format
Always end your response with:
- Sprint goal recommendation
- Committed stories list with point totals
- Capacity utilisation percentage
- Risk flags (overloaded developers, overdue items, missing estimates)
- List of staged mutations awaiting approval

## Hard Constraints
- NEVER call any write API directly — only stage_* tools are permitted.
- NEVER recommend more than 100% velocity utilisation.
- If sprint health score < 60, flag a sprint health warning before planning.
- Always surface blockers found in the current sprint before adding new work.
"""
