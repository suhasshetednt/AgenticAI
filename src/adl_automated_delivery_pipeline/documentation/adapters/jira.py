"""Jira adapter — TicketRequirements (+ optional SQL/VDS) -> DocContext."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from adl_automated_delivery_pipeline.documentation.context import DocContext

_FEATURE_TAG = re.compile(r"^\s*\[([^\]]+)\]")


def _feature_name(summary: str) -> str:
    """Derive a clean feature name from a Jira summary.

    ASL summaries are formatted '[Feature Name] verbose description ...'. Use the
    bracketed tag as the document title; fall back to the full summary otherwise.
    """
    m = _FEATURE_TAG.match(summary or "")
    return (m.group(1).strip() if m else (summary or "").strip())


def jira_to_context(reqs: Any, sql: str = "", vds_path: str = "") -> DocContext:
    """Map a TicketRequirements dataclass into a generic DocContext."""
    prepared = datetime.now(timezone.utc).strftime("%d %B %Y")
    return DocContext(
        # Title is the clean feature name (drives the document title and filename);
        # the ticket id is kept in metadata only — never shown in the header/footer.
        title=_feature_name(reqs.summary),
        subtitle="Technical Implementation",
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
            "join_analysis": getattr(reqs, "join_analysis", ""),
            "sql": sql,
            "vds_path": vds_path,
        },
    )
