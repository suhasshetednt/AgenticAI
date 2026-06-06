"""
ADL WORKFLOW  —  JIRA + DOCUMENTATION + DREMIO  (ASL Airlines)
===============================================================
Sequence:
  1. Jira Agent   — fetch ticket, extract requirements
  2. Doc Agent    — generate Technical Implementation Document (.docx)
  3. Dremio Agent — generate VDS SQL, select folder path, create VDS

Start menu:
  [1] Work on an existing ticket (browse sprint -> assignee -> ticket)
  [2] Browse backlog tickets
  [3] Create a new ticket
  [0] Exit

Usage:
    python adl_automated_delivery_pipeline/workflows/adl_automated_delivery_pipeline.py
"""
from __future__ import annotations

import sys
import os
import json
import logging
import time
from typing import Any, cast
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Allow direct execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv
from jira import JIRA, JIRAError
from langchain_core.messages import HumanMessage, SystemMessage

from adl_automated_delivery_pipeline.agents.base import get_llm
from adl_automated_delivery_pipeline.agents.dremio_agent import DremioAgent
from adl_automated_delivery_pipeline.agents.doc_agent import DocumentationAgent
from adl_automated_delivery_pipeline.agents.qlik_agent import QlikAgent
from adl_automated_delivery_pipeline.state import make_initial_state
from adl_automated_delivery_pipeline.workflows import _events as ev

logger = logging.getLogger(__name__)

PROJECT     = "ADL"
_BOARD_ID   = 2          # ADL board (simple board, id confirmed)
_DIV        = "=" * 62
_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "generated_queries"


# ── Self-healing memory ──────────────────────────────────────────────────────────

_MEMORY: Any = None


def _memory_mgr() -> Any:
    """Lazily build the shared MemoryManager (best-effort; ``None`` if unavailable)."""
    global _MEMORY
    if _MEMORY is None:
        try:
            from adl_automated_delivery_pipeline.memory import MemoryManager
            _MEMORY = MemoryManager()
        except Exception as exc:  # noqa: BLE001 - memory is best-effort
            logger.warning("Memory backend unavailable: %s", exc)
            _MEMORY = False  # sentinel: tried and failed
    return _MEMORY or None


def _record_autofix(error: str, fix: str, context: str = "") -> None:
    """Announce an auto-fix and persist the error + fix to memory.

    The printed ``auto-fix`` token is what flips the matching agent into the
    blinking "healing" state on the live dashboard, so keep it in the message.
    """
    print(f"  [auto-fix] {context or 'error intercepted'} — applying fix and saving to memory ...")
    mgr = _memory_mgr()
    if mgr is None:
        print("  [memory] backend unavailable — fix not persisted.")
        return
    try:
        mgr.store_error_fix(error=error, fix=fix, context=context)
        print("  [memory] error + fix saved for future runs.")
    except Exception as exc:  # noqa: BLE001 - never let memory break the workflow
        logger.warning("Could not store error+fix: %s", exc)


# ── Console helpers ─────────────────────────────────────────────────────────────

def _inp(prompt: str, required: bool = True) -> str:
    """Read stripped user input; exit cleanly on Ctrl-C / EOF."""
    while True:
        try:
            val = input(f"  {prompt}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Interrupted. Exiting.")
            raise SystemExit(0)
        if val or not required:
            return val
        print("  (required — please enter a value)")


def _header(title: str) -> None:
    print(f"\n{_DIV}")
    print(f"  {title}")
    print(_DIV)


def _read_multiline(label: str = "Enter SQL (blank line twice when done):") -> str:
    print(f"  {label}")
    lines: list[str] = []
    try:
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        pass
    return "\n".join(lines).strip()


# ── Jira helpers ────────────────────────────────────────────────────────────────

def _jira() -> Any:
    username = os.getenv("JIRA_USERNAME")
    token = os.getenv("JIRA_API_TOKEN")
    return JIRA(
        server=os.getenv("JIRA_INSTANCE_URL"),
        basic_auth=(username, token) if username and token else None,
        max_retries=0,
        timeout=10,
    )


def _issues_to_list(issues: list[Any]) -> list[dict[str, Any]]:
    """Convert a list of Jira issue objects to plain dicts."""
    return [
        {
            "id":       i.key,
            "summary":  i.fields.summary[:100],
            "state":    i.fields.status.name,
            "assignee": i.fields.assignee.displayName if i.fields.assignee else "Unassigned",
            "priority": getattr(i.fields.priority, "name", "-"),
            "type":     i.fields.issuetype.name,
        }
        for i in issues
    ]


def _fetch_sprint_issues(sprint_id: int) -> list[dict[str, Any]]:
    """Return ALL tickets for the given sprint (paginated — no server-side cap)."""
    try:
        raw = _jira().search_issues(
            f"project = {PROJECT} AND sprint = {sprint_id} ORDER BY assignee ASC",
            maxResults=False,
            fields="summary,status,assignee,priority,issuetype",
        )
        return _issues_to_list(raw)
    except JIRAError as e:
        print(f"  Jira ERROR: {e.text}")
        return []
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def _fetch_backlog_issues() -> list[dict[str, Any]]:
    """Return all ADL backlog tickets (not in any sprint, not Done)."""
    try:
        raw = _jira().search_issues(
            f"project = {PROJECT} AND sprint is EMPTY "
            f"AND statusCategory != Done ORDER BY assignee ASC",
            maxResults=False,
            fields="summary,status,assignee,priority,issuetype",
        )
        return _issues_to_list(raw)
    except JIRAError as e:
        print(f"  Jira ERROR: {e.text}")
        return []
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def _fetch_ticket(ticket_id: str) -> dict[str, Any]:
    """Fetch full ticket including complete description and image attachments."""
    import base64
    try:
        issue = _jira().issue(ticket_id)
        f = issue.fields
        
        attachments: list[dict[str, Any]] = []
        if hasattr(f, 'attachment'):
            for att in f.attachment:
                mime_type = getattr(att, 'mimeType', '')
                if mime_type.startswith("image/"):
                    try:
                        content = att.get()
                        b64 = base64.b64encode(content).decode('utf-8')
                        attachments.append({
                            "filename": getattr(att, 'filename', 'image'),
                            "mimeType": mime_type,
                            "data": b64
                        })
                    except Exception as e:
                        logger.warning("Could not read attachment: %s", e)

        return {
            "status":      "SUCCESS",
            "id":          issue.key,
            "summary":     f.summary,
            "description": f.description or "",
            "state":       f.status.name,
            "priority":    getattr(f.priority, "name", "-"),
            "assignee":    f.assignee.displayName if f.assignee else "Unassigned",
            "reporter":    f.reporter.displayName if f.reporter else "-",
            "type":        f.issuetype.name,
            "attachments": attachments,
        }
    except JIRAError as e:
        return {"status": "FAILED", "error": e.text}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


# ── Project selection ────────────────────────────────────────────────────────────

# Friendly fallback when Jira can't be reached (offline / auth issue). The board id
# is only a hint — at runtime we discover the real board for the chosen project.
_KNOWN_PROJECTS: dict[str, int] = {"ADL": 2}


def _discover_projects() -> list[dict[str, Any]]:
    """Return the Jira projects the user can work on as ``[{key, name}]``.

    Falls back to the known-projects map when the Jira API is unavailable.
    """
    try:
        projects = _jira().projects()
        out = [{"key": p.key, "name": getattr(p, "name", p.key)} for p in projects]
        out.sort(key=lambda p: p["key"])
        if out:
            return out
    except Exception as exc:  # noqa: BLE001 - graceful offline degradation
        logger.warning("Could not list Jira projects: %s", exc)
    return [{"key": k, "name": k} for k in _KNOWN_PROJECTS]


def _resolve_board_id(project_key: str) -> int:
    """Find the agile board id for *project_key* that actually carries sprints.

    Priority:
      1. The confirmed board id from ``_KNOWN_PROJECTS`` (e.g. ADL -> board 2).
      2. The first *scrum* board (Kanban boards have no sprints).
      3. The first board of any type.
    """
    # Confirmed board ids win — they are known to hold the active sprint.
    known = _KNOWN_PROJECTS.get(project_key)
    if known:
        return known
    try:
        boards = _jira().boards(projectKeyOrID=project_key)
        if boards:
            scrum = [b for b in boards if getattr(b, "type", "").lower() == "scrum"]
            chosen = scrum[0] if scrum else boards[0]
            return int(chosen.id)
    except Exception as exc:  # noqa: BLE001 - graceful offline degradation
        logger.warning("Could not resolve board for %s: %s", project_key, exc)
    return 0


def _pick_project() -> bool:
    """Let the user choose which Jira project to work on.

    Updates the module-level ``PROJECT`` and ``_BOARD_ID`` globals so every
    downstream helper (sprint/backlog/JQL) targets the chosen project. Returns
    ``False`` if the user cancels.
    """
    global PROJECT, _BOARD_ID

    _header("SELECT PROJECT")
    print("  Loading projects ...")
    projects = _discover_projects()

    proj_map: dict[str, dict[str, Any]] = {}
    for idx, p in enumerate(projects, start=1):
        proj_map[str(idx)] = p
        marker = "   (default)" if p["key"] == PROJECT else ""
        print(f"  [{idx}] {p['key']:<10} {p['name']}{marker}")
    print("  [0] Cancel")
    print(_DIV)

    while True:
        raw = _inp(f"Select project number (Enter for {PROJECT}): ", required=False)
        if raw == "":
            chosen = next((p for p in projects if p["key"] == PROJECT), projects[0])
            break
        if raw == "0":
            return False
        if raw in proj_map:
            chosen = proj_map[raw]
            break
        print("  Invalid selection — please try again.")

    PROJECT = chosen["key"]
    _BOARD_ID = _resolve_board_id(PROJECT)
    print(f"\n  Project set to {PROJECT}  (board id {_BOARD_ID}).")
    return True


# ── Sprint selection ─────────────────────────────────────────────────────────────

def _load_sprints() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (active_sprints, last_10_closed_sprints) as dicts."""
    try:
        all_sprints: list[Any] = _jira().sprints(_BOARD_ID)
        active: list[dict[str, Any]] = []
        closed: list[dict[str, Any]] = []
        for s in all_sprints:
            entry = {"id": s.id, "name": s.name, "state": s.state}
            if s.state == "active":
                active.append(entry)
            elif s.state == "closed":
                closed.append(entry)
        # Most-recent closed sprints last in list — reverse for newest-first display
        closed_recent = list(reversed(closed[-10:]))
        return active, closed_recent
    except Exception as e:
        logger.warning("Could not load sprints: %s", e)
        return [], []


def _pick_sprint() -> dict[str, Any] | None:
    """Show active + recent closed sprints; return selected sprint dict or None."""
    print(f"\n  Loading sprints ...", end="", flush=True)
    active, closed = _load_sprints()
    print(" done")

    if not active and not closed:
        print("  Could not load sprints.")
        return None

    _header("SELECT SPRINT")
    idx = 1
    sprint_map: dict[str, dict[str, Any]] = {}

    if active:
        print("  -- Active Sprint --")
        for s in active:
            print(f"  [{idx:2d}]  {s['name']}  [ACTIVE]  <-- default")
            sprint_map[str(idx)] = s
            idx += 1

    if closed:
        print("\n  -- Recent Closed Sprints --")
        for s in closed:
            print(f"  [{idx:2d}]  {s['name']}  [CLOSED]")
            sprint_map[str(idx)] = s
            idx += 1

    print(f"  [ 0]  Back")
    print(_DIV)

    while True:
        raw = _inp("Select sprint number: ")
        if raw == "0":
            return None
        if raw in sprint_map:
            chosen = sprint_map[raw]
            print(f"\n  Selected: {chosen['name']}  [{chosen['state'].upper()}]")
            return chosen
        print(f"  Please enter a number between 1 and {idx - 1}, or 0 to go back.")


# ── Assignee and ticket pickers ──────────────────────────────────────────────────

def _pick_assignee(issues: list[dict[str, Any]], sprint_name: str) -> str | None:
    """Show unique assignees with ticket counts; return chosen name or None."""
    assignees = sorted(set(i["assignee"] for i in issues))
    _header(f"ASSIGNEES  --  {sprint_name}")
    for idx, name in enumerate(assignees, 1):
        count = sum(1 for i in issues if i["assignee"] == name)
        print(f"  [{idx:2d}]  {name}  ({count} ticket{'s' if count != 1 else ''})")
    print(f"  [ 0]  Back")
    print(_DIV)

    while True:
        raw = _inp("Select assignee number: ")
        if raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(assignees):
            return assignees[int(raw) - 1]
        print(f"  Please enter a number between 1 and {len(assignees)}, or 0 to go back.")


def _pick_ticket(issues: list[dict[str, Any]], assignee: str) -> dict[str, Any] | None:
    """Show assignee's tickets; return chosen ticket dict or None."""
    my_issues = [i for i in issues if i["assignee"] == assignee]
    if not my_issues:
        print(f"\n  No tickets found for {assignee}.")
        return None

    _header(f"TICKETS  --  {assignee}")
    # Column-aligned table — renders cleanly in the monospace web console and the CLI.
    print(f"  {'#':>2}   {'Key':<9} {'Status':<17} {'Priority':<9} Summary")
    print(f"  {'-' * 2}   {'-' * 9} {'-' * 17} {'-' * 9} {'-' * 45}")
    for idx, t in enumerate(my_issues, 1):
        summary = t["summary"] or ""
        if len(summary) > 55:
            summary = summary[:54].rstrip() + "..."
        print(f"  {idx:>2d}   {t['id']:<9} {t['state']:<17} {t['priority']:<9} {summary}")
    print(f"  {'0':>2}   Back")
    print(_DIV)

    while True:
        raw = _inp("Select ticket number: ")
        if raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(my_issues):
            return my_issues[int(raw) - 1]
        print(f"  Please enter a number between 1 and {len(my_issues)}, or 0 to go back.")


# ── Status transition ────────────────────────────────────────────────────────────

def _transition_to_in_progress(ticket_id: str, current_state: str) -> None:
    """Move a ticket from To Do → In Progress. No-op if already past that state."""
    if current_state.lower() != "to do":
        return
    try:
        jc = _jira()
        transitions = jc.transitions(ticket_id)
        in_progress = next(
            (t for t in transitions if "in progress" in t["to"]["name"].lower()),
            None,
        )
        if not in_progress:
            print(f"  WARNING: No 'In Progress' transition found for {ticket_id}.")
            return
        jc.transition_issue(ticket_id, in_progress["id"])
        print(f"  Status  : To Do  →  In Progress")
    except JIRAError as e:
        print(f"  WARNING: Could not transition ticket: {e.text}")
    except Exception as e:
        print(f"  WARNING: Could not transition ticket: {e}")


# ── Requirements extraction ──────────────────────────────────────────────────────

_EXTRACTION_PROMPT = """You are a requirements analyst. Extract structured information from the Jira ticket description below and any attached images.

Return a JSON object with EXACTLY these keys:
{{
  "business_requirement": "<one paragraph summary of what needs to be built>",
  "source_database": "<database name, e.g. amos_postgres>",
  "source_tables": ["<schema.table_name>", ...],
  "output_fields": [{{"name": "<field_name>", "description": "<what it represents>"}}, ...],
  "transformations": ["<each transformation rule as a plain English sentence>", ...],
  "filter_conditions": ["<each filter/where condition>", ...],
  "acceptance_criteria": ["<each acceptance criterion>", ...]
}}

Rules:
- source_tables must use full schema.table format (e.g. amos.staff_pqs_qualification)
- transformations must include date conversion rules, CASE WHEN logic, NULLIF patterns, AND any conditional formatting or calculations detailed in the attached images.
- Return ONLY the JSON object — no markdown fences, no explanation

Ticket description:
{description}
"""


@dataclass
class TicketRequirements:
    ticket_id: str
    summary: str
    business_requirement: str
    source_database: str
    source_tables: list[str]
    output_fields: list[dict[str, Any]]
    transformations: list[str]
    filter_conditions: list[str]
    acceptance_criteria: list[str]
    extra_notes: str = ""
    raw_description: str = field(default="", repr=False)


def _extract_requirements(ticket: dict[str, Any]) -> TicketRequirements | None:
    """Jira Agent phase: use LLM to parse ticket description into structured requirements."""
    desc = ticket.get("description", "")

    if not desc:
        print("  WARNING: Ticket has no description — using summary only.")
        return TicketRequirements(
            ticket_id=ticket["id"],
            summary=ticket["summary"],
            business_requirement=ticket["summary"],
            source_database="amos_postgres",
            source_tables=[],
            output_fields=[],
            transformations=[],
            filter_conditions=[],
            acceptance_criteria=[],
        )

    # Truncate very long descriptions to stay within the 10k TPM free-tier limit.
    # ~4,000 chars ≈ 1,000 tokens; leaves budget for prompt template + response.
    _MAX_DESC_CHARS = 4_000
    if len(desc) > _MAX_DESC_CHARS:
        desc = desc[:_MAX_DESC_CHARS] + "\n\n[... description truncated for token limit ...]"

    print("  Jira Agent analyzing ticket ...", end="", flush=True)
    _retry_delays = [65, 65]  # wait out the full 60-second TPM window
    for _attempt, _delay in enumerate(_retry_delays, start=1):
        try:
            llm = get_llm()
            
            attachments = ticket.get("attachments", [])
            msg_content: list[dict[str, Any]] = [{"type": "text", "text": _EXTRACTION_PROMPT.format(description=desc)}]
            for att in attachments:
                msg_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{att['mimeType']};base64,{att['data']}"}
                })

            response = llm.invoke([
                SystemMessage(content="You are a precise requirements analyst. Return only valid JSON. Analyze both text and attached images for any logic/formulas/formatting rules."),
                HumanMessage(content=cast(Any, msg_content)),
            ])
            raw: str = str(response.content).strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw.strip())
            print(" done")
            return TicketRequirements(
                ticket_id=ticket["id"],
                summary=ticket["summary"],
                business_requirement=parsed.get("business_requirement", ticket["summary"]),
                source_database=parsed.get("source_database", "amos_postgres"),
                source_tables=parsed.get("source_tables", []),
                output_fields=parsed.get("output_fields", []),
                transformations=parsed.get("transformations", []),
                filter_conditions=parsed.get("filter_conditions", []),
                acceptance_criteria=parsed.get("acceptance_criteria", []),
                raw_description=desc,
            )
        except json.JSONDecodeError as e:
            print(f"\n  JSON parse error: {e}")
            return None
        except Exception as e:
            err = str(e)
            if ("rate_limit" in err.lower() or "429" in err) and _attempt <= len(_retry_delays):
                print(f"\n  Rate limited — waiting {_delay}s before retry ({_attempt}/{len(_retry_delays)}) ...")
                time.sleep(_delay)
                continue
            print(f"\n  ERROR: {e}")
        return None


def _display_requirements(reqs: TicketRequirements) -> None:
    _header("TICKET REQUIREMENTS  (extracted by Jira Agent)")
    print(f"  Ticket  : {reqs.ticket_id}")
    print(f"  Summary : {reqs.summary}\n")
    print(f"  Business Requirement:")
    print(f"    {reqs.business_requirement}\n")
    print(f"  Source Database : {reqs.source_database}")
    print(f"  Source Tables ({len(reqs.source_tables)}):")
    for t in reqs.source_tables:
        print(f"    - {t}")
    print(f"\n  Output Fields ({len(reqs.output_fields)}):")
    for f in reqs.output_fields:
        print(f"    - {f['name']}: {f.get('description', '')}")
    print(f"\n  Transformations ({len(reqs.transformations)}):")
    for t in reqs.transformations:
        print(f"    - {t}")
    if reqs.filter_conditions:
        print(f"\n  Filters ({len(reqs.filter_conditions)}):")
        for c in reqs.filter_conditions:
            print(f"    - {c}")
    print(f"\n  Acceptance Criteria ({len(reqs.acceptance_criteria)}):")
    for a in reqs.acceptance_criteria:
        print(f"    - {a}")
    print(_DIV)


# AMOS table column overrides — the catalog_data.json entry for these tables reflects a
# different source (usually MM with tail_number-style columns). When the table appears in
# an AMOS context (amos.* prefix in source_tables), use these authoritative columns instead.
# Survives catalog regeneration from dremio_catalog_sync.py.
_AMOS_CATALOG_OVERRIDES: dict[str, list[dict[str, str]]] = {
    "aircraft": [
        {"name": "ac_registr", "type": "VARCHAR",
         "desc": "Aircraft registration — JOIN key for all AMOS aircraft lookups (e.g. EI-FTD)"},
        {"name": "ac_typ",     "type": "VARCHAR",
         "desc": "Aircraft type (e.g. B737NG, B737MAX) — NOT tail_number (that is MM only)"},
    ],
}


def _get_table_schema(tname: str) -> str:
    from adl_automated_delivery_pipeline.tools.catalog_loader import load_raw
    base_name = tname.split(".")[-1].lower()

    # For AMOS-prefixed tables check the override map first.
    # The catalog entry for some tables (e.g. aircraft) reflects a different source domain
    # and would give the LLM wrong column names (e.g. tail_number instead of ac_registr).
    if tname.lower().startswith("amos.") and base_name in _AMOS_CATALOG_OVERRIDES:
        override = _AMOS_CATALOG_OVERRIDES[base_name]
        col_lines: list[str] = [
            f"    - {c['name']} ({c['type']}) - {c['desc']}" for c in override
        ]
        return (
            f"Table: {tname}  [AMOS override — catalog entry is from a different source]\n"
            + "\n".join(col_lines)
        )

    try:
        _, descriptions, columns = load_raw()
        cols = columns.get(base_name)
        if not cols:
            for k, v in columns.items():
                if k.lower() == base_name:
                    cols = v
                    base_name = k
                    break
        if cols:
            desc = descriptions.get(base_name, "")
            header = f"Table: {tname}" + (f" ({desc})" if desc else "")
            col_lines: list[str] = []
            for c in cols:
                desc_str = f" - {c['desc']}" if c.get("desc") else ""
                col_lines.append(f"    - {c['name']} ({c['type']}){desc_str}")
            return f"{header}\n" + "\n".join(col_lines)
    except Exception as exc:
        logger.warning("Failed to load schema for %s: %s", tname, exc)
    return f"Table: {tname} (schema not found in catalog)"


def _build_dremio_prompt(reqs: TicketRequirements) -> str:
    fields_txt = "\n".join(
        f"  - {f['name']}: {f.get('description', '')}" for f in reqs.output_fields
    ) or "  - (not specified)"
    tables_txt = "\n".join(f"  - {t}" for t in reqs.source_tables) or "  - (not specified)"
    transforms  = "\n".join(f"  - {t}" for t in reqs.transformations) or "  - (not specified)"
    filters     = "\n".join(f"  - {c}" for c in reqs.filter_conditions) or "  - None specified"
    acceptance  = "\n".join(f"  - {a}" for a in reqs.acceptance_criteria) or "  - (not specified)"
    notes_block = f"\n--- ADDITIONAL INSTRUCTIONS ---\n{reqs.extra_notes}" if reqs.extra_notes else ""

    # Look up schemas from catalog for each source table
    schemas_list: list[str] = []
    for t in reqs.source_tables:
        schemas_list.append(_get_table_schema(t))
    schemas_txt = "\n\n".join(schemas_list) if schemas_list else "  - (no table schemas available)"

    return f"""Generate an optimised Dremio SQL query for the following requirement.
Apply ALL rules from the query rules document before writing any SQL.
Do NOT add LIMIT or ORDER BY — this query will be used as a Virtual Dataset definition.
Add the VDS comment block at the top.

--- TICKET ---
Ticket ID : {reqs.ticket_id}
Summary   : {reqs.summary}

--- BUSINESS REQUIREMENT ---
{reqs.business_requirement}

--- SOURCE DATABASE ---
{reqs.source_database}
CRITICAL: All AMOS table references MUST use the prefix amos_postgres.amos.<table>
Example: amos_postgres.amos.rotables_trend  (NEVER amos_acceptance, amos_dev, amos_staging, etc.)

--- SOURCE TABLES ---
{tables_txt}

--- DATA CATALOG SCHEMAS (CRITICAL: ALWAYS use exact column names from here) ---
{schemas_txt}

--- REQUIRED OUTPUT FIELDS ---
{fields_txt}

--- TRANSFORMATION RULES ---
{transforms}

--- FILTER CONDITIONS ---
{filters}

--- ACCEPTANCE CRITERIA ---
{acceptance}{notes_block}

Generate the complete, optimised SQL query now.
Return ONLY the SQL — no explanation before or after.
"""


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        return "\n".join(ln for ln in lines if not ln.strip().startswith("```")).strip()
    return text


# Dremio reserved words that break parse when used unquoted as aliases or column refs
_DREMIO_RESERVED: frozenset[str] = frozenset({
    "value", "values", "timestamp", "date", "time", "interval",
    "type", "status", "end", "start", "key", "level",
    "row", "rows", "rank", "position", "percent",
    "group", "order", "table",
    "year", "month", "day", "hour", "minute", "second",
})


def _remove_semicolons(sql: str) -> str:
    """Remove semicolons — Dremio (Calcite SQL) rejects them anywhere in a query."""
    import re
    sql = sql.rstrip().rstrip(";").rstrip()
    sql = re.sub(r";(?=(?:[^'\"]*['\"][^'\"]*['\"])*[^'\"]*$)", " ", sql)
    return sql


def _fix_dremio_sql(sql: str) -> str:
    """Fix common LLM-generated SQL patterns that Dremio (Calcite) rejects."""
    import re
    # GROUP BY () — Calcite doesn't accept empty parens; just remove the clause
    sql = re.sub(r"\bGROUP\s+BY\s*\(\s*\)", "", sql, flags=re.IGNORECASE)
    # COUNT() → COUNT(*)
    sql = re.sub(r"\bCOUNT\s*\(\s*\)", "COUNT(*)", sql, flags=re.IGNORECASE)
    # Fix wrong AMOS source prefix — only amos_postgres.amos.* is valid (rule 1.6)
    sql = re.sub(r"\bamos_\w+\.amos\.", "amos_postgres.amos.", sql, flags=re.IGNORECASE)
    # Fix AMOS rotables column names — catalog-confirmed names are partno/serialno.
    # LLM sometimes generates SQL-standard (part_no/serial_no) or short forms (pn/sn).
    # No other catalog table uses pn or sn so these substitutions are safe.
    sql = re.sub(r"\b(\w+)\.part_no\b", r"\1.partno", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\b(\w+)\.serial_no\b", r"\1.serialno", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\b(\w+)\.pn\b", r"\1.partno", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\b(\w+)\.sn\b", r"\1.serialno", sql, flags=re.IGNORECASE)
    # For AMOS queries: aircraft.tail_number is ALWAYS wrong — AMOS aircraft uses ac_registr.
    # tail_number belongs to the MM aircraft table (different source, different join key).
    if re.search(r"amos_postgres\.amos\.", sql, re.IGNORECASE):
        sql = re.sub(r"\b(\w+)\.tail_number\b", r"\1.ac_registr", sql, flags=re.IGNORECASE)
    # Remove outermost ORDER BY at the end of the query (VDS definitions cannot have ORDER BY)
    sql = re.sub(r"(?i)\bORDER\s+BY\s+(?:(?!\b(?:WITH|SELECT|FROM|WHERE|GROUP|HAVING|WINDOW|OVER|\)))\b[\s\S])*$", "", sql)
    return sql.strip()


def _validate_columns_against_catalog(sql: str) -> list[str]:
    """Check every alias.column reference in SQL against catalog_data.json.

    Returns a list of warning strings for columns not found in their table.
    Tables absent from the catalog are silently skipped (Dremio is authoritative
    for tables we haven't catalogued yet).
    """
    import re
    from adl_automated_delivery_pipeline.tools.catalog_loader import load_raw

    try:
        _, _, columns = load_raw()
    except Exception:
        return []

    # Build alias → base_table_name map from FROM/JOIN clauses
    # Handles: amos_postgres.amos.rotables r  OR  amos_postgres.amos.rotables AS r
    _SKIP_KEYWORDS = frozenset({
        "where", "on", "left", "right", "inner", "outer", "cross",
        "join", "set", "select", "from", "with", "as",
    })
    alias_map: dict[str, str] = {}
    alias_pat = re.compile(
        r"(?:FROM|JOIN)\s+(?:\w+\.)*(\w+)\s+(?:AS\s+)?([A-Za-z_]\w*)",
        re.IGNORECASE,
    )
    for m in alias_pat.finditer(sql):
        alias = m.group(2).lower()
        if alias in _SKIP_KEYWORDS:
            continue
        alias_map[alias] = m.group(1).lower()

    if not alias_map:
        return []

    # Detect whether this is an AMOS query — enables override map for tables like aircraft
    # whose catalog entry reflects a different source domain (e.g. MM instead of AMOS).
    is_amos_query = bool(re.search(r"amos_postgres\.amos\.", sql, re.IGNORECASE))

    # Pre-build case-insensitive catalog lookup: lower_table_name → {lower_col_name: real_col_name}
    catalog_index: dict[str, dict[str, str]] = {}
    for tname, tcols in columns.items():
        catalog_index[tname.lower()] = {c["name"].lower(): c["name"] for c in tcols}

    # Check every alias.column reference
    col_ref_pat = re.compile(r'\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b')
    checked: set[tuple[str, str]] = set()
    issues: list[str] = []

    for m in col_ref_pat.finditer(sql):
        alias = m.group(1).lower()
        col = m.group(2).lower()
        key = (alias, col)
        if key in checked or alias not in alias_map:
            continue
        checked.add(key)

        tname = alias_map[alias]

        # For AMOS queries, check the override map first so we validate against
        # the correct AMOS column set, not a wrong catalog entry from another domain.
        override = _AMOS_CATALOG_OVERRIDES.get(tname) if is_amos_query else None
        if override is not None:
            cat_cols = {c["name"].lower(): c["name"] for c in override}
        else:
            cat_cols = catalog_index.get(tname)
        if cat_cols is None:
            continue  # table not in catalog — skip silently

        if col not in cat_cols:
            # Fuzzy suggestions: strip underscores and compare
            col_plain = col.replace("_", "")
            suggestions: list[str] = [
                real for lower, real in cat_cols.items()
                if col_plain in lower.replace("_", "") or lower.replace("_", "") in col_plain
            ]
            hint = f"  Did you mean: {', '.join(suggestions[:4])}?" if suggestions else ""
            issues.append(
                f"  Column '{m.group(2)}' not found in '{tname}' (alias '{m.group(1)}').{hint}"
            )

    return issues


def _fix_reserved_keywords(sql: str) -> str:
    """Quote any Dremio reserved word used bare as an alias or dotted column reference.

    Handles two patterns:
      AS value       → AS "value"
      table.value    → table."value"
    Skips words that are already quoted.
    """
    import re

    def _quote_alias(m: re.Match[str]) -> str:
        keyword, word = str(m.group(1)), str(m.group(2))
        if word.lower() in _DREMIO_RESERVED:
            return f"{keyword} \"{word}\""
        return str(m.group(0))

    def _quote_dot_ref(m: re.Match[str]) -> str:
        prefix, word = str(m.group(1)), str(m.group(2))
        if word.lower() in _DREMIO_RESERVED:
            return f"{prefix}\"{word}\""
        return str(m.group(0))

    # AS value  (not already quoted)
    sql = re.sub(r"\b(AS)\s+([A-Za-z_]\w*)\b", _quote_alias, sql, flags=re.IGNORECASE)
    # table.value  (not already quoted — regex won't match ."word" since " is not [A-Za-z_])
    sql = re.sub(r"(\.)([A-Za-z_]\w*)\b", _quote_dot_ref, sql)
    return sql


def _save_sql(reqs: TicketRequirements, sql: str) -> Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    sql_path = _OUTPUT_DIR / f"{reqs.ticket_id}_{ts}.sql"
    sql_path.write_text(sql, encoding="utf-8")
    (_OUTPUT_DIR / f"{reqs.ticket_id}_{ts}.json").write_text(
        json.dumps({
            "ticket_id":        reqs.ticket_id,
            "summary":          reqs.summary,
            "generated_at":     ts,
            "source_database":  reqs.source_database,
            "source_tables":    reqs.source_tables,
            "output_fields":    reqs.output_fields,
            "transformations":  reqs.transformations,
            "acceptance_criteria": reqs.acceptance_criteria,
        }, indent=2),
        encoding="utf-8",
    )
    return sql_path


# ── Documentation Agent phase ───────────────────────────────────────────────────

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


# ── Dremio folder path helper ────────────────────────────────────────────────────

def _fetch_dremio_folders() -> list[str]:
    """Return a list of folder paths under dremio-db by calling the catalog API."""
    try:
        from adl_automated_delivery_pipeline.tools.dremio_tools import list_catalog_children
        result = cast(Any, list_catalog_children).invoke({"path": "dremio-db"})
        if result.get("status") != "SUCCESS":
            return []
        folders = [
            f"dremio-db.{c['name']}"
            for c in result.get("children", [])
            if c.get("type") in ("CONTAINER", "FOLDER", None)
        ]
        return sorted(folders)
    except Exception as exc:
        logger.warning("Could not fetch dremio-db folders: %s", exc)
        return []


def _suggest_vds_name(summary: str, sql: str) -> str:
    """Derive a VDS name suggestion from SQL comment, then ticket summary."""
    # 1. Try SQL comment: -- VDS : some_name_vds
    for line in sql.splitlines()[:8]:
        stripped = line.strip()
        if stripped.startswith("-- VDS"):
            candidate = stripped.split(":", 1)[-1].strip()
            if candidate:
                return candidate
    # 2. Derive from ticket summary: "[APU Health Monitor] Create query ..." → apu_health_monitor_vds
    import re
    # Extract bracketed project name if present
    bracket = re.search(r"\[([^\]]+)\]", summary)
    base = bracket.group(1) if bracket else summary
    slug = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_")
    return f"{slug}_vds"


def _quote_dremio_path(space: str, folder: str, vds_name: str) -> str:
    """Build a fully-quoted, dot-separated Dremio path.

    `folder` may be slash-separated (e.g. 'engine/reports'); each segment must be
    quoted individually — Dremio rejects a single quoted segment containing '/'.
    """
    parts = [space, *(p for p in folder.split("/") if p), vds_name]
    return ".".join(f'"{p}"' for p in parts)


def _pick_vds_location(
    summary: str,
    sql: str,
) -> tuple[str, str, str] | None:
    """Step-by-step VDS location picker: folder → (optional sub-folder) → VDS name.

    Returns (space, folder_slash_path, vds_name) or None if cancelled.
    """
    from adl_automated_delivery_pipeline.tools.dremio_tools import create_dremio_folder

    _header("CREATE VDS  —  Step 1: Choose folder in dremio-db")
    print("  Fetching existing folders under dremio-db ...", end="", flush=True)
    folders = _fetch_dremio_folders()           # ["dremio-db.amos_engine", ...]
    folder_names = [f.split(".", 1)[-1] for f in folders]
    print(f" done  ({len(folder_names)} folders found)\n")

    # ── Step 1: pick or create top-level folder ────────────────────────────────
    is_new_folder = False
    folder_top = ""

    if folder_names:
        print("  Existing folders under dremio-db:")
        for idx, name in enumerate(folder_names, 1):
            print(f"  [{idx:2d}]  dremio-db.{name}")
        print(f"  [ 0]  Create a new folder under dremio-db")
        print(f"  [ C]  Cancel")
        print(_DIV)

        while True:
            raw = _inp("Select folder: ").strip()
            if raw.upper() == "C":
                print("  Cancelled.")
                return None
            if raw == "0":
                new_name = _inp("  New folder name: ").strip().replace(" ", "_")
                if not new_name:
                    print("  Folder name cannot be empty.")
                    continue
                folder_top = new_name
                is_new_folder = True
                break
            if raw.isdigit() and 1 <= int(raw) <= len(folder_names):
                folder_top = folder_names[int(raw) - 1]
                break
            print(f"  Please enter 0–{len(folder_names)}, or C to cancel.")
    else:
        print("  (No folders found — enter folder name manually)")
        folder_top = _inp("Folder name inside dremio-db: ").strip().replace(" ", "_")
        is_new_folder = True

    # ── Create the new top-level folder immediately ───────────────────────────
    if is_new_folder:
        print(f"\n  Creating folder dremio-db/{folder_top} in main branch ...")
        result = create_dremio_folder("dremio-db", folder_top)
        if result["status"] != "SUCCESS":
            print(f"\n  ERROR: {result.get('error')}")
            retry = _inp("  Continue anyway? [y/n]: ", required=False)
            if retry.lower() not in ("y", "yes"):
                return None
        else:
            created = result.get("created", [])
            if created:
                print(f"  Folder created: dremio-db.{folder_top}  (main branch)")
            else:
                print(f"  Folder already exists: dremio-db.{folder_top}")

    # ── Step 2: enter sub-folder ──────────────────────────────────────────────
    _header(f"CREATE VDS  —  Step 2: Inside dremio-db.{folder_top}")
    print(f"  You are now inside: dremio-db.{folder_top}")
    sub = _inp(
        "  Sub-folder name (leave blank to use this folder directly): ",
        required=False,
    ).strip().replace(" ", "_")

    if sub:
        print(f"\n  Creating sub-folder dremio-db/{folder_top}/{sub} ...")
        result = create_dremio_folder("dremio-db", f"{folder_top}/{sub}")
        if result["status"] != "SUCCESS":
            print(f"  ERROR: {result.get('error')}")
            retry = _inp("  Continue without sub-folder? [y/n]: ", required=False)
            if retry.lower() in ("y", "yes"):
                sub = ""
            else:
                return None
        else:
            created = result.get("created", [])
            if created:
                print(f"  Sub-folder created: dremio-db.{folder_top}.{sub}  (main branch)")

    folder_path = f"{folder_top}/{sub}" if sub else folder_top
    current_path = f"dremio-db.{folder_path.replace('/', '.')}"

    # ── Step 3: VDS name ──────────────────────────────────────────────────────
    _header(f"CREATE VDS  —  Step 3: Name the VDS in {current_path}")
    suggested = _suggest_vds_name(summary, sql)
    print(f"  Current location : {current_path}")
    print(f"  Suggested VDS name (from ticket/SQL): {suggested}\n")
    vds_name = _inp(f"  VDS name [{suggested}]: ", required=False).strip() or suggested

    # ── Summary ───────────────────────────────────────────────────────────────
    full_path = f"{current_path}.{vds_name}"
    print(f"\n  VDS will be saved as:")
    print(f"    {full_path}")
    confirm = _inp("\n  Confirm? [y/n]: ", required=False)
    if confirm.lower() not in ("y", "yes", ""):
        print("  Cancelled.")
        return None

    return "dremio-db", folder_path, vds_name


# ── Dremio Agent phase ───────────────────────────────────────────────────────────

_DREMIO_MENU = """\

{div}
  DREMIO AGENT  --  Select Operation
{div}
  [1] Generate VDS query from ticket requirements  (recommended)
  [2] Preview existing table or view
  [3] Browse catalog folder / list views
  [4] Execute a SQL query
  [5] Validate SQL
  [6] Create Virtual Dataset (provide SQL manually)
  [7] Update existing VDS
  [8] Free-text query (ask the Dremio Agent anything)
  [0] Exit Dremio Agent
{div}"""


def _dremio_phase(reqs: TicketRequirements | None) -> str:
    """Interactive Dremio Agent menu. Returns approved VDS path (or empty string)."""
    agent = DremioAgent()
    approved_vds_path = ""

    while True:
        print(_DREMIO_MENU.format(div=_DIV))
        choice = _inp("Select option: ")

        if choice == "0":
            print("  Dremio Agent closed.")
            return approved_vds_path

        # ── [1] Generate VDS query ─────────────────────────────────────────────
        elif choice == "1":
            if not reqs:
                print("  No ticket requirements loaded — cannot generate query.")
                continue

            attempt = 0
            # Load rules once — truncate to keep well under the 10k TPM limit
            _rules_path = Path(__file__).resolve().parent.parent / "rules" / "dremio_query_rules.md"
            _rules = _rules_path.read_text(encoding="utf-8")[:6_000] if _rules_path.exists() else ""

            while True:
                attempt += 1
                print(f"\n  Generating SQL (attempt {attempt}) ...")
                prompt = _build_dremio_prompt(reqs)

                # Direct LLM call — bypasses ReAct agent so no tool schemas or
                # catalog index are sent. The prompt already contains all requirements.
                _retry_delays = [65, 65]
                raw_sql = ""
                for _att, _dly in enumerate(_retry_delays, start=1):
                    try:
                        _llm = get_llm()
                        _resp = _llm.invoke([
                            SystemMessage(content=(
                                "You are a Dremio SQL expert for ASL Airlines.\n"
                                "Return ONLY the SQL query — no explanation, no markdown fences.\n\n"
                                f"QUERY RULES (apply all):\n{_rules}"
                            )),
                            HumanMessage(content=prompt),
                        ])
                        raw_sql = str(_resp.content) if hasattr(_resp, "content") else str(_resp)
                        break
                    except Exception as _exc:
                        _e = str(_exc)
                        if ("rate_limit" in _e.lower() or "429" in _e) and _att <= len(_retry_delays):
                            print(f"\n  Rate limited — waiting {_dly}s ({_att}/{len(_retry_delays)}) ...")
                            time.sleep(_dly)
                        else:
                            raise

                result = {"agent_output": raw_sql}
                _pre_fix_sql = _strip_fences(raw_sql.strip())
                sql = _fix_dremio_sql(
                    _fix_reserved_keywords(
                        _remove_semicolons(
                            _pre_fix_sql
                        )
                    )
                )

                # If the deterministic Calcite-dialect repairs actually changed the
                # SQL, that is an auto-fix worth remembering for future runs.
                if sql and _pre_fix_sql and sql.strip() != _pre_fix_sql.strip():
                    _record_autofix(
                        error="Generated SQL was not valid Dremio/Calcite dialect "
                              "(semicolons / reserved words / unsupported constructs).",
                        fix="Applied automatic Calcite-dialect fix-ups "
                            "(_fix_dremio_sql / _fix_reserved_keywords / _remove_semicolons).",
                        context="Dremio SQL generation",
                    )

                if not sql:
                    print("\n  Agent returned empty SQL — retrying automatically ...\n")
                    continue

                # Catalog validation — catch wrong column names before Dremio API call
                catalog_issues = _validate_columns_against_catalog(sql)
                if catalog_issues:
                    print("\n  CATALOG WARNINGS — column names not found in catalog:")
                    for issue in catalog_issues:
                        print(f"  ⚠  {issue}")
                    print(
                        "\n  These columns may be wrong. "
                        "Use [2] to regenerate with corrections, or [1] to proceed anyway."
                    )

                _header(f"GENERATED SQL  (attempt {attempt}  |  {reqs.ticket_id})")
                print("\n" + sql + "\n")
                print(_DIV)
                print("  [1] Approve and save to file")
                print("  [2] Regenerate with feedback")
                print("  [3] Discard and return to menu")
                print(_DIV)

                regenerate = False
                while True:
                    sub = _inp("Select [1/2/3]: ")
                    if sub == "1":
                        # Save SQL to file first
                        sql_file = _save_sql(reqs, sql)
                        print(f"\n  SQL saved: {sql_file}\n")

                        # Ask whether to create VDS in Dremio
                        create_now = _inp("Create VDS in Dremio now? [y/n]: ", required=False)
                        if create_now.lower() in ("y", "yes"):
                            summary    = reqs.summary if reqs else ""
                            location = _pick_vds_location(summary, sql)
                            if location:
                                space, folder, vds_name = location
                                approved_vds_path = f"{space}.{folder.replace('/', '.')}.{vds_name}"
                                # Call tool directly — bypassing the agent gives us the real API error
                                from adl_automated_delivery_pipeline.tools.dremio_tools import (
                                    validate_sql_query,
                                    create_virtual_dataset,
                                    get_catalog_item,
                                    create_dremio_folder,
                                    execute_dremio_sql
                                )
                                
                                # Pre-check if VDS already exists
                                check_res = cast(Any, get_catalog_item).invoke({"path": approved_vds_path})
                                if check_res.get("status") == "SUCCESS":
                                    print(f"\n  A VDS named {vds_name} already exists at {approved_vds_path}.")
                                    action = _inp("  Do you want to [b]ackup, [d]elete, or [c]ancel? [b/d/c]: ")
                                    if action.lower() in ("b", "backup"):
                                        print("  Backing up existing VDS to a backup folder...")
                                        from datetime import datetime
                                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                        backup_name = f"{vds_name}_{ts}"
                                        backup_folder = f"{folder}/backup" if folder else "backup"
                                        
                                        print(f"  Ensuring backup folder {space}.{backup_folder.replace('/', '.')} exists...")
                                        create_dremio_folder(space=space, folder_path=backup_folder)
                                        
                                        existing = check_res["item"]
                                        old_sql = existing.get("sql", "")
                                        if old_sql:
                                            res_bak = cast(Any, create_virtual_dataset).invoke({
                                                "space": space,
                                                "folder_path": backup_folder,
                                                "vds_name": backup_name,
                                                "sql": old_sql
                                            })
                                            if res_bak.get("status") == "SUCCESS":
                                                print(f"  Old VDS successfully copied to backup as {backup_name}.")
                                                cast(Any, execute_dremio_sql).invoke({"sql": f'DROP VIEW {_quote_dremio_path(space, folder, vds_name)}'})
                                                print(f"  Old VDS removed from main folder.")
                                            else:
                                                print(f"  Failed to create backup copy: {res_bak.get('error')}")
                                        else:
                                            print("  Could not read SQL from old VDS.")
                                    elif action.lower() in ("d", "delete"):
                                        print("  Deleting existing VDS...")
                                        cast(Any, execute_dremio_sql).invoke({"sql": f'DROP VIEW {_quote_dremio_path(space, folder, vds_name)}'})
                                        print("  Old VDS deleted.")
                                    else:
                                        print("  VDS creation cancelled.")
                                        break

                                print(f"\n  Creating VDS at {approved_vds_path} ...")
                                # validate_sql_query / create_virtual_dataset imported above
                                # Validate first
                                if not sql.strip():
                                    print("\n  Cannot create VDS — SQL is empty.\n")
                                    break
                                val = cast(Any, validate_sql_query).invoke({"sql": sql})
                                if val.get("status") != "SUCCESS":
                                    print(f"\n  Validation FAILED: {val.get('error', val)}\n")
                                    print("  [1] Approve and save to file")
                                    print("  [2] Regenerate with feedback")
                                    print("  [3] Discard and return to menu")
                                    print(_DIV)
                                else:
                                    print("  SQL validated OK. Creating VDS ...")
                                    cres = cast(Any, create_virtual_dataset).invoke({
                                        "space": space,
                                        "folder_path": folder,
                                        "vds_name": vds_name,
                                        "sql": sql,
                                    })
                                    if cres.get("status") == "SUCCESS":
                                        print(f"  VDS created successfully!")
                                        print(f"  ID  : {cres.get('vds_id')}")
                                        print(f"  Path: {cres.get('vds_path')}\n")
                                        return approved_vds_path
                                    else:
                                        print(f"\n  VDS creation FAILED:")
                                        print(f"  {cres.get('error', cres)}\n")
                                        approved_vds_path = ""  # don't hand a non-existent VDS to the Qlik phase
                                        err_msg = cres.get("error")
                                        sep = "\n" if reqs.extra_notes else ""
                                        reqs.extra_notes += f"{sep}[Attempt {attempt} API Error]: {err_msg}. Please fix this SQL error."
                                        _record_autofix(
                                            error=f"Dremio VDS creation failed (attempt {attempt}): {err_msg}",
                                            fix="Fed the Dremio error back into the prompt and "
                                                "auto-regenerated the SQL.",
                                            context="Dremio VDS creation",
                                        )
                                        print("  Error noted. Regenerating ...\n")
                                        regenerate = True
                                        break
                    elif sub == "2":
                        feedback = _inp("Describe what needs to change:\n  > ")
                        sep = "\n" if reqs.extra_notes else ""
                        reqs.extra_notes += f"{sep}[Attempt {attempt} feedback]: {feedback}"
                        print("  Feedback noted. Regenerating ...\n")
                        regenerate = True
                        break
                    elif sub == "3":
                        print("  SQL discarded.")
                        regenerate = False
                        break
                    else:
                        print("  Please enter 1, 2, or 3.")

                if not regenerate:
                    break   # back to Dremio menu

        # ── [2] Preview ────────────────────────────────────────────────────────
        elif choice == "2":
            path = _inp("Full path (e.g. dremio-db.folder.view_name): ")
            rows = _inp("Rows to preview [20]: ", required=False) or "20"
            state = make_initial_state(user_id="workflow", role="admin", project_key=PROJECT,
                                       message=f"Preview {rows} rows from: {path}")
            result = cast(dict[str, Any], agent.run(state))
            print(f"\n{result.get('agent_output', '')}\n")

        # ── [3] Browse ─────────────────────────────────────────────────────────
        elif choice == "3":
            path = _inp("Folder path (e.g. dremio-db.amos_training): ")
            state = make_initial_state(user_id="workflow", role="admin", project_key=PROJECT,
                                       message=f"List all views, tables, and sub-folders inside: {path}")
            result = cast(dict[str, Any], agent.run(state))
            print(f"\n{result.get('agent_output', '')}\n")

        # ── [4] Execute SQL ────────────────────────────────────────────────────
        elif choice == "4":
            sql = _read_multiline("Enter SQL (blank line twice when done):")
            if sql:
                state = make_initial_state(user_id="workflow", role="admin", project_key=PROJECT,
                                           message=f"Execute this SQL query and show results:\n{sql}")
                result = cast(dict[str, Any], agent.run(state))
                print(f"\n{result.get('agent_output', '')}\n")

        # ── [5] Validate SQL ───────────────────────────────────────────────────
        elif choice == "5":
            sql = _read_multiline("Enter SQL to validate (blank line twice when done):")
            if sql:
                state = make_initial_state(user_id="workflow", role="admin", project_key=PROJECT,
                                           message=f"Validate this SQL and show the schema:\n{sql}")
                result = cast(dict[str, Any], agent.run(state))
                print(f"\n{result.get('agent_output', '')}\n")

        # ── [6] Create VDS ─────────────────────────────────────────────────────
        elif choice == "6":
            space  = _inp("Space/catalog (e.g. dremio-db): ")
            folder = _inp("Folder path inside space (e.g. amos_training/reports): ")
            name   = _inp("VDS name: ")
            sql    = _remove_semicolons(_read_multiline("Enter SQL definition (blank line twice when done):"))
            if sql:
                state = make_initial_state(
                    user_id="workflow", role="admin", project_key=PROJECT,
                    message=(
                        f"Validate and then create a Virtual Dataset named '{name}' "
                        f"in space '{space}' under folder '{folder}' with this SQL:\n{sql}"
                    ),
                )
                result = cast(dict[str, Any], agent.run(state))
                print(f"\n{result.get('agent_output', '')}\n")

        # ── [7] Update VDS ─────────────────────────────────────────────────────
        elif choice == "7":
            vds_id = _inp("VDS catalog ID: ")
            sql    = _remove_semicolons(_read_multiline("Enter new SQL definition (blank line twice when done):"))
            if sql:
                state = make_initial_state(
                    user_id="workflow", role="admin", project_key=PROJECT,
                    message=f"Update VDS with catalog ID '{vds_id}' using this SQL:\n{sql}",
                )
                result = cast(dict[str, Any], agent.run(state))
                print(f"\n{result.get('agent_output', '')}\n")

        # ── [8] Free-text ──────────────────────────────────────────────────────
        elif choice == "8":
            query = _inp("Your question for the Dremio Agent: ")
            state = make_initial_state(user_id="workflow", role="admin",
                                       project_key=PROJECT, message=query)
            result = cast(dict[str, Any], agent.run(state))
            print(f"\n{result.get('agent_output', '')}\n")

        else:
            print("  Invalid option — please choose 0-8.\n")


# ── QlikSense dashboard phase ───────────────────────────────────────────────────

def _fetch_ticket_meta(ticket_id: str) -> dict[str, Any]:
    """Fetch fresh ticket metadata from Jira: assignee, sprint, priority, state.

    Returns a dict with keys: assignee, sprint, priority, state, summary.
    Falls back gracefully if Jira is unreachable or sprint field is absent.
    """
    try:
        issue = _jira().issue(ticket_id, fields="summary,status,assignee,priority,customfield_10020")
        f = issue.fields
        # Sprint is stored in customfield_10020 as a list of sprint objects (JIRA Agile)
        sprint_name = "-"
        sprints: list[Any] = getattr(f, "customfield_10020", None) or []
        if sprints:
            # Pick the last (most recent) sprint in the list
            last = sprints[-1]
            sprint_name = getattr(last, "name", str(last))
        return {
            "assignee": f.assignee.displayName if f.assignee else "Unassigned",
            "sprint":   sprint_name,
            "priority": getattr(f.priority, "name", "-"),
            "state":    f.status.name,
            "summary":  f.summary,
        }
    except Exception as exc:
        logger.warning("Could not refresh ticket meta for %s: %s", ticket_id, exc)
        return {"assignee": "-", "sprint": "-", "priority": "-", "state": "-", "summary": ""}


def _qlik_preflight(reqs: TicketRequirements, vds_path: str) -> tuple[str, str, str] | None:
    """Show a full pre-flight briefing before the Qlik agent runs.

    Fetches fresh ticket data (assignee, sprint) from Jira, displays it together
    with the Dremio VDS path and the ticket's Qlik-relevant requirements, then
    prompts the user to confirm or override app name / space.

    Returns (vds_path, app_name, space) if the user confirms, or None to cancel.
    """
    _header("QLIK AGENT  —  PRE-FLIGHT CHECK")

    # ── Refresh ticket from Jira ──────────────────────────────────────────────
    print(f"  Fetching latest ticket data for {reqs.ticket_id} ...", end="", flush=True)
    meta = _fetch_ticket_meta(reqs.ticket_id)
    print(" done\n")

    # ── Jira ticket section ───────────────────────────────────────────────────
    print("  JIRA TICKET")
    print(f"  {'Ticket ID':<14}: {reqs.ticket_id}")
    print(f"  {'Summary':<14}: {meta['summary'] or reqs.summary}")
    print(f"  {'Assignee':<14}: {meta['assignee']}")
    print(f"  {'Sprint':<14}: {meta['sprint']}")
    print(f"  {'Priority':<14}: {meta['priority']}")
    print(f"  {'State':<14}: {meta['state']}")

    # ── Dremio VDS section ────────────────────────────────────────────────────
    print(f"\n  DREMIO VDS  (from Dremio Agent)")
    print(f"  {'VDS Path':<14}: {vds_path}")

    # ── Qlik requirements extracted from ticket ───────────────────────────────
    print(f"\n  OUTPUT FIELDS  (from Jira ticket — will become dashboard columns)")
    if reqs.output_fields:
        for f_def in reqs.output_fields:
            name = f_def.get("name", "?")
            desc = f_def.get("description", "")
            print(f"    - {name:<20} {desc}")
    else:
        print("    (none extracted from ticket — using VDS columns directly)")

    if reqs.filter_conditions:
        print(f"\n  FILTERS  (from Jira ticket)")
        for fc in reqs.filter_conditions:
            print(f"    - {fc}")

    print(f"\n  ACCEPTANCE CRITERIA  (from Jira ticket)")
    if reqs.acceptance_criteria:
        for ac in reqs.acceptance_criteria:
            print(f"    - {ac}")
    else:
        print("    (none listed in ticket)")

    print(_DIV)

    # ── Confirmation prompts ──────────────────────────────────────────────────
    vds_override = _inp(
        f"  VDS path [{vds_path}] (Enter to confirm or type override): ",
        required=False,
    ).strip()
    vds_to_use = vds_override or vds_path

    suggested_name = f"{reqs.ticket_id} - {reqs.summary.lstrip('[').split(']')[0].strip()}"
    name_input = _inp(
        f"  App name [{suggested_name}] (Enter to confirm): ",
        required=False,
    ).strip()
    app_name = name_input or suggested_name

    default_space = os.getenv("QLIK_SPACE", "development")
    space_input = _inp(
        f"  Qlik space [{default_space}] (Enter to confirm): ",
        required=False,
    ).strip()
    space = space_input or default_space

    print(f"\n  Ready to build dashboard:")
    print(f"    Ticket : {reqs.ticket_id}  ({meta['assignee']}  |  {meta['sprint']})")
    print(f"    VDS    : {vds_to_use}")
    print(f"    App    : {app_name}")
    print(f"    Space  : {space}")
    print(_DIV)

    confirm = _inp("  Proceed with Qlik dashboard creation? [y/n]: ", required=False)
    if confirm.lower() not in ("y", "yes", ""):
        print("  Qlik phase cancelled.")
        return None

    return vds_to_use, app_name, space


def _qlik_phase(reqs: TicketRequirements, vds_path: str) -> None:
    """Phase 4: Build a QlikSense Cloud dashboard from the approved Dremio VDS."""
    params = _qlik_preflight(reqs, vds_path)
    if params is None:
        return

    vds_to_use, app_name, space = params

    print(f"\n  Connecting to Dremio and building dashboard ...")
    print(f"    VDS   : {vds_to_use}")
    print(f"    App   : {app_name}")
    print(f"    Space : {space}\n")

    agent = QlikAgent()
    prompt = (
        f"Create an APU Health dashboard.\n"
        f"VDS Path: {vds_to_use}\n"
        f"App Name: {app_name}\n"
        f"Space: {space}\n\n"
        f"Ticket Transformations & Rules (Extract conditional formatting thresholds from here!):\n"
        f"{chr(10).join(reqs.transformations)}\n"
        f"{chr(10).join(reqs.acceptance_criteria)}\n"
        f"{reqs.raw_description}\n"
    )
    result = agent.run(prompt)

    if result.get("status") == "SUCCESS":
        _header("QLIK SENSE DASHBOARD READY")
        print(f"\n{result['output']}\n")
        print(_DIV)
    else:
        print(f"\n  Dashboard creation FAILED: {result.get('error', result)}")


# ── Create ticket path ──────────────────────────────────────────────────────────

def _create_ticket_flow() -> dict[str, Any] | None:
    """Guided ticket creation. Returns full ticket dict if user proceeds, else None."""
    import importlib
    # Resolve dynamically so the (heavily generic) create_agent signature is typed
    # as Any here — avoids partially-unknown-type noise from langchain's defaults.
    _create_agent = getattr(importlib.import_module("langchain.agents"), "create_agent")
    from adl_automated_delivery_pipeline.agents.jira_claude_agent import (
        get_ticket, search_tickets, create_ticket, add_comment,
        transition_ticket, get_my_tickets, lookup_user, reassign_ticket,
    )

    _header("CREATE NEW TICKET")
    summary  = _inp("Summary: ")
    desc     = _inp("Description (leave blank to skip): ", required=False)
    priority = _inp("Priority [Medium] (Low / Medium / High / Critical): ", required=False) or "Medium"
    itype    = _inp("Issue type [Task] (Task / Bug / Story): ", required=False) or "Task"
    assignee = _inp("Assignee email or name (leave blank to skip): ", required=False)

    query = f"Create a new {itype} in ADL with summary '{summary}', priority {priority}"
    if desc:
        query += f", description: {desc}"
    if assignee:
        query += f", assign to {assignee}"

    print("\n  Creating ticket via Jira Agent ...")
    llm = get_llm()
    tools = [get_ticket, search_tickets, create_ticket, add_comment,
             transition_ticket, get_my_tickets, lookup_user, reassign_ticket]
    executor: Any = _create_agent(
        model=llm, tools=tools,
        system_prompt=(
            "You are a Jira assistant for ASL Airlines, ADL project. "
            "Create the ticket exactly as instructed and return the ticket ID."
        ),
    )
    response = executor.invoke({"messages": [HumanMessage(content=query)]}, config={"recursion_limit": 10})
    msg = response["messages"][-1]
    print(f"\n  Agent: {getattr(msg, 'content', str(msg))}\n")

    proceed = _inp("Proceed to Dremio Agent for this ticket? [y/n]: ", required=False)
    if proceed.lower() in ("y", "yes"):
        ticket_id = _inp("Enter the new ticket ID (e.g. ADL-1700): ")
        ticket = _fetch_ticket(ticket_id.strip().upper())
        if ticket["status"] == "SUCCESS":
            return ticket
        print(f"  ERROR fetching ticket: {ticket.get('error')}")
    return None


# ── GitHub path ───────────────────────────────────────────────────────────────

def _github_flow() -> None:
    """Interactive chat with the GitHub Version Control Agent."""
    from adl_automated_delivery_pipeline.agents.github_agent import GitHubAgent
    
    _header("GITHUB VERSION CONTROL AGENT")
    print("  Type your request (e.g., 'commit all files and push' or 'check status')")
    print("  Type 'exit', 'quit', or '0' to return to main menu.")
    print(_DIV)
    
    agent = GitHubAgent()
    
    while True:
        try:
            req = _inp("\n  GitHub> ")
            if req.lower() in ("exit", "quit", "0"):
                break
            if not req.strip():
                continue
                
            print("  Agent is running...")
            res = agent.run(req)
            print(f"\n{res.get('output', 'Done.')}\n")
        except KeyboardInterrupt:
            break

def _post_workflow_git_check() -> None:
    import subprocess
    from adl_automated_delivery_pipeline.agents.github_agent import GitHubAgent
    
    print("\n  Validating local codebase against GitHub version ...", end="", flush=True)

    # Anchor git to the project root (where the .git lives) by searching upwards
    # from this file's location. This ensures the check works regardless of how
    # the pipeline was launched or installed.
    current_path = Path(__file__).resolve()
    repo_root = None
    for p in [current_path] + list(current_path.parents):
        if (p / ".git").exists():
            repo_root = str(p)
            break
            
    if not repo_root:
        print(" skipped.")
        print("  [Git] Not a git repository; skipping version check.\n")
        return

    # The git step is an optional convenience: skip cleanly when this directory
    # isn't a git repo or git isn't installed, rather than reporting a "failure".
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
    except FileNotFoundError:
        print(" skipped.")
        print("  [Git] git is not installed or not on PATH; skipping version check.\n")
        return

    if inside.returncode != 0 or inside.stdout.strip() != "true":
        print(" skipped.")
        print("  [Git] Not a git repository; skipping version check.\n")
        return

    try:
        status_out = subprocess.check_output(
            ["git", "status", "--porcelain"], text=True, cwd=repo_root
        ).strip()
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True, cwd=repo_root, stderr=subprocess.DEVNULL
            ).strip()
        except subprocess.CalledProcessError:
            branch = ""

        unpushed = ""
        if branch:
            try:
                unpushed = subprocess.check_output(
                    ["git", "log", f"origin/{branch}..{branch}", "--oneline"], text=True, cwd=repo_root
                ).strip()
            except subprocess.CalledProcessError:
                # No upstream tracking branch (e.g. origin/<branch> doesn't exist yet).
                pass

        if not status_out and not unpushed:
            print(" done.")
            print("  [Git] The version is same with respect to github code.\n")
            return

        print(" done.")
        print("  [Git] New changes detected (modified files or unpushed commits).")
        ans = _inp("  Would you like the GitHub Agent to commit and push these changes? [y/n]: ", required=False)
        if ans.lower() in ("y", "yes"):
            print("  Handing over to GitHub Agent...\n")
            agent = GitHubAgent()
            res = agent.run("Please check git status, add all changed files, commit them with a descriptive message summarizing the recent pipeline workflow, and push to the remote repository.")
            print(f"\n{res.get('output', 'Done.')}\n")
    except (subprocess.CalledProcessError, OSError) as e:
        print(f" (Failed to check git status: {e})")


# ── Headless dashboard runner ────────────────────────────────────────────────────

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
        ev.artifact("docx", doc_path.as_posix())
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


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    )

    # parents[3] = project root (file is <root>/src/<pkg>/workflows/<file>.py).
    root = Path(__file__).resolve().parents[3]
    for candidate in [
        root / "config.env",
        root / ".env",
    ]:
        if candidate.exists():
            load_dotenv(candidate, override=False)

    # ── Choose the Jira project to work on (default: ADL) ─────────────────────
    if not _pick_project():
        print("  Bye.")
        return

    print(f"\n{_DIV}")
    print(f"  ASL AIRLINES  --  {PROJECT} WORKFLOW  |  JIRA -> DOC -> DREMIO -> QLIK")
    print(_DIV)
    print("  [1]  Work on an existing ticket  (browse sprint)")
    print("  [2]  Browse backlog tickets")
    print("  [3]  Create a new ticket")
    print("  [4]  GitHub version control assistant")
    print("  [0]  Exit")
    print(_DIV)

    mode = _inp("Select option: ")

    if mode == "0":
        print("  Bye.")
        return

    ticket: dict[str, Any] | None = None
    reqs:   TicketRequirements | None = None

    # ── Mode 1: Sprint ticket ─────────────────────────────────────────────────
    if mode == "1":
        sprint = _pick_sprint()
        if not sprint:
            print("  Cancelled.")
            return

        print(f"\n  Fetching tickets for {sprint['name']} ...", end="", flush=True)
        issues = _fetch_sprint_issues(sprint["id"])
        if not issues:
            print(f"\n  No tickets found in {sprint['name']}. Exiting.")
            return
        print(f" done  ({len(issues)} tickets found)")

        assignee = _pick_assignee(issues, sprint["name"])
        if not assignee:
            print("  Cancelled.")
            return

        selected = _pick_ticket(issues, assignee)
        if not selected:
            print("  Cancelled.")
            return

        _header(f"SELECTED TICKET : {selected['id']}")
        print(f"  Sprint   : {sprint['name']}  [{sprint['state'].upper()}]")
        print(f"  Summary  : {selected['summary']}")
        print(f"  State    : {selected['state']}")
        print(f"  Priority : {selected['priority']}")
        print(f"  Assignee : {assignee}")
        print(_DIV)

        print(f"\n  Fetching full ticket details ...", end="", flush=True)
        ticket = _fetch_ticket(selected["id"])
        if ticket["status"] == "FAILED":
            print(f"\n  ERROR: {ticket.get('error')}")
            return
        print(" done")
        _transition_to_in_progress(selected["id"], selected["state"])
        print()

        reqs = _extract_requirements(ticket)
        if reqs is None:
            print("  Could not extract requirements. Exiting.")
            return
        _display_requirements(reqs)

        confirm = _inp("Proceed to Documentation + Dremio Agent? [y/n]: ")
        if confirm.lower() not in ("y", "yes"):
            print("  Workflow stopped.")
            return

    # ── Mode 2: Backlog ticket ────────────────────────────────────────────────
    elif mode == "2":
        print(f"\n  Fetching backlog tickets ...", end="", flush=True)
        issues = _fetch_backlog_issues()
        if not issues:
            print("\n  No backlog tickets found. Exiting.")
            return
        print(f" done  ({len(issues)} tickets found)")

        assignee = _pick_assignee(issues, "Backlog")
        if not assignee:
            print("  Cancelled.")
            return

        selected = _pick_ticket(issues, assignee)
        if not selected:
            print("  Cancelled.")
            return

        _header(f"SELECTED TICKET : {selected['id']}")
        print(f"  Source   : Backlog")
        print(f"  Summary  : {selected['summary']}")
        print(f"  State    : {selected['state']}")
        print(f"  Priority : {selected['priority']}")
        print(f"  Assignee : {assignee}")
        print(_DIV)

        print(f"\n  Fetching full ticket details ...", end="", flush=True)
        ticket = _fetch_ticket(selected["id"])
        if ticket["status"] == "FAILED":
            print(f"\n  ERROR: {ticket.get('error')}")
            return
        print(" done")
        _transition_to_in_progress(selected["id"], selected["state"])
        print()

        reqs = _extract_requirements(ticket)
        if reqs is None:
            print("  Could not extract requirements. Exiting.")
            return
        _display_requirements(reqs)

        confirm = _inp("Proceed to Documentation + Dremio Agent? [y/n]: ")
        if confirm.lower() not in ("y", "yes"):
            print("  Workflow stopped.")
            return

    # ── Mode 3: Create new ticket ─────────────────────────────────────────────
    elif mode == "3":
        ticket = _create_ticket_flow()
        if ticket:
            reqs = _extract_requirements(ticket)
            if reqs:
                _display_requirements(reqs)
                confirm = _inp("Proceed to Documentation + Dremio Agent? [y/n]: ")
                if confirm.lower() not in ("y", "yes"):
                    print("  Workflow stopped.")
                    return

    # ── Mode 4: GitHub ────────────────────────────────────────────────────────
    elif mode == "4":
        _github_flow()
        return

    else:
        print("  Invalid option. Exiting.")
        return

    # ── Phase 2: Documentation Agent ──────────────────────────────────────────
    if reqs:
        _doc_phase(reqs)
        doc_confirm = _inp("Proceed to Dremio Agent? [y/n]: ")
        if doc_confirm.lower() not in ("y", "yes"):
            print("  Workflow stopped after documentation.")
            _header("WORKFLOW COMPLETE")
            print(f"  Ticket  : {reqs.ticket_id}")
            print(_DIV)
            return
        # Cooldown reduced as per user request
        print("  Cooling down 5s to reset API rate limit window ...", end="", flush=True)
        time.sleep(5)
        print(" ready.\n")

    # ── Phase 3: Dremio Agent ─────────────────────────────────────────────────
    vds_path = _dremio_phase(reqs)

    # ── Phase 4: QlikSense Dashboard ──────────────────────────────────────────
    if vds_path:
        ans = _inp("Build QlikSense dashboard from this VDS? [y/n]: ", required=False)
        if ans.lower() in ("y", "yes", "1"):
            qlik_reqs = reqs
            sep_ans = _inp("Is there a separate JIRA ticket for Qlik? [y/n]: ", required=False)
            if sep_ans.lower() in ("y", "yes", "1"):
                print("\n  [1] Work on an existing Qlik ticket (browse sprint)")
                print("  [2] Browse Qlik backlog tickets")
                print("  [0] Cancel / use original ticket")
                q_mode = _inp("Select option: ")
                
                selected = None
                if q_mode == "1":
                    sprint = _pick_sprint()
                    if sprint:
                        issues = _fetch_sprint_issues(sprint["id"])
                        if issues:
                            assignee = _pick_assignee(issues, sprint["name"])
                            if assignee:
                                selected = _pick_ticket(issues, assignee)
                elif q_mode == "2":
                    issues = _fetch_backlog_issues()
                    if issues:
                        assignee = _pick_assignee(issues, "Backlog")
                        if assignee:
                            selected = _pick_ticket(issues, assignee)
                            
                if selected:
                    print(f"\n  Fetching full Qlik ticket details ...", end="", flush=True)
                    q_ticket = _fetch_ticket(selected["id"])
                    if q_ticket["status"] != "FAILED":
                        print(" done")
                        _transition_to_in_progress(selected["id"], selected["state"])
                        print()
                        q_reqs = _extract_requirements(q_ticket)
                        if q_reqs:
                            _display_requirements(q_reqs)
                            qlik_reqs = q_reqs
                    else:
                        print(f"\n  ERROR: {q_ticket.get('error')}")

            if qlik_reqs:
                _qlik_phase(qlik_reqs, vds_path)
            else:
                print("\n  Cannot build Qlik dashboard: No ticket requirements available.")

    _post_workflow_git_check()

    _header("WORKFLOW COMPLETE")
    print(f"  Ticket  : {reqs.ticket_id if reqs else 'N/A'}")
    if reqs and reqs.extra_notes:
        print(f"  Notes   : {reqs.extra_notes[:120]}")
    print(_DIV)


if __name__ == "__main__":
    main()