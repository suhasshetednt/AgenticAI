# Spec: Live Pipeline Dashboard

**Date:** 2026-06-06
**Status:** Approved (design) — pending user spec review
**Project:** `adl_automated_delivery_pipeline` (ASL Airlines ADL — DnT Infotech)

## 1. Goal & Scope

A browser dashboard to **run the full ADL pipeline and watch it execute live**:
`Jira → Requirements → Documentation → Dremio VDS → Qlik`. The existing
**human approval gates** are preserved, so live Dremio/Qlik writes only happen
after explicit Approve in the UI.

**Entry:** quick-run by ticket key (e.g. `ADL-1729`), plus an optional Browse
path (sprint → assignee → ticket) that reuses the existing interactive menus.

**Layout:** vertical timeline rail + detail panel (selected during brainstorming).

### In scope (v1)
- `run_ticket(key)` that executes all 5 stages start-to-finish, gated.
- Sentinel log markers driving a live stage timeline, log stream, approval cards,
  and artifact chips.
- Vanilla HTML/JS dashboard served by the existing FastAPI app.

### Out of scope (deferred, with seams)
- **Resume / start-at-stage** across runs (`run_ticket(key, start_at=...)` + per-row
  "re-run from here" + run-state/existence detection). Seam only in v1.
- Multi-run history, per-stage timing charts, Browse-menu UI polish (v1 Browse
  works through the raw bridged menus).

## 2. Background (what already exists)

`src/adl_automated_delivery_pipeline/api/app.py` already provides:
- A FastAPI app with `GET /` (serves an optional dashboard HTML) and a `/ws`
  websocket.
- `WebSocketIO` that monkeypatches `builtins.print`/`input` so the interactive
  CLI's stdout/stdin flow over the socket. Output events:
  `{"type": "log"|"prompt"|"error"|"done", "message": str}`. UI replies are text
  pushed to `input_queue` (unblocking the bridged `input()`).
- `START_WORKFLOW` over the socket starts `run_pipeline()` in a background thread,
  which calls `workflows.adl_automated_delivery_pipeline.main()`.

The pipeline (`workflows/adl_automated_delivery_pipeline.py`) is a menu-driven CLI.
`main()` has modes (sprint/backlog/create/github) and y/n gates between
`_doc_phase` → `_dremio_phase` (returns `vds_path`) → `_qlik_phase`. Phase
functions are reusable: `_fetch_ticket`, `_extract_requirements`, `_doc_phase`,
`_dremio_phase`, `_qlik_phase`.

**Decision:** keep this print/input websocket bridge ("wrap the CLI") and make the
stage view reliable by emitting a few **stable sentinel markers**, rather than
regex-matching prose. The big menu `main()` logic is left untouched.

## 3. Architecture

Three additive backend changes + one new frontend file.

### 3.1 Sentinel emitter — `workflows/_events.py` (new)
Tiny helpers that `print()` one machine-readable line each (in addition to normal
human logs). They carry no state and have no deps.

```python
def stage(name: str, status: str) -> None:   # status: start|done|fail
    print(f"::STAGE {name} {status}::")
def artifact(kind: str, value: str) -> None:  # kind: docx|sql|vds|qlik
    print(f"::ARTIFACT {kind}={value}::")
def approve(kind: str, detail: str) -> None:   # kind: dremio|qlik
    print(f"::APPROVE {kind}={detail}::")
def done() -> None:
    print("::DONE::")
```

### 3.2 `run_ticket(key, start_at="jira")` — new function in the workflow module
Reuses the existing phase functions, wrapping each with sentinel markers and
honoring the approval gates. v1 always starts at `jira`; `start_at` is accepted
but only `"jira"` is implemented (seam for resume).

```
stage("jira","start"); ticket=_fetch_ticket(key); stage("jira","done"|"fail")
stage("reqs","start"); reqs=_extract_requirements(ticket); stage("reqs","done")
stage("doc","start");  path=_doc_phase(reqs); artifact("docx",path); stage("doc","done")
approve("dremio", proposed_vds_hint(reqs)); if _inp("Approve Dremio? [y/n]") not yes: done(); return
  # detail = a human hint derived from reqs (proposed VDS name/folder), NOT the final
  # path — the actual vds_path is only known after _dremio_phase runs, emitted as ::ARTIFACT vds=…::
stage("dremio","start"); vds=_dremio_phase(reqs); artifact("vds",vds); stage("dremio","done")
approve("qlik", vds); if yes: stage("qlik","start"); _qlik_phase(reqs,vds); artifact("qlik",url); stage("qlik","done")
done()
```

Minimal additive change to phase functions: ensure `_doc_phase` **returns** the
saved `.docx` Path (today it doesn't return it) so `run_ticket` can emit the
artifact marker. No behavioral change otherwise.

### 3.3 `api/app.py` — accept a typed start message
`START_WORKFLOW` becomes a JSON payload:
- `{"action":"start","mode":"ticket","key":"ADL-1729"}` → `run_ticket(key)`
- `{"action":"start","mode":"browse"}` → existing `main()` (menus over the bridge)

Backward compatible: a bare `"START_WORKFLOW"` string still maps to browse/`main()`.
`run_pipeline()` is parameterized to call the chosen target.

### 3.4 Frontend — `docs/pipeline_dashboard.html` (new), served at `/`
Vanilla HTML + CSS + JS (no framework/build step). `get_dashboard()` in `app.py`
is updated to prefer `pipeline_dashboard.html` (falling back to the current asset
/ placeholder). It opens `/ws` and renders **layout B**:
- **Run bar:** ticket-key `<input>` + **Run** (sends the `ticket` payload); a
  **Browse ▾** toggle (sends the `browse` payload; menu prompts render inline).
- **Timeline rail (left):** 5 stage rows (`jira, reqs, doc, dremio, qlik`), each
  with a status dot (pending/running/done/failed/waiting) driven by `::STAGE::`,
  plus elapsed time. Selecting a row focuses its logs in the detail panel.
- **Detail panel (right):** the log stream for the active/selected stage (plain
  `log` events, attributed to the current stage); **artifact chips** from
  `::ARTIFACT::` (`.docx`, `vds.sql`/VDS path, Qlik URL — clickable where a URL);
  and an **approval card** from `::APPROVE::` with **Approve/Reject** buttons that
  send `"y"`/`"n"` back over the socket to unblock the gate `input()`.

## 4. Marker protocol (the only UI↔pipeline contract)

One marker per line, emitted on stdout (so it rides the existing `log` channel):

| Marker | Meaning |
|--------|---------|
| `::STAGE <name> <start\|done\|fail>::` | stage status; `name ∈ {jira,reqs,doc,dremio,qlik}` |
| `::ARTIFACT <kind>=<value>::` | produced artifact; `kind ∈ {docx,sql,vds,qlik}` |
| `::APPROVE <kind>=<detail>::` | a gate is waiting; show approval card |
| `::DONE::` | run finished |

The frontend parses these lines; **every other `log` line is body text** routed to
the currently-running stage. Unknown markers are ignored (forward-compatible).

## 5. Data flow

```
UI Run(ADL-1729) ──ws {action:start,mode:ticket,key}──► run_ticket(key) [bg thread]
  ::STAGE jira start:: ─► ws log ─► UI: Jira ●running
  ::ARTIFACT docx=…\ADL-1729_…docx:: ─► UI artifact chip
  ::APPROVE dremio=occ.aslb_business:: ─► UI approval card (blocks on input())
  UI Approve ──ws "y"──► input() unblocks ─► VDS created ─► ::STAGE dremio done::
  ::DONE:: ─► UI: complete + summary
```

## 6. Safety

Approval gates remain mandatory before any **Dremio VDS write** and **Qlik build**;
the backend still blocks on `input()`, so the UI cannot bypass them. **Reject**
sends `"n"` → the workflow stops cleanly and emits `::DONE::`. Read-only stages
(Jira fetch, requirement extraction, documentation) run without prompts.

## 7. Error handling

- Pipeline exceptions already surface as an `error` event from `run_pipeline()`'s
  `try/except` → the active stage shows **failed** with the traceback in the detail
  panel; `::DONE::` still fires in `finally`.
- A stage emitting `::STAGE x fail::` marks that row failed and halts the timeline.
- Websocket disconnect cancels the sender task; the existing ghost-thread logic
  stops a stale run if a new one starts.
- Malformed/unknown markers are ignored.

## 8. Testing

- **Marker parser (JS), unit:** feed sample marker lines → assert timeline state
  transitions, artifact chips, approval card show/hide. (Lightweight JS test or a
  small DOM harness; if no JS runner is set up, a documented manual checklist.)
- **Sentinel emitter (Py), unit:** assert each helper prints the exact marker
  string (capture stdout).
- **`run_ticket` (Py), unit:** stub `_fetch_ticket`/`_extract_requirements`/
  `_doc_phase`/`_dremio_phase`/`_qlik_phase` and a fake `input()`; assert phases
  are called in order and the correct markers are emitted around them, including
  the reject path (Dremio `n` → stops, `::DONE::`). Offline, `-m unit`.
- **Manual:** run `ADL-1729` in the browser; watch Doc complete (docx chip),
  approve Dremio, see the VDS path chip; try Reject and confirm a clean stop.

## 9. Build now vs. deferred (YAGNI)

**Now:** `workflows/_events.py`; `run_ticket(key)`; `_doc_phase` returns its path;
`api/app.py` typed start message + parameterized `run_pipeline`; `get_dashboard`
serves the new file; `docs/pipeline_dashboard.html` (timeline + logs + approvals +
artifacts + quick-run + basic Browse toggle); unit tests per §8.

**Deferred (seams only):** resume / `start_at` execution + per-row re-run controls
+ run-state detection; multi-run history; timing charts; Browse-menu UI polish.

## 10. Conventions

Per repo `CLAUDE.md`: library code uses the module logger, not `print()` — **except**
the `workflows/` CLI layer, which intentionally prints to the console/websocket
bridge; the sentinel emitter lives in that layer and is the one place `print()` is
the contract. Full type annotations; specific exceptions; `datetime.now(timezone.utc)`;
no secrets. Frontend is dependency-free (no build step), matching how `app.py`
already serves a static dashboard.
