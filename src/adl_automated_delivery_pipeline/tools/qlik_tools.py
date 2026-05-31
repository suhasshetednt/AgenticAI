"""QlikSense Cloud tools for the LangGraph agent stack.

Data loading approach — INLINE:
  Python fetches all rows from Dremio (via Dremio REST API) and embeds them directly
  in the QlikSense LOAD script as INLINE data.  This is the only approach that reliably
  loads data in QlikSense Cloud SaaS without a Qlik Data Gateway, because the QlikSense
  cloud reload engine cannot reach Dremio's REST API even when a REST data connection is
  registered (DoReload succeeds but loads nothing — the connection fails silently).

  To refresh the dashboard with new Dremio data, call refresh_apu_dashboard — it
  re-fetches from Dremio, rebuilds the INLINE script, and triggers a reload.

QlikSense APIs used:
  Engine API  wss://{tenant}/app/{appId}   — script + object creation
  REST API    https://{tenant}/api/v1/     — app, space, reload management
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any
import time
import uuid
from typing import Any

import requests
import websocket
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── Column mapping: Dremio source field → QlikSense display label ─────────────
_APU_FIELD_MAP: dict[str, str] = {
    "partno":         "APU P/n",
    "serialno":       "APU S/n",
    "psn":            "PSN",
    "ac_registr":     "Aircraft Reg.",
    "ref_date":       "Reference Date",
    "trend_type":     "Trend Type",
    "event_perfno_i": "Workorder",
    "value":          "CT5ATP value",   # 'value' is a Dremio reserved word — quoted in SQL
    "ac_typ":         "Aircraft Type",
}

_NUMERIC_FIELDS: frozenset[str] = frozenset({"value"})   # loaded with Num() in script

_DREMIO_PAGE_SIZE = 500   # Dremio Cloud hard cap per results page

_DREMIO_PAGE_SIZE = 500   # Dremio Cloud hard cap per results page


# ── Config helpers ────────────────────────────────────────────────────────────

def _pick_env(*names: str) -> str:
    for name in names:
        val = os.getenv(name, "").strip()
        if val:
            return val
    return ""


def _tenant() -> str:
    """'https://foo.eu.qlikcloud.com/path' → 'foo.eu.qlikcloud.com'"""
    raw = _pick_env("QLIK_TENANT")
    return raw.split("//")[-1].split("/")[0]


def _api_key() -> str:
    return _pick_env("QLIK_API_KEY")


def _default_space() -> str:
    return _pick_env("QLIK_SPACE") or "personal"


def _dremio_base_url() -> str:
    return _pick_env("dremio_url").rstrip("/")


def _dremio_token() -> str:
    return _pick_env("DREMIO_TOKEN")


# ── Dremio data fetch ─────────────────────────────────────────────────────────

def _fetch_dremio_rows(sql: str, max_rows: int = 5000) -> list[dict]:
    """Execute SQL on Dremio Cloud and return all rows (paginated)."""
    from adl_automated_delivery_pipeline.tools.dremio_tools import _new_client, _JOB_POLL_INTERVAL, _SQL_TIMEOUT_SECONDS

    client = _new_client()
    job    = client.post("/sql", {"sql": sql})
    job_id = job.get("id")
    if not job_id:
        raise RuntimeError(f"No job ID returned from Dremio: {job}")

    for _ in range(_SQL_TIMEOUT_SECONDS // _JOB_POLL_INTERVAL):
        time.sleep(_JOB_POLL_INTERVAL)
        info  = client.get(f"/job/{job_id}")
        state = info.get("jobState", "")
        if state == "COMPLETED":
            logger.info("Dremio job %s complete — %d rows", job_id, info.get("rowCount", 0))
            break
        if state in ("FAILED", "CANCELED", "INVALID_STATE"):
            raise RuntimeError(f"Dremio job {state}: {info.get('errorMessage', '')}")
    else:
        raise RuntimeError("Dremio query timed out")

    all_rows: list[dict] = []
    offset = 0
    while len(all_rows) < max_rows:
        limit = min(_DREMIO_PAGE_SIZE, max_rows - len(all_rows))
        page  = client.get(f"/job/{job_id}/results?offset={offset}&limit={limit}")
        rows  = page.get("rows", [])
        all_rows.extend(rows)
        if len(rows) < limit:
            break
        offset += limit
    return all_rows


# ── QlikSense REST helpers ────────────────────────────────────────────────────

def _rest_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}


def _rest(method: str, path: str, **kwargs: Any) -> requests.Response:
    url  = f"https://{_tenant()}/api/v1{path}"
    resp = requests.request(method, url, headers=_rest_headers(), timeout=30, **kwargs)
    resp.raise_for_status()
    return resp


def _rest_get(path: str) -> dict:
    return _rest("GET", path).json()


def _rest_post(path: str, payload: dict) -> dict:
    return _rest("POST", path, json=payload).json()


def _rest_patch(path: str, payload: dict) -> dict:
    return _rest("PATCH", path, json=payload).json()


# ── Engine API (WebSocket JSON-RPC) ───────────────────────────────────────────

class _Engine:
    """JSON-RPC WebSocket session for a specific QlikSense Cloud app."""

    def __init__(self, app_id: str, timeout: int = 60) -> None:
        url      = f"wss://{_tenant()}/app/{app_id}"
        self._ws = websocket.create_connection(
            url,
            header={"Authorization": f"Bearer {_api_key()}"},
            timeout=timeout,
        )
        self._seq = 0
        # Drain the OnConnected notification that QlikSense Cloud sends on open
        self._ws.settimeout(3)
        try:
            while True:
                raw = self._ws.recv()
                if not raw:
                    break
                if json.loads(raw).get("method") == "OnConnected":
                    break
        except Exception:
            pass
        self._ws.settimeout(timeout)

    def rpc(self, handle: int, method: str, params: list | None = None) -> dict:
        self._seq += 1
        self._ws.send(json.dumps({
            "jsonrpc": "2.0", "id": self._seq,
            "handle": handle, "method": method,
            "params": params or [],
        }))
        while True:
            raw = self._ws.recv()
            if not raw:
                continue
            msg = json.loads(raw)
            if msg.get("id") == self._seq:
                if "error" in msg:
                    raise RuntimeError(f"Engine [{method}]: {msg['error']}")
                return msg.get("result", {})

    def open_doc(self, app_id: str) -> int:
        return self.rpc(-1, "OpenDoc", [app_id])["qReturn"]["qHandle"]

    def set_script(self, app_h: int, script: str) -> None:
        self.rpc(app_h, "SetScript", [script])

    def do_reload(self, app_h: int) -> None:
        self.rpc(app_h, "DoReload")

    def create_object(self, app_h: int, props: dict) -> tuple[int, str]:
        r = self.rpc(app_h, "CreateObject", [props])
        return r["qReturn"]["qHandle"], props["qInfo"].get("qId", "")

    def publish_object(self, handle: int, label: str = "") -> None:
        """Promote private → community so the object is included in managed-space publish."""
        try:
            self.rpc(handle, "Publish", [])
            logger.info("Promoted %s (handle %d) to community", label or "object", handle)
        except Exception as exc:
            logger.warning("Publish(%s) skipped: %s", label or handle, exc)

    def save(self, app_h: int) -> None:
        self.rpc(app_h, "DoSave")

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass


# ── App / space helpers ───────────────────────────────────────────────────────

def _create_qlik_app(name: str) -> str:
    resp   = _rest_post("/apps", {"attributes": {"name": name}})
    app_id = resp.get("attributes", {}).get("id") or resp.get("id", "")
    if not app_id:
        raise RuntimeError(f"Could not create QlikSense app. Response: {resp}")
    return app_id


def _find_space(name: str) -> tuple[str, str]:
    """Return (space_id, space_type). Both empty strings for personal space."""
    if not name or name.lower() == "personal":
        return "", ""
    data = _rest_get("/spaces?limit=100").get("data", [])
    for s in data:
        if s.get("name", "").lower() == name.lower():
            return s["id"], s.get("type", "shared")
    raise ValueError(f"Space '{name}' not found. Available: {[s['name'] for s in data]}")


def _publish_app_to_space(app_id: str, space_id: str, app_name: str) -> str:
    """Publish personal app to managed space. Returns the published app ID."""
    pub = _rest_post(f"/apps/{app_id}/publish", {"spaceId": space_id, "targetName": app_name})
    return pub.get("attributes", {}).get("id") or pub.get("id", app_id)


def _move_app_to_shared_space(app_id: str, space_id: str) -> None:
    items = _rest_get(f"/items?resourceType=app&resourceId={app_id}&limit=5").get("data", [])
    if items:
        _rest_patch(f"/items/{items[0]['id']}", {"spaceId": space_id})


# ── REST reload (async + poll) ────────────────────────────────────────────────

def _rest_reload(app_id: str, timeout: int = 180) -> dict:
    resp      = _rest_post("/reloads", {"appId": app_id})
    reload_id = resp.get("id", "")
    if not reload_id:
        return {"status": "FAILED", "error": f"No reload ID: {resp}"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(4)
        r     = _rest_get(f"/reloads/{reload_id}")
        state = r.get("status", "")
        if state == "SUCCEEDED":
            return {"status": "SUCCESS"}
        if state in ("FAILED", "ABORTED"):
            return {"status": "FAILED", "error": f"Reload {state}: {r.get('log', '')}"}
    return {"status": "FAILED", "error": "Reload timed out"}


# ── INLINE load script builder ────────────────────────────────────────────────

def _build_inline_script(rows: list[dict], vds_path: str) -> str:
    """Build a QlikSense LOAD ... INLINE script from Dremio result rows.

    Data is embedded directly in the script so the QlikSense reload engine
    does not need to reach any external service — the most reliable approach
    for QlikSense Cloud SaaS without a Qlik Data Gateway.
    """
    src_fields    = list(_APU_FIELD_MAP.keys())
    display_names = list(_APU_FIELD_MAP.values())

    def _esc(v: Any) -> str:
        if v is None:
            return ""
        return str(v).replace('"', '""')

    # Header row + data rows for the INLINE block
    header    = ", ".join(f'"{n}"' for n in display_names)
    data_rows = [
        ", ".join(f'"{_esc(row.get(f, ""))}"' for f in src_fields)
        for row in rows
    ]
    inline_body = "\n".join([header] + data_rows)

    # LOAD field list — CT5ATP value is numeric, everything else is a string dimension
    load_fields = []
    for src, display in _APU_FIELD_MAP.items():
        if src in _NUMERIC_FIELDS:
            load_fields.append(f'  Num("{display}") AS "{display}"')
        else:
            load_fields.append(f'  "{display}"')
    load_field_str = ",\n".join(load_fields)

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return (
        f"// APU Health Monitor — data fetched from Dremio by adl_automated_delivery_pipeline\n"
        f"// VDS  : {vds_path}\n"
        f"// Rows : {len(rows)}\n"
        f"// Built: {ts}\n\n"
        f"APU_Health:\n"
        f"LOAD\n"
        f"{load_field_str}\n"
        f"INLINE [\n"
        f"{inline_body}\n"
        f"];\n"
    )


# ── Table visualization builder ───────────────────────────────────────────────

def _table_props(q_id: str, amber_th: int = 630, red_th: int = 660) -> dict:
    """Engine API CreateObject props for the APU Health straight table (9 columns)."""

    def _dim(label: str) -> dict:
        return {"qDef": {"qFieldDefs": [label], "qLabel": label}, "qNullSuppression": False}

    def _dim_colored(label: str) -> dict:
        return {
            "qDef": {"qFieldDefs": [label], "qLabel": label},
            "qNullSuppression": False,
            "qAttributeExpressions": [
                {
                    "qExpression": (
                        f"=If([CT5ATP value]>={red_th},RGB(220,53,69),"
                        f"If([CT5ATP value]>={amber_th},RGB(255,193,7),ARGB(0,0,0,0)))"
                    ),
                    "id": "cellBackgroundColor",
                },
                {
                    "qExpression": (
                        f"=If([CT5ATP value]>={red_th},RGB(255,255,255),"
                        f"If([CT5ATP value]>={amber_th},RGB(0,0,0),RGB(0,0,0)))"
                    ),
                    "id": "cellForegroundColor",
                },
            ],
        }

    return {
        "qInfo":         {"qId": q_id, "qType": "sn-table"},
        "visualization": "sn-table",
        "showTitles":    True,
        "title":         "APU Health Monitor",
        "qHyperCubeDef": {
            "qDimensions": [
                _dim("APU P/n"),
                _dim("APU S/n"),
                _dim("PSN"),
                _dim("Aircraft Reg."),
                _dim("Reference Date"),
                _dim("Trend Type"),
                _dim("Workorder"),
                _dim_colored("CT5ATP value"),
                _dim("Aircraft Type"),
            ],
            "qMeasures":        [],
            "qSuppressMissing": True,
            "qInitialDataFetch": [{"qTop": 0, "qLeft": 0, "qHeight": 100, "qWidth": 9}],
        },
    }


# ── LangChain tools ───────────────────────────────────────────────────────────

@tool
def list_qlik_spaces() -> dict:
    """List all QlikSense Cloud spaces.

    Returns:
        Dict with status, count, spaces list (id, name, type).
    """
    try:
        data = _rest_get("/spaces?limit=100").get("data", [])
        return {
            "status": "SUCCESS",
            "count":  len(data),
            "spaces": [{"id": s["id"], "name": s["name"], "type": s["type"]} for s in data],
        }
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def list_qlik_apps(space_name: str = "") -> dict:
    """List QlikSense apps, optionally filtered to a named space.

    Args:
        space_name: Space name to filter by. Empty = all apps.

    Returns:
        Dict with status, count, apps list (id, name, space).
    """
    try:
        items = _rest_get("/items?resourceType=app&limit=100").get("data", [])
        apps  = [{"id": i["resourceId"], "name": i["name"], "space": i.get("spaceId", "personal")}
                 for i in items]
        return {"status": "SUCCESS", "count": len(apps), "apps": apps}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def create_apu_health_dashboard(
    vds_path:        str,
    app_name:        str = "APU Health Monitor",
    space_name:      str = "",
    amber_threshold: int = 630,
    red_threshold:   int = 660,
) -> dict:
    """Build an APU Health Monitor dashboard in QlikSense Cloud from a Dremio VDS.

    Flow:
      1. Fetch all rows from the Dremio VDS via the Dremio REST API.
      2. Embed data directly in the QlikSense LOAD script as INLINE data.
      3. Create the app, set the script, reload, build the 9-column table sheet.
      4. Promote sheet objects to community and publish to the target space.

    Columns: APU P/n | APU S/n | PSN | Aircraft Reg. | Reference Date |
             Trend Type | Workorder | CT5ATP value | Aircraft Type
    CT5ATP colour rules: no colour < amber_threshold | Amber >= amber_threshold | Red >= red_threshold

    Args:
        vds_path:   Dot-separated Dremio VDS path, e.g. 'dremio-db.apu_health.apu_health'.
        app_name:   Name for the QlikSense app.
        space_name: Target space, e.g. 'development'. Empty = personal space.

    Returns:
        Dict with status, app_id, app_url, rows_loaded.
    """
    try:
        space = space_name or _default_space()

        # ── Resolve space ──────────────────────────────────────────────────────
        space_id, space_type = _find_space(space)

        # ── 1. Fetch data from Dremio ──────────────────────────────────────────
        parts  = vds_path.split(".")
        quoted = ".".join(f'"{p}"' for p in parts)
        sql    = (
            f'SELECT partno, serialno, psn, ac_registr, ref_date, '
            f'trend_type, event_perfno_i, "value", ac_typ FROM {quoted}'
        )
        logger.info("Fetching Dremio rows for: %s", vds_path)
        rows = _fetch_dremio_rows(sql, max_rows=5000)
        if not rows:
            return {"status": "FAILED", "error": "Dremio VDS returned 0 rows"}
        logger.info("Fetched %d rows from Dremio", len(rows))

        # ── 2. Build INLINE load script ────────────────────────────────────────
        script = _build_inline_script(rows, vds_path)

        # ── 3. Create app, set script, reload ─────────────────────────────────
        app_id = _create_qlik_app(app_name)
        logger.info("Created personal app: %s", app_id)

        if space_id and space_type != "managed":
            _move_app_to_shared_space(app_id, space_id)

        eng = _Engine(app_id, timeout=120)
        try:
            app_h = eng.open_doc(app_id)
            eng.set_script(app_h, script)
            logger.info("Script set — reloading ...")
            try:
                eng.do_reload(app_h)
            except Exception as exc:
                logger.warning("Engine DoReload failed (%s); falling back to REST reload", exc)
                eng.save(app_h)
                eng.close()
                r = _rest_reload(app_id)
                if r["status"] != "SUCCESS":
                    return {**r, "app_id": app_id}
                eng   = _Engine(app_id, timeout=120)
                app_h = eng.open_doc(app_id)

            # ── 4. Create sheet + table ────────────────────────────────────────
            tbl_id   = f"tbl_{uuid.uuid4().hex[:8]}"
            sheet_id = f"sh_{uuid.uuid4().hex[:8]}"

            tbl_h, _   = eng.create_object(app_h, _table_props(tbl_id, amber_threshold, red_threshold))
            sheet_h, _ = eng.create_object(app_h, {
                "qInfo":    {"qId": sheet_id, "qType": "sheet"},
                "qMetaDef": {"title": "APU Health Monitor"},
                "rank":     0,
                "cells":    [{"name": tbl_id, "type": "sn-table",
                               "col": 0, "row": 0, "colspan": 24, "rowspan": 12}],
                "columns":  24,
                "rows":     12,
            })

            # Promote private → community (community objects are included in managed publish)
            eng.publish_object(tbl_h,   "table")
            eng.publish_object(sheet_h, "sheet")
            eng.save(app_h)
            logger.info("Sheet and table created and promoted to community")
        finally:
            eng.close()

        # ── 5. Publish to managed space ────────────────────────────────────────
        pub_app_id = app_id
        if space_id and space_type == "managed":
            logger.info("Publishing to managed space '%s' ...", space)
            pub_app_id = _publish_app_to_space(app_id, space_id, app_name)
            logger.info("Published app ID: %s", pub_app_id)

        app_url = f"https://{_tenant()}/sense/app/{pub_app_id}/sheet/{sheet_id}"
        return {
            "status":      "SUCCESS",
            "app_id":      pub_app_id,
            "app_name":    app_name,
            "space":       space,
            "rows_loaded": len(rows),
            "sheet_id":    sheet_id,
            "app_url":     app_url,
        }

    except requests.HTTPError as e:
        return {"status": "FAILED", "error": f"HTTP {getattr(e.response, "status_code", "Unknown")}: {getattr(e.response, "text", str(e))}"}
    except Exception as e:
        logger.exception("create_apu_health_dashboard failed")
        return {"status": "FAILED", "error": str(e)}


@tool
def refresh_apu_dashboard(app_id: str, vds_path: str = "dremio-db.apu_health.apu_health") -> dict:
    """Refresh an existing APU Health dashboard with the latest data from Dremio.

    Re-fetches all rows from Dremio, rebuilds the INLINE load script, and
    triggers a reload so the dashboard reflects the freshest data.

    Args:
        app_id:   QlikSense app ID to refresh.
        vds_path: Dremio VDS path (dot-separated).

    Returns:
        Dict with status, rows_loaded.
    """
    try:
        parts  = vds_path.split(".")
        quoted = ".".join(f'"{p}"' for p in parts)
        sql    = (
            f'SELECT partno, serialno, psn, ac_registr, ref_date, '
            f'trend_type, event_perfno_i, "value", ac_typ FROM {quoted}'
        )
        rows   = _fetch_dremio_rows(sql, max_rows=5000)
        script = _build_inline_script(rows, vds_path)

        eng = _Engine(app_id, timeout=120)
        try:
            app_h = eng.open_doc(app_id)
            eng.set_script(app_h, script)
            try:
                eng.do_reload(app_h)
            except Exception as exc:
                logger.warning("Engine DoReload failed (%s); using REST reload", exc)
                eng.save(app_h)
                eng.close()
                r = _rest_reload(app_id)
                return {**r, "rows_loaded": len(rows)}
            eng.save(app_h)
        finally:
            eng.close()

        return {"status": "SUCCESS", "rows_loaded": len(rows)}

    except requests.HTTPError as e:
        return {"status": "FAILED", "error": f"HTTP {getattr(e.response, "status_code", "Unknown")}: {getattr(e.response, "text", str(e))}"}
    except Exception as e:
        logger.exception("refresh_apu_dashboard failed")
        return {"status": "FAILED", "error": str(e)}
