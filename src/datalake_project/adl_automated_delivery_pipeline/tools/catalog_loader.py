"""Data catalog loader — reads catalog_data.json + excel_master.json for query assistance.

Mirrors the enrichment logic in generate_catalog.py but as reusable, cached functions
so the Dremio agent can discover exact table and column names when writing SQL.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Catalog JSON files live two levels above this package (D:\Agents\)
_AGENTS_ROOT = Path(__file__).resolve().parent.parent.parent
_CATALOG_JSON = _AGENTS_ROOT / "catalog_data.json"
_EXCEL_MASTER = _AGENTS_ROOT / "excel_master.json"

# Domains shown in the compact index injected into the system prompt.
# amos.ldg is excluded here because 1836 names would bloat the prompt —
# it is searchable via search_tables() instead.
_INDEX_DOMAINS: frozenset[str] = frozenset({
    "hoc",
    "mm.table",
    "mssql",
    "sap",
    "xero.tables",
    "masters.file",
    "tally",
})

# Domains included in search_catalog lookups — includes amos.ldg so the
# agent can find rotables, rotables_trend, and all other AMOS source tables.
_SEARCH_DOMAINS: frozenset[str] = _INDEX_DOMAINS | frozenset({"amos.ldg", "amos.tables"})

_DOMAIN_LABEL: dict[str, str] = {
    "amos.ldg":    "AMOS",
    "amos.tables": "AMOS",
    "hoc":         "HOC",
    "mm.table":    "Movement Manager",
    "mssql":       "MSSQL",
    "sap":         "SAP",
    "xero.tables": "Xero",
    "masters.file":"Master Files",
    "tally":       "Tally",
}


@lru_cache(maxsize=1)
def _load_raw() -> tuple[list[dict[str, Any]], dict[str, str], dict[str, list[dict[str, Any]]]]:
    """Load and enrich catalog data (unfiltered). Cached for the process lifetime.

    Returns all tables regardless of domain — callers apply their own domain filter.
    """
    if not _CATALOG_JSON.exists():
        logger.warning("catalog_data.json not found at %s", _CATALOG_JSON)
        return [], {}, {}

    with _CATALOG_JSON.open(encoding="utf-8") as f:
        data = json.load(f)

    tables: list[dict[str, Any]] = data["tables"]
    descriptions: dict[str, str] = dict(data.get("descriptions", {}))
    columns: dict[str, list[dict[str, Any]]] = {k: list(v) for k, v in data.get("columns", {}).items()}

    # Enrich from excel_master.json when present (same logic as generate_catalog.py)
    if _EXCEL_MASTER.exists():
        try:
            with _EXCEL_MASTER.open(encoding="utf-8") as f:
                excel = json.load(f)
            excel_tables: dict[str, Any] = excel.get("tables", {})
            excel_columns: dict[str, list[dict[str, Any]]] = excel.get("columns", {})

            excel_lookup = {
                (name.lower(), info.get("domain_dremio", "")): name
                for name, info in excel_tables.items()
            }

            for t in tables:
                key = (t["table"].lower(), t.get("domain", ""))
                ename = excel_lookup.get(key)
                if not ename:
                    continue
                excel_desc = excel_tables[ename].get("description", "")
                if excel_desc:
                    descriptions[t["table"]] = excel_desc
                ecols = excel_columns.get(ename, [])
                if ecols:
                    ecol_map = {c["name"].lower(): c for c in ecols}
                    for col in columns.get(t["table"], []):
                        if not col.get("desc"):
                            col["desc"] = ecol_map.get(col["name"].lower(), {}).get("desc", "")
        except Exception as exc:
            logger.warning("Failed to enrich from excel_master.json: %s", exc)

    return tables, descriptions, columns


def format_catalog_index() -> str:
    """Compact table-name index grouped by domain — for injection into the system prompt.

    AMOS (amos.ldg, 1800+ tables) is excluded from the name listing to keep the
    prompt small, but is fully searchable via search_catalog(). A note is included
    so the agent knows to search rather than assume AMOS tables don't exist.
    """
    all_tables, _, _ = _load_raw()
    if not all_tables:
        return "(data catalog unavailable — catalog_data.json not found)"

    index_tables = [t for t in all_tables if t.get("domain") in _INDEX_DOMAINS]
    amos_count = sum(1 for t in all_tables if t.get("domain") in {"amos.ldg", "amos.tables"})

    by_domain: dict[str, list[str]] = {}
    for t in index_tables:
        by_domain.setdefault(t["domain"], []).append(t["table"])

    total = len(index_tables) + amos_count
    lines = [
        f"DATA CATALOG — {total} tables across {len(by_domain) + 1} sources",
        "Call search_catalog(keyword) to get column details before writing SQL.",
        "",
        f"[AMOS / amos.ldg]  {amos_count} tables — too many to list.",
        "  Use search_catalog('rotables'), search_catalog('flight'), etc. to find AMOS tables.",
        "  AMOS tables are always accessible via the amos_postgres source in Dremio.",
    ]
    for domain in sorted(by_domain):
        label = _DOMAIN_LABEL.get(domain, domain)
        names = ", ".join(sorted(by_domain[domain]))
        lines.append(f"[{label} / {domain}]")
        lines.append(f"  {names}")
    return "\n".join(lines)


def search_tables(keyword: str, max_results: int = 15) -> list[dict[str, Any]]:
    """Return tables and columns whose name or description contains *keyword*.

    Searches across all domains including AMOS (amos.ldg).
    Tables with a direct name match are returned with all columns; column-only
    matches return only the matching columns.
    """
    all_tables, descriptions, columns = _load_raw()
    kw = keyword.strip().lower()
    if not kw:
        return []

    results: list[dict[str, Any]] = []
    for t in all_tables:
        if t.get("domain") not in _SEARCH_DOMAINS:
            continue

        tname = t["table"]
        tdesc = descriptions.get(tname, "")
        all_cols = columns.get(tname, [])

        table_hit = kw in tname.lower() or kw in tdesc.lower()
        col_matches = [
            c for c in all_cols
            if kw in c["name"].lower() or kw in c.get("desc", "").lower()
        ]

        if not table_hit and not col_matches:
            continue

        results.append({
            "table": tname,
            "source": t["source"],
            "domain": t["domain"],
            "description": tdesc,
            "total_columns": len(all_cols),
            "columns": all_cols if table_hit else col_matches,
        })

        if len(results) >= max_results:
            break

    return results
