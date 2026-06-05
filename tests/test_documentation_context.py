"""Unit tests for DocContext fact resolution."""

from __future__ import annotations

import pytest

from adl_automated_delivery_pipeline.documentation.context import DocContext


@pytest.mark.unit
def test_get_resolves_title_subtitle_dotted_and_bare_keys() -> None:
    ctx = DocContext(
        title="ADL-1729 VDS",
        subtitle="Add carrier codes",
        metadata={"prepared_by": "DnT"},
        data={"vds_path": "dremio-db.occ.aslb_business", "rows": [1, 2]},
    )
    assert ctx.get("title") == "ADL-1729 VDS"
    assert ctx.get("subtitle") == "Add carrier codes"
    assert ctx.get("metadata.prepared_by") == "DnT"
    assert ctx.get("data.vds_path") == "dremio-db.occ.aslb_business"
    assert ctx.get("vds_path") == "dremio-db.occ.aslb_business"  # bare -> data
    assert ctx.get("prepared_by") == "DnT"                       # bare -> metadata
    assert ctx.get("missing", default="-") == "-"
