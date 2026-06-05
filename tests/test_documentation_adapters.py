"""Unit tests for the Jira adapter (TicketRequirements -> DocContext)."""

from __future__ import annotations

import pytest

from adl_automated_delivery_pipeline.documentation.adapters.jira import jira_to_context
from adl_automated_delivery_pipeline.workflows.adl_automated_delivery_pipeline import (
    TicketRequirements,
)


def _reqs() -> TicketRequirements:
    return TicketRequirements(
        ticket_id="ADL-1729",
        summary="Add carrier codes PH/QF",
        business_requirement="Include PH and QF in the ASLB business VDS.",
        source_database="occ",
        source_tables=["occ.aslb_business"],
        output_fields=[{"name": "carrier_code", "description": "IATA carrier"}],
        transformations=["filter carrier in (PH, QF)"],
        filter_conditions=["carrier_code IN ('PH','QF')"],
        acceptance_criteria=["PH and QF rows appear"],
        extra_notes="High priority",
    )


@pytest.mark.unit
def test_jira_to_context_maps_fields() -> None:
    ctx = jira_to_context(_reqs(), sql="SELECT 1", vds_path="dremio-db.occ.aslb_business")
    assert ctx.title == "ADL-1729"
    assert "Add carrier codes" in ctx.subtitle
    assert ctx.metadata["ticket_id"] == "ADL-1729"
    assert ctx.data["source_tables"] == ["occ.aslb_business"]
    assert ctx.data["sql"] == "SELECT 1"
    assert ctx.data["vds_path"] == "dremio-db.occ.aslb_business"


@pytest.mark.unit
def test_source_stubs_raise_not_implemented() -> None:
    from adl_automated_delivery_pipeline.documentation.adapters import (
        dremio,
        meeting,
        sprint,
    )
    for fn in (sprint.sprint_to_context, meeting.meeting_to_context, dremio.dremio_to_context):
        with pytest.raises(NotImplementedError):
            fn(object())
