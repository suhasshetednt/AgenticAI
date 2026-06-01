"""Dremio REST API tools for the LangGraph agent stack.

Supports both Dremio Cloud (uses /v0/projects/{projectId}/...) and
on-premise Dremio (uses /api/v3/...). Cloud is auto-detected when
DREMIO_PROJECT_ID is set.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests
import urllib.parse
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_DEFAULT_ROW_LIMIT = 100
# Hard cap on how long execute_dremio_sql polls a Dremio job before giving up.
# Configurable via env for environments with slow engines / heavy queries.
_SQL_TIMEOUT_SECONDS = int(os.getenv("DREMIO_SQL_TIMEOUT_S", "120"))
_JOB_POLL_INTERVAL = 2


# ── Dremio REST client ────────────────────────────────────────────────────────

def _pick_env(*names: str) -> str:
    """Return the first non-empty value among the given env var names."""
    for name in names:
        val = os.getenv(name, "").strip()
        if val:
            return val
    return ""


@dataclass
class DremioClient:
    """REST client for Dremio Cloud and on-premise Dremio.

    Automatically uses /v0/projects/{project_id}/ prefix when project_id
    is provided (Dremio Cloud), otherwise falls back to /api/v3/ (on-premise).
    """

    host: str
    project_id: str = ""
    username: str = ""
    password: str = ""
    pat: str = ""
    _session: requests.Session = field(default_factory=requests.Session, init=False, repr=False)

    def __post_init__(self) -> None:
        self._session.headers.update({"Content-Type": "application/json"})
        self._authenticate()

    def _authenticate(self) -> None:
        if self.pat:
            self._session.headers["Authorization"] = f"Bearer {self.pat}"
            return
        resp = self._session.post(
            f"{self.host.rstrip('/')}/apiv2/login",
            json={"userName": self.username, "password": self.password},
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json()["token"]
        self._session.headers["Authorization"] = f"_dremio{token}"

    @property
    def _api_base(self) -> str:
        base = self.host.rstrip("/")
        if self.project_id:
            return f"{base}/v0/projects/{self.project_id}"
        return f"{base}/api/v3"

    def get(self, path: str) -> dict:
        resp = self._session.get(f"{self._api_base}{path}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, payload: dict) -> dict:
        resp = self._session.post(f"{self._api_base}{path}", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def put(self, path: str, payload: dict) -> dict:
        resp = self._session.put(f"{self._api_base}{path}", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()


def _new_client() -> DremioClient:
    """Stateless factory — creates and authenticates a fresh client per tool call."""
    return DremioClient(
        host=_pick_env("DREMIO_HOST", "DREMIO_URL", "dremio_url"),
        project_id=_pick_env("DREMIO_PROJECT_ID"),
        username=_pick_env("DREMIO_USERNAME", "dremio_username"),
        password=_pick_env("DREMIO_PASSWORD", "dremio_password"),
        pat=_pick_env("DREMIO_PAT", "DREMIO_TOKEN"),
    )


def _clean_path(path: str) -> str:
    """Normalise a catalog path: strip quotes, convert dots to slashes."""
    return path.replace('"', "").replace("'", "").replace(".", "/")


# ── LangChain tools ───────────────────────────────────────────────────────────

@tool
def execute_dremio_sql(sql: str, context: str = "") -> dict:
    """Execute a SQL query in Dremio and return results.

    Args:
        sql: SQL query to execute.
        context: Optional Dremio context path (e.g. 'amos_postgres.amos').

    Returns:
        Dict with status, job_id, schema, rows, and row_count.
    """
    try:
        client = _new_client()

        payload: dict[str, Any] = {"sql": sql}
        if context:
            payload["context"] = [p for p in context.split(".") if p]

        job = client.post("/sql", payload)
        job_id = job.get("id")
        if not job_id:
            return {"status": "FAILED", "error": "No job ID returned", "response": job}

        polls = _SQL_TIMEOUT_SECONDS // _JOB_POLL_INTERVAL
        for _ in range(polls):
            time.sleep(_JOB_POLL_INTERVAL)
            info = client.get(f"/job/{job_id}")
            state = info.get("jobState", "")
            if state == "COMPLETED":
                break
            if state in ("FAILED", "CANCELED", "INVALID_STATE"):
                return {
                    "status": "FAILED",
                    "job_id": job_id,
                    "job_state": state,
                    "error": info.get("errorMessage", "Job failed"),
                }
        else:
            return {"status": "FAILED", "error": "Query timed out", "job_id": job_id}

        results = client.get(f"/job/{job_id}/results?offset=0&limit={_DEFAULT_ROW_LIMIT}")
        return {
            "status": "SUCCESS",
            "job_id": job_id,
            "row_count": results.get("rowCount", 0),
            "schema": results.get("schema", []),
            "rows": results.get("rows", []),
        }
    except requests.HTTPError as e:
        return {"status": "FAILED", "error": f"HTTP {getattr(e.response, "status_code", "Unknown")}: {getattr(e.response, "text", str(e))}"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def validate_sql_query(sql: str) -> dict:
    """Validate SQL syntax and column references without executing the query.

    Uses ``EXPLAIN PLAN FOR`` — Dremio binds the query (checking syntax and that
    every referenced column resolves) but does NOT execute it or scan source data,
    so validation stays fast even against federated sources. (The previous
    ``SELECT * (...) LIMIT 0`` wrapper was not reliably short-circuited by Dremio
    and could time out running a full scan.)

    Args:
        sql: SQL to validate.

    Returns:
        Dict with status and message; on failure, the underlying error dict.
    """
    explain = f"EXPLAIN PLAN FOR\n{sql}"
    result = execute_dremio_sql.invoke({"sql": explain})  # type: ignore[attr-defined]
    if result["status"] == "SUCCESS":
        return {"status": "SUCCESS", "message": "Query is valid"}
    return result


@tool
def list_catalog_children(path: str) -> dict:
    """List all views, tables, and sub-folders inside a Dremio catalog folder or space.

    Use this to browse what exists under a given path.

    Args:
        path: Dot- or slash-separated path, quotes are stripped automatically.
              e.g. 'dremio-db.amos_training_status_report'
              or   '"dremio-db"."amos_training_status_report"'

    Returns:
        Dict with status, parent_path, count, and list of children (name, type, datasetType, path).
    """
    try:
        client = _new_client()
        url_path = _clean_path(path)
        item = client.get(f"/catalog/by-path/{url_path}")

        # Dremio Cloud returns children directly in the by-path response for folders
        raw_children = item.get("children", [])

        # Fallback: fetch by ID if no inline children
        if not raw_children:
            item_id = item.get("id")
            if item_id:
                detail = client.get(f"/catalog/{urllib.parse.quote(item_id, safe='')}")
                raw_children = detail.get("children", [])

        children = [
            {
                "name": c.get("path", [""])[-1],
                "type": c.get("type"),
                "datasetType": c.get("datasetType"),
                "path": ".".join(c.get("path", [])),
                "id": c.get("id"),
            }
            for c in raw_children
        ]
        return {
            "status": "SUCCESS",
            "parent_path": path,
            "count": len(children),
            "children": children,
        }
    except requests.HTTPError as e:
        return {"status": "FAILED", "error": f"HTTP {getattr(e.response, "status_code", "Unknown")}: {getattr(e.response, "text", str(e))}"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def get_catalog_item(path: str) -> dict:
    """Inspect metadata of a specific Dremio catalog item.

    Args:
        path: Dot- or slash-separated path, quotes are stripped automatically.

    Returns:
        Dict with status and full item metadata including children (if folder).
    """
    try:
        client = _new_client()
        url_path = _clean_path(path)
        item = client.get(f"/catalog/by-path/{url_path}")
        return {"status": "SUCCESS", "item": item}
    except requests.HTTPError as e:
        return {"status": "FAILED", "error": f"HTTP {getattr(e.response, "status_code", "Unknown")}: {getattr(e.response, "text", str(e))}"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def list_dremio_sources() -> dict:
    """List all top-level sources and spaces in the Dremio catalog.

    Returns:
        Dict with status, count, and list of catalog entries.
    """
    try:
        client = _new_client()
        result = client.get("/catalog")
        entries = [
            {
                "name": e.get("path", [""])[-1],
                "type": e.get("type"),
                "containerType": e.get("containerType"),
                "id": e.get("id"),
                "path": ".".join(e.get("path", [])),
            }
            for e in result.get("data", [])
        ]
        return {"status": "SUCCESS", "count": len(entries), "entries": entries}
    except requests.HTTPError as e:
        return {"status": "FAILED", "error": f"HTTP {getattr(e.response, "status_code", "Unknown")}: {getattr(e.response, "text", str(e))}"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def create_dremio_folder(space: str, folder_path: str) -> dict[str, Any]:
    """Create a single folder (or nested path) under a Dremio space/catalog.

    Walks the path top-down and creates each missing segment. Segments that
    already exist are silently skipped.

    Args:
        space: Top-level catalog name, e.g. "dremio-db".
        folder_path: Slash-separated folder path, e.g. "apu_health" or "engine/apu".

    Returns:
        dict with status ("SUCCESS" / "FAILED"), and on success:
          - created: list of folder path segments actually created
          - skipped: list of segments that already existed
    """
    client = _new_client()
    segments = [s for s in folder_path.split("/") if s]
    built: list[str] = [space]
    created: list[str] = []
    skipped: list[str] = []

    for seg in segments:
        built.append(seg)
        url_path = "/".join(urllib.parse.quote(p, safe="") for p in built)
        try:
            client.get(f"/catalog/by-path/{url_path}")
            skipped.append(".".join(built))
        except requests.HTTPError as e:
            if getattr(e.response, "status_code", "Unknown") != 404:
                return {
                    "status": "FAILED",
                    "error": f"Unexpected HTTP {getattr(e.response, "status_code", "Unknown")} checking {'.'.join(built)}: {getattr(e.response, "text", str(e))}",
                }
            # Folder does not exist — try Cloud format first, then on-prem v3
            # Dremio Cloud (v0): entityType must be lowercase "folder", no containerType
            # Dremio on-prem (v3): entityType "folder" also works; fallback adds containerType
            last_error = ""
            for payload in [
                {"entityType": "folder", "path": list(built)},
                {"entityType": "folder", "containerType": "FOLDER", "path": list(built)},
            ]:
                try:
                    client.post("/catalog", payload)
                    created.append(".".join(built))
                    last_error = ""
                    break
                except requests.HTTPError as ce:
                    last_error = f"HTTP {getattr(e.response, "status_code", "Unknown")}: {getattr(e.response, "text", str(e))}"
            if last_error:
                return {
                    "status": "FAILED",
                    "error": f"Could not create folder '{'.'.join(built)}': {last_error}",
                }

    return {"status": "SUCCESS", "created": created, "skipped": skipped}


def _ensure_folder(client: DremioClient, space: str, folder_path: str) -> dict:
    """Thin wrapper used by create_virtual_dataset to pre-create missing folders."""
    result = create_dremio_folder(space, folder_path)
    return result


@tool
def create_virtual_dataset(space: str, folder_path: str, vds_name: str, sql: str) -> dict:
    """Create a Virtual Dataset (VDS / View) in Dremio.

    Args:
        space: Dremio space name (e.g. 'dremio-db').
        folder_path: Slash-separated folder inside the space (e.g. 'AMOS/Training').
        vds_name: Name for the new VDS (e.g. 'staff_pqs_qualification_vds').
        sql: SQL query defining the VDS.

    Returns:
        Dict with status, vds_path, and vds_id.
    """
    try:
        client = _new_client()

        # Ensure every folder segment exists before creating the VDS
        folder_result = _ensure_folder(client, space, folder_path)
        if folder_result["status"] != "SUCCESS":
            return folder_result

        path_parts = [space] + [p for p in folder_path.split("/") if p] + [vds_name]
        # Dremio Cloud v0: sql and sqlContext are top-level fields, NOT nested in virtualDataset
        payload = {
            "entityType": "dataset",
            "type": "VIRTUAL_DATASET",
            "path": path_parts,
            "sql": sql,
            "sqlContext": [],
        }
        result = client.post("/catalog", payload)
        return {
            "status": "SUCCESS",
            "vds_path": ".".join(path_parts),
            "vds_id": result.get("id"),
            "details": result,
        }
    except requests.HTTPError as e:
        return {"status": "FAILED", "error": f"HTTP {getattr(e.response, "status_code", "Unknown")}: {getattr(e.response, "text", str(e))}"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def update_virtual_dataset(vds_id: str, sql: str) -> dict:
    """Update the SQL definition of an existing Virtual Dataset.

    Args:
        vds_id: Dremio catalog ID of the VDS to update.
        sql: New SQL definition.

    Returns:
        Dict with status and updated VDS details.
    """
    try:
        client = _new_client()
        encoded_id = urllib.parse.quote(vds_id, safe="")
        existing = client.get(f"/catalog/{encoded_id}")
        existing["virtualDataset"]["sql"] = sql
        result = client.put(f"/catalog/{encoded_id}", existing)
        return {"status": "SUCCESS", "vds_id": vds_id, "details": result}
    except requests.HTTPError as e:
        return {"status": "FAILED", "error": f"HTTP {getattr(e.response, "status_code", "Unknown")}: {getattr(e.response, "text", str(e))}"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def preview_dataset(path: str, row_limit: int = 20) -> dict:
    """Preview rows from a Dremio source table or VDS.

    Args:
        path: Dot-separated path (e.g. '"dremio-db"."amos_training_status_report"."amos_training_status_report"').
        row_limit: Rows to return (max 500).

    Returns:
        Dict with status, schema, and sample rows.
    """
    limit = min(row_limit, 500)
    sql = f'SELECT * FROM {path} LIMIT {limit}'
    return execute_dremio_sql.invoke({"sql": sql})  # type: ignore[attr-defined]


@tool
def search_catalog(keyword: str) -> dict:
    """Search the ASL data catalog for tables and columns matching a keyword.

    Always call this before writing SQL to confirm exact table names, column names,
    and data types. The catalog covers AMOS, HOC, Movement Manager, SAP, Xero,
    Master Files, MSSQL, and Tally sources.

    Args:
        keyword: Search term — a table name fragment, column name, or business concept
                 (e.g. 'aircraft', 'flight', 'employee', 'salary', 'invoice').

    Returns:
        Dict with status, keyword, count, and matches. Each match includes:
        table, source, domain, description, total_columns, and columns
        (list of {name, type, desc}).
    """
    try:
        from adl_automated_delivery_pipeline.tools.catalog_loader import search_tables
        matches = search_tables(keyword, max_results=15)
        return {
            "status": "SUCCESS",
            "keyword": keyword,
            "count": len(matches),
            "matches": matches,
        }
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}

