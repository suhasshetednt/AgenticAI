# Live Pipeline Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A browser dashboard that runs the ADL pipeline by ticket key (or browse) and shows it executing live — a vertical stage timeline, per-stage logs, Approve/Reject gates, and artifact links.

**Architecture:** Keep `api/app.py`'s websocket print/input bridge. The pipeline emits a few **stable sentinel markers** (`::STAGE::`/`::ARTIFACT::`/`::APPROVE::`/`::DONE::`) on stdout; a new `run_ticket(key)` runner reuses the existing phase functions and wraps them with markers; a dependency-free `docs/pipeline_dashboard.html` parses the markers (via a testable `dashboard_parser.js`) and renders the timeline.

**Tech Stack:** Python 3.11 (FastAPI, existing websocket bridge), vanilla HTML/CSS/JS, Node (for the parser unit test only), pytest (`-m unit`).

**Spec:** `docs/superpowers/specs/2026-06-06-live-pipeline-dashboard-design.md`

**Conventions:** `workflows/` is the CLI layer where `print()` IS the contract (the bridge); the sentinel emitter lives there. Full type annotations; specific exceptions; `from __future__ import annotations`; tests `@pytest.mark.unit`. Run tests with the parent venv `E:\LLM\Claude\.venv\Scripts\python.exe`; run the JS test with `node`. Git on branch `feature/live-pipeline-dashboard` (already created); commit via `git -C E:\LLM\Claude\adl_automated_delivery_pipeline`.

---

## File Structure

**Create:**
- `src/adl_automated_delivery_pipeline/workflows/_events.py` — sentinel marker emitter
- `docs/dashboard_parser.js` — pure `parseMarker(line)` (browser + node)
- `docs/pipeline_dashboard.html` — the dashboard UI (HTML/CSS/JS)
- `tests/test_dashboard_events.py` — emitter unit tests
- `tests/test_run_ticket.py` — `run_ticket` order/markers unit tests
- `tests/test_dashboard_api.py` — `_resolve_start` + `GET /` tests
- `tests/test_dashboard_parser.cjs` — node assertions for `parseMarker`

**Modify:**
- `src/adl_automated_delivery_pipeline/workflows/adl_automated_delivery_pipeline.py` — make `_doc_phase` return its path; add `run_ticket(...)`
- `src/adl_automated_delivery_pipeline/api/app.py` — `_resolve_start`, parameterized `run_pipeline(payload)`, JSON start message, serve the new dashboard

---

## Task 1: Sentinel marker emitter

**Files:**
- Create: `src/adl_automated_delivery_pipeline/workflows/_events.py`
- Test: `tests/test_dashboard_events.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_events.py`:

```python
"""Unit tests for the dashboard sentinel emitter."""

from __future__ import annotations

import pytest

from adl_automated_delivery_pipeline.workflows import _events as ev


@pytest.mark.unit
def test_markers_have_exact_format(capsys: pytest.CaptureFixture[str]) -> None:
    ev.stage("dremio", "start")
    ev.artifact("vds", "dremio-db.occ.aslb_business")
    ev.approve("dremio", "ADL-1729: carrier codes")
    ev.done()
    out = capsys.readouterr().out.splitlines()
    assert out == [
        "::STAGE dremio start::",
        "::ARTIFACT vds=dremio-db.occ.aslb_business::",
        "::APPROVE dremio=ADL-1729: carrier codes::",
        "::DONE::",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `E:\LLM\Claude\.venv\Scripts\python.exe -m pytest tests/test_dashboard_events.py -v`
Expected: FAIL — `ModuleNotFoundError: ..._events`.

- [ ] **Step 3: Write minimal implementation**

Create `src/adl_automated_delivery_pipeline/workflows/_events.py`:

```python
"""Sentinel markers for the live dashboard.

These print one machine-readable line each on stdout, so they ride the existing
websocket log bridge in ``api/app.py``. The browser dashboard parses them to
drive the stage timeline, artifact chips, and approval cards. ``print`` is the
intended contract here (this is the CLI/bridge layer), so it is not a logging
violation.
"""

from __future__ import annotations


def stage(name: str, status: str) -> None:
    """Emit a stage status marker. status is one of: start, done, fail."""
    print(f"::STAGE {name} {status}::")


def artifact(kind: str, value: str) -> None:
    """Emit a produced-artifact marker. kind: docx, sql, vds, qlik."""
    print(f"::ARTIFACT {kind}={value}::")


def approve(kind: str, detail: str) -> None:
    """Emit an approval-needed marker. kind: dremio, qlik."""
    print(f"::APPROVE {kind}={detail}::")


def done() -> None:
    """Emit the run-finished marker."""
    print("::DONE::")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `E:\LLM\Claude\.venv\Scripts\python.exe -m pytest tests/test_dashboard_events.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C E:\LLM\Claude\adl_automated_delivery_pipeline add src/adl_automated_delivery_pipeline/workflows/_events.py tests/test_dashboard_events.py
git -C E:\LLM\Claude\adl_automated_delivery_pipeline commit -m "feat(dashboard): sentinel marker emitter"
```

---

## Task 2: `_doc_phase` returns its document path

**Files:**
- Modify: `src/adl_automated_delivery_pipeline/workflows/adl_automated_delivery_pipeline.py:884-899`
- Test: `tests/test_run_ticket.py` (created here; extended in Task 3)

This is the only behavioral change to an existing phase: return the saved `.docx`
Path so `run_ticket` can emit an artifact marker. The CLI `main()` ignores the
return value, so its behavior is unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_ticket.py`:

```python
"""Unit tests for _doc_phase return value and run_ticket orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

import adl_automated_delivery_pipeline.workflows.adl_automated_delivery_pipeline as wf


@pytest.mark.unit
def test_doc_phase_returns_saved_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeAgent:
        def generate(self, reqs, *a, **k):  # noqa: ANN001
            return Path("X:/Project Documentation/ADL-1.docx")

    monkeypatch.setattr(wf, "DocumentationAgent", _FakeAgent)
    reqs = wf.TicketRequirements(
        ticket_id="ADL-1", summary="s", business_requirement="b",
        source_database="occ", source_tables=[], output_fields=[],
        transformations=[], filter_conditions=[], acceptance_criteria=[],
    )
    assert wf._doc_phase(reqs) == Path("X:/Project Documentation/ADL-1.docx")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `E:\LLM\Claude\.venv\Scripts\python.exe -m pytest tests/test_run_ticket.py::test_doc_phase_returns_saved_path -v`
Expected: FAIL — `_doc_phase` returns `None`.

- [ ] **Step 3: Modify `_doc_phase`**

In `src/adl_automated_delivery_pipeline/workflows/adl_automated_delivery_pipeline.py`, replace the function body (lines 884-899) with this version (signature now returns `Path | None`; on success returns `path`, on failure returns `None`):

```python
def _doc_phase(reqs: TicketRequirements) -> "Path | None":
    """Phase 2: Run DocumentationAgent to produce a Technical Implementation Document.

    Returns the saved .docx Path on success, or None if generation failed.
    """
    _header("DOCUMENTATION AGENT  —  Technical Implementation Document")
    print("  Generating Technical Implementation Document from ticket requirements ...")
    print("  (This calls the configured LLM — may take 15–30 seconds)\n")
    try:
        agent = DocumentationAgent()
        path = agent.generate(reqs)
        print(f"\n  Document saved: {path}")
        print("  Open it in Word for review and sign-off.\n")
        return path
    except RuntimeError as exc:
        print(f"\n  WARNING: Documentation generation failed: {exc}")
        print("  Continuing to Dremio Agent ...\n")
        return None
    except Exception as exc:
        print(f"\n  WARNING: Unexpected error during documentation: {exc}")
        print("  Continuing to Dremio Agent ...\n")
        return None
```

`Path` is already imported at the top of this module (used elsewhere). No other change.

- [ ] **Step 4: Run test to verify it passes**

Run: `E:\LLM\Claude\.venv\Scripts\python.exe -m pytest tests/test_run_ticket.py::test_doc_phase_returns_saved_path -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C E:\LLM\Claude\adl_automated_delivery_pipeline add src/adl_automated_delivery_pipeline/workflows/adl_automated_delivery_pipeline.py tests/test_run_ticket.py
git -C E:\LLM\Claude\adl_automated_delivery_pipeline commit -m "feat(dashboard): _doc_phase returns saved docx path"
```

---

## Task 3: `run_ticket` orchestrator

**Files:**
- Modify: `src/adl_automated_delivery_pipeline/workflows/adl_automated_delivery_pipeline.py` (add `run_ticket` near `main`)
- Test: `tests/test_run_ticket.py` (extend)

- [ ] **Step 1: Write the failing test (append)**

Append to `tests/test_run_ticket.py`:

```python
@pytest.mark.unit
def test_run_ticket_happy_path_emits_markers_in_order(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reqs = wf.TicketRequirements(
        ticket_id="ADL-1", summary="s", business_requirement="b",
        source_database="occ", source_tables=[], output_fields=[],
        transformations=[], filter_conditions=[], acceptance_criteria=[],
    )
    monkeypatch.setattr(wf, "_fetch_ticket", lambda key: {"status": "SUCCESS", "id": key})
    monkeypatch.setattr(wf, "_extract_requirements", lambda ticket: reqs)
    monkeypatch.setattr(wf, "_display_requirements", lambda r: None)
    monkeypatch.setattr(wf, "_doc_phase", lambda r: Path("Project Documentation/ADL-1.docx"))
    monkeypatch.setattr(wf, "_dremio_phase", lambda r: "dremio-db.occ.aslb_business")
    monkeypatch.setattr(wf, "_qlik_phase", lambda r, v: None)
    answers = iter(["y", "y"])  # approve dremio, approve qlik
    monkeypatch.setattr(wf, "_inp", lambda *a, **k: next(answers))

    wf.run_ticket("ADL-1")

    markers = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert markers == [
        "::STAGE jira start::", "::STAGE jira done::",
        "::STAGE reqs start::", "::STAGE reqs done::",
        "::STAGE doc start::",
        "::ARTIFACT docx=Project Documentation/ADL-1.docx::",
        "::STAGE doc done::",
        "::APPROVE dremio=ADL-1: s::",
        "::STAGE dremio start::",
        "::ARTIFACT vds=dremio-db.occ.aslb_business::",
        "::STAGE dremio done::",
        "::APPROVE qlik=dremio-db.occ.aslb_business::",
        "::STAGE qlik start::", "::STAGE qlik done::",
        "::DONE::",
    ]


@pytest.mark.unit
def test_run_ticket_reject_dremio_stops(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reqs = wf.TicketRequirements(
        ticket_id="ADL-1", summary="s", business_requirement="b",
        source_database="occ", source_tables=[], output_fields=[],
        transformations=[], filter_conditions=[], acceptance_criteria=[],
    )
    monkeypatch.setattr(wf, "_fetch_ticket", lambda key: {"status": "SUCCESS", "id": key})
    monkeypatch.setattr(wf, "_extract_requirements", lambda ticket: reqs)
    monkeypatch.setattr(wf, "_display_requirements", lambda r: None)
    monkeypatch.setattr(wf, "_doc_phase", lambda r: Path("d.docx"))
    monkeypatch.setattr(wf, "_dremio_phase", lambda r: (_ for _ in ()).throw(AssertionError("dremio ran")))
    monkeypatch.setattr(wf, "_inp", lambda *a, **k: "n")  # reject dremio

    wf.run_ticket("ADL-1")

    markers = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert "::STAGE dremio start::" not in markers
    assert markers[-1] == "::DONE::"


@pytest.mark.unit
def test_run_ticket_jira_fail_stops(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(wf, "_fetch_ticket", lambda key: {"status": "FAILED", "error": "nope"})
    wf.run_ticket("ADL-X")
    markers = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert markers == ["::STAGE jira start::", "::STAGE jira fail::", "::DONE::"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `E:\LLM\Claude\.venv\Scripts\python.exe -m pytest tests/test_run_ticket.py -k run_ticket -v`
Expected: FAIL — `run_ticket` does not exist.

- [ ] **Step 3: Add `run_ticket`**

In `src/adl_automated_delivery_pipeline/workflows/adl_automated_delivery_pipeline.py`, add this function immediately above `def main()` (around line 1903). Add the import of `_events` at the top of the file with the other imports (`from adl_automated_delivery_pipeline.workflows import _events as ev`):

```python
def run_ticket(key: str, start_at: str = "jira") -> None:
    """Headless dashboard runner: execute the full pipeline for one ticket key,
    emitting sentinel markers around each phase. v1 always starts at "jira";
    ``start_at`` is accepted for a future resume feature but only "jira" runs.
    """
    ev.stage("jira", "start")
    ticket = _fetch_ticket(key)
    if ticket.get("status") != "SUCCESS":
        print(f"  ERROR fetching {key}: {ticket.get('error')}")
        ev.stage("jira", "fail")
        ev.done()
        return
    ev.stage("jira", "done")

    ev.stage("reqs", "start")
    reqs = _extract_requirements(ticket)
    if reqs is None:
        print("  Could not extract requirements.")
        ev.stage("reqs", "fail")
        ev.done()
        return
    _display_requirements(reqs)
    ev.stage("reqs", "done")

    ev.stage("doc", "start")
    doc_path = _doc_phase(reqs)
    if doc_path is not None:
        ev.artifact("docx", str(doc_path))
    ev.stage("doc", "done")

    ev.approve("dremio", f"{reqs.ticket_id}: {reqs.summary}")
    if _inp("Approve Dremio Agent (create/modify VDS)? [y/n]: ", required=False).lower() not in (
        "y", "yes", "1",
    ):
        print("  Stopped before Dremio.")
        ev.done()
        return

    ev.stage("dremio", "start")
    vds_path = _dremio_phase(reqs)
    if vds_path:
        ev.artifact("vds", vds_path)
        ev.stage("dremio", "done")
    else:
        ev.stage("dremio", "fail")
        ev.done()
        return

    ev.approve("qlik", vds_path)
    if _inp("Build QlikSense dashboard from this VDS? [y/n]: ", required=False).lower() in (
        "y", "yes", "1",
    ):
        ev.stage("qlik", "start")
        _qlik_phase(reqs, vds_path)
        ev.stage("qlik", "done")

    ev.done()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `E:\LLM\Claude\.venv\Scripts\python.exe -m pytest tests/test_run_ticket.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git -C E:\LLM\Claude\adl_automated_delivery_pipeline add src/adl_automated_delivery_pipeline/workflows/adl_automated_delivery_pipeline.py tests/test_run_ticket.py
git -C E:\LLM\Claude\adl_automated_delivery_pipeline commit -m "feat(dashboard): run_ticket headless runner with markers"
```

---

## Task 4: `api/app.py` — typed start message + serve the dashboard

**Files:**
- Modify: `src/adl_automated_delivery_pipeline/api/app.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_api.py`:

```python
"""Unit tests for the dashboard API: start-payload resolution and GET /."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from adl_automated_delivery_pipeline.api.app import app, _resolve_start


@pytest.mark.unit
def test_resolve_start_ticket_browse_and_default() -> None:
    assert _resolve_start({"mode": "ticket", "key": "ADL-1"}) == ("ticket", "ADL-1")
    assert _resolve_start({"mode": "browse"}) == ("browse", None)
    assert _resolve_start({}) == ("browse", None)


@pytest.mark.unit
def test_root_serves_html() -> None:
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `E:\LLM\Claude\.venv\Scripts\python.exe -m pytest tests/test_dashboard_api.py -v`
Expected: FAIL — `_resolve_start` not importable.

- [ ] **Step 3: Edit `api/app.py`**

(a) Add `import json` near the top imports (after `import asyncio`).

(b) Add this helper above `run_pipeline` (after the `ws_io = WebSocketIO()` line):

```python
def _resolve_start(payload: dict) -> tuple[str, str | None]:
    """Map a start payload to (mode, key). mode is 'ticket' or 'browse'."""
    if payload.get("mode") == "ticket":
        return ("ticket", payload.get("key"))
    return ("browse", None)
```

(c) Replace `def run_pipeline():` (lines 131-149) with a payload-aware version:

```python
def run_pipeline(payload: dict) -> None:
    """Runs the pipeline in a background thread. payload selects ticket vs browse."""
    module_dir = Path(__file__).resolve().parent.parent.parent  # project root
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    ws_io.enable()
    try:
        mode, key = _resolve_start(payload)
        from adl_automated_delivery_pipeline.workflows.adl_automated_delivery_pipeline import (
            main,
            run_ticket,
        )
        if mode == "ticket" and key:
            run_ticket(key)
        else:
            main()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        output_queue.put({"type": "error", "message": f"Pipeline crashed: {str(e)}\n{tb}"})
        print(f"Pipeline crashed:\n{tb}")
    finally:
        ws_io.disable()
        output_queue.put({"type": "done", "message": "Workflow exited."})
```

(d) In `get_dashboard()` (line 151-163), change the served filename from
`ai_dashboard_prototype.html` to prefer the new dashboard. Replace the body with:

```python
@app.get("/")
def get_dashboard():
    """Serves the live pipeline dashboard HTML, if present in the docs dir."""
    for name in ("pipeline_dashboard.html", "ai_dashboard_prototype.html"):
        candidate = (_DOCS_DIR / name) if _DOCS_DIR else None
        if candidate and candidate.is_file():
            return HTMLResponse(candidate.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1>ADL Live Pipeline Dashboard</h1>"
        "<p>The dashboard asset (<code>docs/pipeline_dashboard.html</code>) was not found.</p>",
        status_code=200,
    )
```

(e) In the websocket handler, replace the `if data == "START_WORKFLOW":` branch
condition and thread start. Replace lines 186-204 (`if data == "START_WORKFLOW": ... else: input_queue.put(data)`) with:

```python
            start_payload: dict | None = None
            if data == "START_WORKFLOW":
                start_payload = {"mode": "browse"}
            else:
                try:
                    parsed = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    parsed = None
                if isinstance(parsed, dict) and parsed.get("action") == "start":
                    start_payload = parsed

            if start_payload is not None:
                global active_thread_id
                while not input_queue.empty():
                    try: input_queue.get_nowait()
                    except queue.Empty: break
                while not output_queue.empty():
                    try: output_queue.get_nowait()
                    except queue.Empty: break

                t = threading.Thread(target=run_pipeline, args=(start_payload,), daemon=True)
                t.start()
                active_thread_id = t.ident
                output_queue.put({"type": "log", "message": "Initiating workflow execution..."})
            else:
                input_queue.put(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `E:\LLM\Claude\.venv\Scripts\python.exe -m pytest tests/test_dashboard_api.py -v`
Expected: PASS (2 tests). The `GET /` test passes via the fallback HTML until Task 6 adds the file.

- [ ] **Step 5: Commit**

```bash
git -C E:\LLM\Claude\adl_automated_delivery_pipeline add src/adl_automated_delivery_pipeline/api/app.py tests/test_dashboard_api.py
git -C E:\LLM\Claude\adl_automated_delivery_pipeline commit -m "feat(dashboard): typed start payload + serve dashboard"
```

---

## Task 5: Marker parser (browser + node-testable)

**Files:**
- Create: `docs/dashboard_parser.js`
- Test: `tests/test_dashboard_parser.cjs`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_parser.cjs`:

```javascript
const assert = require("assert");
const { parseMarker } = require("../docs/dashboard_parser.js");

assert.deepStrictEqual(parseMarker("::STAGE doc start::"),
  { kind: "stage", name: "doc", status: "start" });
assert.deepStrictEqual(parseMarker("::ARTIFACT docx=C:/x/ADL-1.docx::"),
  { kind: "artifact", artifactKind: "docx", value: "C:/x/ADL-1.docx" });
assert.deepStrictEqual(parseMarker("::APPROVE dremio=ADL-1: hi::"),
  { kind: "approve", approveKind: "dremio", detail: "ADL-1: hi" });
assert.deepStrictEqual(parseMarker("::DONE::"), { kind: "done" });
assert.deepStrictEqual(parseMarker("  Fetching ADL-1 ..."),
  { kind: "log", text: "  Fetching ADL-1 ..." });

console.log("ok - dashboard_parser");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node E:\LLM\Claude\adl_automated_delivery_pipeline\tests\test_dashboard_parser.cjs`
Expected: FAIL — `Cannot find module '../docs/dashboard_parser.js'`.

- [ ] **Step 3: Write the parser**

Create `docs/dashboard_parser.js`:

```javascript
// Pure marker parser shared by the dashboard (browser) and its node test.
// Returns one of: {kind:'stage',name,status} | {kind:'artifact',artifactKind,value}
//               | {kind:'approve',approveKind,detail} | {kind:'done'} | {kind:'log',text}
function parseMarker(line) {
  const s = String(line).trim();
  let m;
  if ((m = s.match(/^::STAGE\s+(\w+)\s+(start|done|fail)::$/))) {
    return { kind: "stage", name: m[1], status: m[2] };
  }
  if ((m = s.match(/^::ARTIFACT\s+(\w+)=(.*)::$/))) {
    return { kind: "artifact", artifactKind: m[1], value: m[2] };
  }
  if ((m = s.match(/^::APPROVE\s+(\w+)=(.*)::$/))) {
    return { kind: "approve", approveKind: m[1], detail: m[2] };
  }
  if (s === "::DONE::") {
    return { kind: "done" };
  }
  return { kind: "log", text: line };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { parseMarker };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node E:\LLM\Claude\adl_automated_delivery_pipeline\tests\test_dashboard_parser.cjs`
Expected: prints `ok - dashboard_parser`, exit 0.

- [ ] **Step 5: Commit**

```bash
git -C E:\LLM\Claude\adl_automated_delivery_pipeline add docs/dashboard_parser.js tests/test_dashboard_parser.cjs
git -C E:\LLM\Claude\adl_automated_delivery_pipeline commit -m "feat(dashboard): testable marker parser"
```

---

## Task 6: Dashboard UI (`pipeline_dashboard.html`)

**Files:**
- Create: `docs/pipeline_dashboard.html`

No automated DOM test (no JS framework/runner in this repo); the parser logic is
already tested in Task 5. Verify via the manual checklist in Step 3.

- [ ] **Step 1: Create the dashboard**

Create `docs/pipeline_dashboard.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>ADL — Live Pipeline Dashboard</title>
<style>
  :root { --navy:#00386b; --gold:#c89a00; --bg:#0f1420; --panel:#161c2b; --line:#26304a; --ok:#1f9d55; --run:#caa300; --fail:#d14; --muted:#8aa; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:system-ui,Segoe UI,Arial,sans-serif; background:var(--bg); color:#e6ebf5; }
  header { background:var(--navy); padding:12px 18px; display:flex; gap:10px; align-items:center; }
  header h1 { font-size:15px; margin:0 16px 0 0; color:#fff; }
  header input { flex:0 0 200px; padding:7px 9px; border-radius:6px; border:1px solid var(--line); background:#0b101a; color:#fff; }
  header button { padding:7px 14px; border-radius:6px; border:0; background:var(--gold); color:#1a1a1a; font-weight:600; cursor:pointer; }
  header button.secondary { background:#2a3350; color:#dfe6f5; }
  #status { margin-left:auto; font-size:12px; color:var(--muted); }
  main { display:flex; gap:14px; padding:14px; height:calc(100vh - 58px); }
  #timeline { flex:0 0 230px; background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:10px; }
  .stage { display:flex; align-items:center; gap:8px; padding:9px 8px; border-radius:8px; cursor:pointer; font-size:13px; }
  .stage.active { background:#1d2740; }
  .dot { width:12px; height:12px; border-radius:50%; border:2px solid #44506e; }
  .stage[data-st="running"] .dot { background:var(--run); border-color:var(--run); animation:pulse 1s infinite; }
  .stage[data-st="done"] .dot { background:var(--ok); border-color:var(--ok); }
  .stage[data-st="fail"] .dot { background:var(--fail); border-color:var(--fail); }
  .stage[data-st="waiting"] .dot { background:var(--gold); border-color:var(--gold); }
  .stage .t { margin-left:auto; font-size:11px; color:var(--muted); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.35} }
  #detail { flex:1; display:flex; flex-direction:column; gap:10px; min-width:0; }
  #approval { display:none; background:#1a1407; border:1px solid #4a3d12; border-radius:10px; padding:12px; }
  #approval.show { display:block; }
  #approval b { color:var(--gold); }
  #approval .btns { margin-top:8px; display:flex; gap:8px; }
  #approval button { padding:6px 14px; border-radius:6px; border:0; cursor:pointer; font-weight:600; }
  .approve { background:var(--ok); color:#fff; } .reject { background:#3a2330; color:#f3c; }
  #log { flex:1; overflow:auto; background:#05080f; border:1px solid var(--line); border-radius:10px; padding:10px; font-family:Consolas,monospace; font-size:12px; line-height:1.5; white-space:pre-wrap; color:#bfe6bf; }
  #log .err { color:#ff8080; }
  #artifacts { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:10px; min-height:42px; }
  #artifacts .chip { display:inline-block; margin:3px; padding:5px 10px; border-radius:14px; background:#10203a; border:1px solid #2a4a78; font-size:12px; }
  #artifacts a { color:#8fc6ff; text-decoration:none; }
  .label { font-size:11px; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); margin-bottom:4px; }
</style>
</head>
<body>
<header>
  <h1>ASL · Live Pipeline</h1>
  <input id="key" placeholder="ADL-1729" />
  <button id="run">Run</button>
  <button id="browse" class="secondary">Browse</button>
  <span id="status">disconnected</span>
</header>
<main>
  <div id="timeline">
    <div class="label">Pipeline</div>
    <div class="stage" data-stage="jira"   data-st="pending"><span class="dot"></span> Jira fetch <span class="t"></span></div>
    <div class="stage" data-stage="reqs"   data-st="pending"><span class="dot"></span> Extract reqs <span class="t"></span></div>
    <div class="stage" data-stage="doc"    data-st="pending"><span class="dot"></span> Generate doc <span class="t"></span></div>
    <div class="stage" data-stage="dremio" data-st="pending"><span class="dot"></span> Dremio VDS <span class="t"></span></div>
    <div class="stage" data-stage="qlik"   data-st="pending"><span class="dot"></span> Qlik <span class="t"></span></div>
  </div>
  <div id="detail">
    <div id="approval"></div>
    <div>
      <div class="label">Artifacts</div>
      <div id="artifacts"><span style="color:#566">none yet</span></div>
    </div>
    <div id="log"></div>
  </div>
</main>

<script src="/dashboard_parser.js"></script>
<script>
  const $ = (s) => document.querySelector(s);
  const stagesOrder = ["jira","reqs","doc","dremio","qlik"];
  let activeStage = null, startTimes = {}, ws = null;

  function setStatus(t){ $("#status").textContent = t; }
  function stageEl(name){ return document.querySelector('.stage[data-stage="'+name+'"]'); }
  function setStage(name, st){
    const el = stageEl(name); if(!el) return;
    el.dataset.st = st;
    if(st === "running"){ activeStage = name; startTimes[name] = Date.now();
      document.querySelectorAll(".stage").forEach(s=>s.classList.remove("active"));
      el.classList.add("active"); }
    if(st === "done" || st === "fail"){
      const ms = startTimes[name] ? (Date.now()-startTimes[name]) : 0;
      el.querySelector(".t").textContent = ms ? (ms/1000).toFixed(1)+"s" : "";
    }
  }
  function logLine(text, cls){
    const log = $("#log"); const div = document.createElement("div");
    if(cls) div.className = cls; div.textContent = text;
    log.appendChild(div); log.scrollTop = log.scrollHeight;
  }
  function addArtifact(kind, value){
    const box = $("#artifacts");
    if(box.querySelector("span")) box.innerHTML = "";
    const chip = document.createElement("span"); chip.className = "chip";
    const isUrl = /^https?:\/\//.test(value);
    chip.innerHTML = (kind+": ") + (isUrl ? '<a href="'+value+'" target="_blank">'+value+'</a>' : value);
    box.appendChild(chip);
  }
  function showApproval(kind, detail){
    const a = $("#approval");
    a.innerHTML = '⚠ Approve <b>'+kind+'</b>: '+detail +
      '<div class="btns"><button class="approve">Approve</button><button class="reject">Reject</button></div>';
    a.classList.add("show");
    const stage = kind === "dremio" ? "dremio" : "qlik";
    setStage(stage, "waiting");
    a.querySelector(".approve").onclick = ()=>{ ws && ws.send("y"); a.classList.remove("show"); };
    a.querySelector(".reject").onclick  = ()=>{ ws && ws.send("n"); a.classList.remove("show"); };
  }
  function resetUI(){
    stagesOrder.forEach(n=>{ const el=stageEl(n); el.dataset.st="pending"; el.querySelector(".t").textContent=""; });
    $("#log").innerHTML=""; $("#artifacts").innerHTML='<span style="color:#566">none yet</span>';
    $("#approval").classList.remove("show"); startTimes={}; activeStage=null;
  }
  function handle(msg){
    if(msg.type === "error"){ if(activeStage) setStage(activeStage,"fail"); logLine(msg.message,"err"); return; }
    if(msg.type === "done"){ setStatus("done"); return; }
    if(msg.type === "prompt"){ logLine(msg.message); return; } // browse-mode menus echo here
    // type === "log": could be a marker or body text
    const p = parseMarker(msg.message);
    if(p.kind === "stage") setStage(p.name, p.status === "start" ? "running" : (p.status === "done" ? "done" : "fail"));
    else if(p.kind === "artifact") addArtifact(p.artifactKind, p.value);
    else if(p.kind === "approve") showApproval(p.approveKind, p.detail);
    else if(p.kind === "done") setStatus("complete");
    else logLine(p.text);
  }
  function connect(){
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
    ws.onopen = ()=> setStatus("connected");
    ws.onclose = ()=> setStatus("disconnected");
    ws.onmessage = (e)=>{ try { handle(JSON.parse(e.data)); } catch(_) { logLine(e.data); } };
  }
  $("#run").onclick = ()=>{
    const key = $("#key").value.trim(); if(!key) return;
    resetUI(); setStatus("running "+key);
    ws.send(JSON.stringify({action:"start", mode:"ticket", key}));
  };
  $("#browse").onclick = ()=>{ resetUI(); setStatus("browse"); ws.send(JSON.stringify({action:"start", mode:"browse"})); };
  connect();
</script>
</body>
</html>
```

- [ ] **Step 2: Mount the parser JS as a static file**

`pipeline_dashboard.html` loads `/dashboard_parser.js`. Add a route to serve it
in `api/app.py` (right after `get_dashboard`):

```python
@app.get("/dashboard_parser.js")
def get_parser_js():
    """Serve the shared marker parser used by the dashboard."""
    from fastapi.responses import Response
    path = (_DOCS_DIR / "dashboard_parser.js") if _DOCS_DIR else None
    if path and path.is_file():
        return Response(path.read_text(encoding="utf-8"), media_type="application/javascript")
    return Response("// parser missing", media_type="application/javascript", status_code=404)
```

- [ ] **Step 3: Manual verification checklist**

Start the server and exercise it (requires `config.env` with Jira + `ANTHROPIC_API_KEY`):

Run: `E:\LLM\Claude\.venv\Scripts\python.exe -m uvicorn adl_automated_delivery_pipeline.api.main:app --port 8000`
(If `api.main` import differs, use `adl_automated_delivery_pipeline.api.app:app`.)

Open `http://localhost:8000` and confirm:
- [ ] Page loads; status shows "connected".
- [ ] Enter `ADL-1729`, click Run. Jira → reqs → doc stages turn green in order; the log streams; a `docx:` artifact chip appears.
- [ ] An "Approve dremio" card appears and the Dremio row shows waiting (gold). Click **Reject** → run stops, status "complete", Dremio stays not-green.
- [ ] Re-run, this time **Approve** dremio → Dremio stage runs; a `vds:` chip appears; the Qlik approval card appears.
- [ ] Clicking a stage row focuses it (active highlight).

- [ ] **Step 4: Commit**

```bash
git -C E:\LLM\Claude\adl_automated_delivery_pipeline add docs/pipeline_dashboard.html src/adl_automated_delivery_pipeline/api/app.py
git -C E:\LLM\Claude\adl_automated_delivery_pipeline commit -m "feat(dashboard): vertical-timeline dashboard UI + parser route"
```

---

## Task 7: Full verification

**Files:** none new.

- [ ] **Step 1: Run the Python unit suite**

Run: `E:\LLM\Claude\.venv\Scripts\python.exe -m pytest -m unit -q`
Expected: all pass, including `test_dashboard_events`, `test_run_ticket`, `test_dashboard_api`, and the prior 49.

- [ ] **Step 2: Run the JS parser test**

Run: `node E:\LLM\Claude\adl_automated_delivery_pipeline\tests\test_dashboard_parser.cjs`
Expected: `ok - dashboard_parser`.

- [ ] **Step 3: Byte-compile the changed Python**

Run: `E:\LLM\Claude\.venv\Scripts\python.exe -m compileall -q src/adl_automated_delivery_pipeline/workflows/_events.py src/adl_automated_delivery_pipeline/api/app.py`
Expected: no output (success).

- [ ] **Step 4: Manual end-to-end** — complete the Task 6 Step 3 checklist against a live ticket (needs `ANTHROPIC_API_KEY` + Jira creds).

- [ ] **Step 5: Finish the branch** — per `superpowers:finishing-a-development-branch` (merge `feature/live-pipeline-dashboard` to `main` or open a PR).

---

## Self-Review Notes (author)

- **Spec coverage:** §3.1 emitter → T1; §3.2 run_ticket + `_doc_phase` return → T2/T3; §3.3 app.py typed start + parameterized run_pipeline → T4; §3.4 frontend + serve → T6 (parser T5); §4 marker protocol → T1 (producer) + T5 (consumer); §5 data flow → T3/T6; §6 safety (mandatory gates, reject stops) → T3 reject test + T6 checklist; §7 error handling → app.py error event (T4) + `::STAGE fail::` (T3); §8 testing → T1/T3/T4/T5 unit + T6 manual. All covered.
- **Type/name consistency:** marker strings identical across emitter (T1), `run_ticket` (T3), and parser (T5): `::STAGE <name> <start|done|fail>::`, `::ARTIFACT <kind>=<value>::`, `::APPROVE <kind>=<detail>::`, `::DONE::`. `_resolve_start` returns `(mode, key)` used consistently in T4. Stage names `jira,reqs,doc,dremio,qlik` match the timeline rows in T6.
- **No placeholders:** every code/step is complete; the only manual (un-automated) part is the DOM UI, covered by an explicit checklist with the parser logic tested separately.
