"""
JIRA -> DREMIO WORKFLOW  (Human-Governed)
==========================================
Phase 1 — Jira Agent   : Fetch ticket + extract requirements.
Phase 2 — Dremio Agent : Generate optimised SQL from requirements.

3 approval gates — nothing proceeds without human sign-off:

  GATE 1  [Jira Agent]   Ticket verified       -> approve to extract requirements
  GATE 2  [Jira Agent]   Requirements reviewed -> approve (+ optional notes) to generate SQL
  GATE 3  [Dremio Agent] SQL reviewed          -> approve to save  |  regenerate  |  reject

Usage:
    python adl_automated_delivery_pipeline/workflows/jira_to_dremio.py ADL-1684
    python adl_automated_delivery_pipeline/workflows/jira_to_dremio.py          # interactive prompt
"""
from __future__ import annotations

import sys
import os
from typing import Any, cast
import json
import logging
import uuid
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
from adl_automated_delivery_pipeline.state import make_initial_state
from adl_automated_delivery_pipeline.approval import ApprovalStore, cli_approval_gate
from adl_automated_delivery_pipeline.state import ApprovalRecord

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "generated_queries"
_DIVIDER    = "=" * 62


# ── Structured requirement model ───────────────────────────────────────────────

@dataclass
class TicketRequirements:
    ticket_id: str
    summary: str
    business_requirement: str
    source_database: str
    source_tables: list[str]
    output_fields: list[dict]
    transformations: list[str]
    filter_conditions: list[str]
    acceptance_criteria: list[str]
    extra_notes: str = ""
    raw_description: str = field(default="", repr=False)


# ── Approval gate helpers ──────────────────────────────────────────────────────

def _enqueue_and_gate(
    operation_type: str,
    operation_label: str,
    payload: dict,
    risk_level: str = "MEDIUM",
    session_id: str = "",
    trace_id: str = "",
) -> bool:
    """Enqueue an ApprovalRecord and invoke the CLI gate. Returns True if approved."""
    record = ApprovalRecord(
        approval_id=str(uuid.uuid4()),
        session_id=session_id,
        trace_id=trace_id,
        operation_type=operation_type,
        operation_label=operation_label,
        payload=payload,
        risk_level=risk_level,
        requires_role="admin",
        requested_by="workflow",
    )
    ApprovalStore.enqueue(record)
    return cli_approval_gate(record)


def _log_decision(
    operation_type: str,
    operation_label: str,
    payload: dict,
    approved: bool,
    risk_level: str = "MEDIUM",
    session_id: str = "",
    trace_id: str = "",
) -> None:
    """Persist an already-decided approval record to the audit trail (no prompt)."""
    record = ApprovalRecord(
        approval_id=str(uuid.uuid4()),
        session_id=session_id,
        trace_id=trace_id,
        operation_type=operation_type,
        operation_label=operation_label,
        payload=payload,
        risk_level=risk_level,
        requires_role="admin",
        requested_by="workflow",
    )
    ApprovalStore.enqueue(record)
    if approved:
        ApprovalStore.approve(record.approval_id, approved_by="cli_operator")
    else:
        ApprovalStore.reject(
            record.approval_id,
            rejected_by="cli_operator",
            reason="User rejected via workflow menu.",
        )


def _input(prompt: str) -> str:
    try:
        return input(f"  {prompt}").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Interrupted.")
        raise SystemExit(0)


# ── Jira helpers ───────────────────────────────────────────────────────────────

def _jira_client() -> Any:
    return JIRA(
        server=os.getenv("JIRA_INSTANCE_URL"),
        basic_auth=(str(os.getenv("JIRA_USERNAME")), str(os.getenv("JIRA_API_TOKEN"))),
    )


def _fetch_full_ticket(ticket_id: str) -> dict:
    try:
        issue = _jira_client().issue(ticket_id)
        f = issue.fields
        return {
            "status":      "SUCCESS",
            "id":          issue.key,
            "summary":     f.summary,
            "description": f.description or "",
            "state":       f.status.name,
            "priority":    getattr(f.priority, "name", "-"),
            "assignee":    f.assignee.displayName if f.assignee else "Unassigned",
            "reporter":    f.reporter.displayName if f.reporter else "-",
            "created":     f.created[:10],
            "updated":     f.updated[:10],
        }
    except JIRAError as e:
        return {"status": "FAILED", "error": e.text}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


# ── LLM extraction prompt ──────────────────────────────────────────────────────

_EXTRACTION_PROMPT = """You are a requirements analyst. Extract structured information from the Jira ticket description below.

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
- transformations must include date conversion rules, CASE WHEN logic, NULLIF patterns
- Return ONLY the JSON — no markdown, no explanation

Ticket description:
{description}
"""


def _extract_requirements_llm(description: str) -> dict:
    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content="You are a precise requirements analyst. Return only valid JSON."),
        HumanMessage(content=_EXTRACTION_PROMPT.format(description=description)),
    ])
    raw = str(cast(Any, response.content)).strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ── Dremio query prompt ────────────────────────────────────────────────────────

def _build_dremio_prompt(reqs: TicketRequirements) -> str:
    fields_block = "\n".join(
        f"  - {f['name']}: {f.get('description', '')}" for f in reqs.output_fields
    )
    tables_block = "\n".join(f"  - {t}" for t in reqs.source_tables)
    transforms   = "\n".join(f"  - {t}" for t in reqs.transformations)
    filters      = "\n".join(f"  - {c}" for c in reqs.filter_conditions) or "  - None specified"
    acceptance   = "\n".join(f"  - {a}" for a in reqs.acceptance_criteria)
    notes_block  = f"\n--- ADDITIONAL INSTRUCTIONS ---\n{reqs.extra_notes}" if reqs.extra_notes else ""

    return f"""Generate an optimised Dremio SQL query for the following requirement.
Apply ALL rules from the query rules document before writing any SQL.
Do NOT add LIMIT to the query — this will be used as a Virtual Dataset definition.
Add the VDS comment block at the top.

--- TICKET ---
Ticket ID : {reqs.ticket_id}
Summary   : {reqs.summary}

--- BUSINESS REQUIREMENT ---
{reqs.business_requirement}

--- SOURCE DATABASE ---
{reqs.source_database}

--- SOURCE TABLES ---
{tables_block}

--- REQUIRED OUTPUT FIELDS ---
{fields_block}

--- TRANSFORMATION RULES ---
{transforms}

--- FILTER CONDITIONS ---
{filters}

--- ACCEPTANCE CRITERIA ---
{acceptance}{notes_block}

Generate the complete, optimised SQL query now.
Return ONLY the SQL — no explanation before or after the query.
"""


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        return "\n".join(l for l in lines if not l.strip().startswith("```")).strip()
    return text


# ── Save output ────────────────────────────────────────────────────────────────

def _save_output(reqs: TicketRequirements, sql: str) -> Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    sql_path = _OUTPUT_DIR / f"{reqs.ticket_id}_{ts}.sql"
    sql_path.write_text(sql, encoding="utf-8")

    meta = {
        "ticket_id": reqs.ticket_id,
        "summary": reqs.summary,
        "generated_at": ts,
        "source_database": reqs.source_database,
        "source_tables": reqs.source_tables,
        "output_fields": reqs.output_fields,
        "transformations": reqs.transformations,
        "acceptance_criteria": reqs.acceptance_criteria,
        "extra_notes": reqs.extra_notes,
    }
    (_OUTPUT_DIR / f"{reqs.ticket_id}_{ts}.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return sql_path


# ── Workflow ───────────────────────────────────────────────────────────────────

def run_workflow(ticket_id: str) -> dict | None:
    ticket_id  = ticket_id.strip().upper()
    session_id = str(uuid.uuid4())
    trace_id   = str(uuid.uuid4())

    # ────────────────────────────────────────────────────────
    # PHASE 1 — JIRA AGENT
    # ────────────────────────────────────────────────────────
    print(f"\n{_DIVIDER}")
    print(f"  PHASE 1 — Jira Agent")
    print(_DIVIDER)
    print(f"  Fetching ticket {ticket_id} ...", end="", flush=True)

    ticket = _fetch_full_ticket(ticket_id)
    if ticket["status"] == "FAILED":
        print(f"\n  ERROR: {ticket.get('error')}")
        return None
    print(" done\n")

    # ── GATE 1: Ticket verification ───────────────────────────
    print(_DIVIDER)
    print("  [GATE 1 of 3]  Jira Agent — Ticket Verification")
    print(_DIVIDER)
    print(f"  Ticket ID  : {ticket['id']}")
    print(f"  Summary    : {ticket['summary']}")
    print(f"  State      : {ticket['state']}")
    print(f"  Priority   : {ticket['priority']}")
    print(f"  Assignee   : {ticket['assignee']}")
    print(f"  Reporter   : {ticket['reporter']}")
    print(f"  Created    : {ticket['created']}   Updated: {ticket['updated']}")
    print(f"  Description: {len(ticket['description'])} characters")
    print(_DIVIDER)

    approved = _enqueue_and_gate(
        operation_type="JIRA_TICKET_VERIFICATION",
        operation_label=f"Proceed with requirements extraction for {ticket_id}?",
        payload={"ticket_id": ticket_id, "summary": ticket["summary"], "state": ticket["state"]},
        risk_level="LOW",
        session_id=session_id,
        trace_id=trace_id,
    )
    if not approved:
        print("  Workflow stopped at Gate 1.")
        return None

    # ── Extract requirements via LLM ──────────────────────────
    desc = ticket["description"]
    if not desc:
        print("  ERROR: Ticket has no description — cannot extract requirements.")
        return None

    print(f"\n  Extracting requirements via LLM ...", end="", flush=True)
    try:
        parsed = _extract_requirements_llm(desc)
    except (json.JSONDecodeError, Exception) as e:
        print(f"\n  ERROR extracting requirements: {e}")
        return None
    print(" done")

    reqs = TicketRequirements(
        ticket_id=ticket_id,
        summary=ticket["summary"],
        business_requirement=parsed.get("business_requirement", ""),
        source_database=parsed.get("source_database", ""),
        source_tables=parsed.get("source_tables", []),
        output_fields=parsed.get("output_fields", []),
        transformations=parsed.get("transformations", []),
        filter_conditions=parsed.get("filter_conditions", []),
        acceptance_criteria=parsed.get("acceptance_criteria", []),
        raw_description=desc,
    )

    # ── GATE 2: Requirements review ───────────────────────────
    print(f"\n{_DIVIDER}")
    print("  [GATE 2 of 3]  Jira Agent — Requirements Review")
    print(_DIVIDER)
    print(f"\n  Business Requirement:")
    print(f"    {reqs.business_requirement}\n")
    print(f"  Source Database : {reqs.source_database}")
    print(f"  Source Tables ({len(reqs.source_tables)}):")
    for t in reqs.source_tables:
        print(f"    - {t}")
    print(f"\n  Output Fields ({len(reqs.output_fields)}):")
    for f in reqs.output_fields:
        print(f"    - {f['name']}: {f.get('description','')}")
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
    print(f"\n{_DIVIDER}")
    print("  Options:")
    print("    [1] Approve — pass requirements to Dremio Agent as-is")
    print("    [2] Approve with notes — add extra instructions for the query")
    print("    [3] Reject — stop workflow")
    print(_DIVIDER)

    while True:
        choice = _input("Select [1/2/3]: ")
        if choice == "1":
            _log_decision(
                operation_type="REQUIREMENTS_APPROVED",
                operation_label=f"Requirements approved for {ticket_id} — no extra notes",
                payload={
                    "ticket_id": ticket_id,
                    "source_database": reqs.source_database,
                    "source_tables": reqs.source_tables,
                    "field_count": len(reqs.output_fields),
                },
                approved=True,
                risk_level="LOW",
                session_id=session_id,
                trace_id=trace_id,
            )
            break
        elif choice == "2":
            notes = _input("Enter additional instructions for the query:\n  > ")
            reqs.extra_notes = notes
            print(f"\n  Notes recorded: {notes}")
            _log_decision(
                operation_type="REQUIREMENTS_APPROVED_WITH_NOTES",
                operation_label=f"Requirements approved with notes for {ticket_id}",
                payload={
                    "ticket_id": ticket_id,
                    "source_database": reqs.source_database,
                    "source_tables": reqs.source_tables,
                    "extra_notes": notes,
                },
                approved=True,
                risk_level="LOW",
                session_id=session_id,
                trace_id=trace_id,
            )
            break
        elif choice == "3":
            print("  Workflow stopped at Gate 2.")
            return None
        else:
            print("  Please enter 1, 2, or 3.")

    # ────────────────────────────────────────────────────────
    # PHASE 2 — DREMIO AGENT
    # ────────────────────────────────────────────────────────
    print(f"\n{_DIVIDER}")
    print(f"  PHASE 2 — Dremio Agent")
    print(_DIVIDER)

    agent  = DremioAgent()
    sql    = ""
    attempt = 0

    while True:
        attempt += 1
        print(f"\n  Generating SQL (attempt {attempt}) ...\n")

        prompt = _build_dremio_prompt(reqs)
        state  = make_initial_state(
            user_id="workflow",
            role="admin",
            project_key=ticket_id.split("-")[0],
            message=prompt,
        )
        result = agent.run(state)
        sql = _strip_fences(str(result.get("agent_output", "")).strip())

        # ── GATE 3: SQL review ────────────────────────────────
        print(f"\n{_DIVIDER}")
        print(f"  [GATE 3 of 3]  Dremio Agent — Generated SQL Review (attempt {attempt})")
        print(_DIVIDER)
        print("\n" + sql + "\n")
        print(_DIVIDER)
        print("  Options:")
        print("    [1] Approve — save SQL to file")
        print("    [2] Regenerate — ask agent to regenerate with additional feedback")
        print("    [3] Reject — discard and stop workflow")
        print(_DIVIDER)

        while True:
            choice = _input("Select [1/2/3]: ")
            if choice == "1":
                _log_decision(
                    operation_type="SQL_APPROVED",
                    operation_label=f"Generated SQL approved for {ticket_id}",
                    payload={
                        "ticket_id": ticket_id,
                        "attempt": attempt,
                        "sql_lines": len(sql.splitlines()),
                    },
                    approved=True,
                    risk_level="MEDIUM",
                    session_id=session_id,
                    trace_id=trace_id,
                )
                break
            elif choice == "2":
                feedback = _input("Describe what needs to change:\n  > ")
                if reqs.extra_notes:
                    reqs.extra_notes += f"\n[Regeneration feedback attempt {attempt}]: {feedback}"
                else:
                    reqs.extra_notes = f"[Regeneration feedback]: {feedback}"
                print(f"\n  Feedback noted. Regenerating...\n")
                break
            elif choice == "3":
                _log_decision(
                    operation_type="SQL_REJECTED",
                    operation_label=f"Generated SQL rejected for {ticket_id}",
                    payload={"ticket_id": ticket_id, "attempt": attempt},
                    approved=False,
                    risk_level="LOW",
                    session_id=session_id,
                    trace_id=trace_id,
                )
                print("  Workflow stopped at Gate 3.")
                return None
            else:
                print("  Please enter 1, 2, or 3.")

        if choice == "1":
            break   # approved — exit generation loop

    # ── Save ──────────────────────────────────────────────────
    sql_path = _save_output(reqs, sql)

    print(f"\n{_DIVIDER}")
    print(f"  WORKFLOW COMPLETE")
    print(_DIVIDER)
    print(f"  Ticket      : {ticket_id}")
    print(f"  SQL saved   : {sql_path}")
    print(f"  Attempts    : {attempt}")
    print(f"  Session ID  : {session_id}")
    print(_DIVIDER)

    return {
        "ticket_id": ticket_id,
        "requirements": reqs,
        "generated_sql": sql,
        "output_file": str(sql_path),
        "session_id": session_id,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    )

    # parents[3] = project root (file is <root>/src/<pkg>/workflows/<file>.py).
    root = Path(__file__).resolve().parents[3]
    for candidate in [root / "config.env", root / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            break

    print("\n" + _DIVIDER)
    print("  JIRA -> DREMIO WORKFLOW  |  Human-Governed  |  ASL Airlines")
    print(_DIVIDER)

    if len(sys.argv) > 1:
        ticket_id = sys.argv[1]
    else:
        ticket_id = _input("Enter Jira ticket ID (e.g. ADL-1684): ")

    if not ticket_id:
        print("  No ticket ID provided. Exiting.")
        return

    run_workflow(ticket_id)


if __name__ == "__main__":
    main()

