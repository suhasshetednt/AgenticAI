"""Jira adapter — TicketRequirements (+ optional SQL/VDS) -> DocContext."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from adl_automated_delivery_pipeline.documentation.context import DocContext


def jira_to_context(reqs: Any, sql: str = "", vds_path: str = "") -> DocContext:
    """Map a TicketRequirements dataclass into a generic DocContext."""
    prepared = datetime.now(timezone.utc).strftime("%d %B %Y")
    return DocContext(
        title=reqs.ticket_id,
        subtitle=reqs.summary,
        metadata={
            "ticket_id": reqs.ticket_id,
            "team": "DnT Infotech - DataLake Team",
            "prepared": prepared,
        },
        data={
            "summary": reqs.summary,
            "business_requirement": reqs.business_requirement,
            "source_database": reqs.source_database,
            "source_tables": list(reqs.source_tables),
            "output_fields": list(reqs.output_fields),
            "transformations": list(reqs.transformations),
            "filter_conditions": list(reqs.filter_conditions),
            "acceptance_criteria": list(reqs.acceptance_criteria),
            "extra_notes": reqs.extra_notes,
            "sql": sql,
            "vds_path": vds_path,
        },
    )
