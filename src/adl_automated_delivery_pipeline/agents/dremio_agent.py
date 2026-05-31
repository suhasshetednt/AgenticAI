"""Dremio Agent — SQL execution and Virtual Dataset management for ASL Airlines."""
from __future__ import annotations

import sys
import logging
from pathlib import Path

# Allow direct execution: python adl_automated_delivery_pipeline/agents/dremio_agent.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from adl_automated_delivery_pipeline.agents.base import BaseJiraAgent
from adl_automated_delivery_pipeline.config import settings
from adl_automated_delivery_pipeline.state import make_initial_state

_RULES_FILE = Path(__file__).resolve().parent.parent / "rules" / "dremio_query_rules.md"


def _load_rules() -> str:
    """Load query rules from file; return empty string if missing."""
    try:
        return _RULES_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""


def _load_catalog_index() -> str:
    """Load compact table-name index from the ASL data catalog for the system prompt."""
    try:
        from adl_automated_delivery_pipeline.tools.catalog_loader import format_catalog_index
        return format_catalog_index()
    except Exception as exc:
        logger.warning("Could not load catalog index: %s", exc)
        return "(catalog index unavailable)"

logger = logging.getLogger(__name__)


class DremioAgent(BaseJiraAgent):
    """Agent for querying AMOS data via Dremio and managing Virtual Datasets.

    Handles SQL execution, VDS creation/update, and catalog browsing against
    the amos_postgres source on Dremio Cloud (EU).
    """

    name = "dremio_agent"

    def _register_tools(self) -> list:
        from adl_automated_delivery_pipeline.tools.dremio_tools import (
            execute_dremio_sql,
            validate_sql_query,
            create_virtual_dataset,
            update_virtual_dataset,
            get_catalog_item,
            list_catalog_children,
            list_dremio_sources,
            preview_dataset,
            search_catalog,
        )
        return [
            execute_dremio_sql,
            validate_sql_query,
            create_virtual_dataset,
            update_virtual_dataset,
            get_catalog_item,
            list_catalog_children,
            list_dremio_sources,
            preview_dataset,
            search_catalog,
        ]

    def _system_prompt(self) -> str:
        catalog = settings.DREMIO_CATALOG_NAME or "dremio-db"
        rules = _load_rules()
        catalog_index = _load_catalog_index()
        return f"""You are a Dremio SQL and Virtual Dataset expert for ASL Airlines.
You help data engineers and analysts query AMOS PostgreSQL data via Dremio, build VDS views, and troubleshoot SQL.

Dremio environment:
- Default catalog name: {catalog}  (use this as the top-level prefix when browsing)
- Default AMOS source: amos_postgres  (schema prefix: amos)
- Dremio Cloud region: EU

When a user asks about views, tables, or folders under a path like "{catalog}.some_folder":
1. Call list_catalog_children with the full path — this is the correct tool for browsing folder contents.
2. Do NOT guess or invent results — always call the tool first.
3. Paths may be written with quotes (e.g. "dremio-db"."folder") — the tools handle quote-stripping automatically.

BEFORE WRITING ANY SQL:
- Call search_catalog(keyword) to find exact table and column names from the ASL data catalog.
- Use the table names exactly as they appear in the catalog (case-sensitive).
- If unsure which table to use, search by business concept (e.g. "aircraft", "flight", "employee").
- If search_catalog returns no match, the table likely exists in amos_postgres but is not yet catalogued.
  In that case, use the schema.table name from the ticket requirements and PROCEED with SQL generation.
  Do NOT refuse to generate SQL just because a table is absent from the catalog.

Available tools:
- search_catalog         — search ASL catalog for exact table/column names (USE BEFORE WRITING SQL)
- execute_dremio_sql     — run any SQL and return results
- validate_sql_query     — validate syntax and schema (LIMIT 0, fast)
- list_catalog_children  — list views/tables/folders inside a catalog path (USE THIS FOR BROWSING)
- get_catalog_item       — inspect metadata of a specific catalog item
- list_dremio_sources    — list all top-level sources and spaces
- create_virtual_dataset — create a new VDS in a Dremio space/folder
- update_virtual_dataset — update the SQL of an existing VDS by catalog ID
- preview_dataset        — preview sample rows from any table or VDS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{catalog_index}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY QUERY RULES — read and apply before every query
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{rules}
"""


_MENU = """
╔══════════════════════════════════════════════════════╗
║           DREMIO AGENT — ASL Airlines                ║
╠══════════════════════════════════════════════════════╣
║  1. List all sources & spaces                        ║
║  2. Browse folder / list views                       ║
║  3. Preview a view or table                          ║
║  4. Execute SQL query                                ║
║  5. Validate SQL query                               ║
║  6. Create Virtual Dataset (VDS)                     ║
║  7. Update existing VDS                              ║
║  8. Free-text query (ask anything)                   ║
║  0. Exit                                             ║
╚══════════════════════════════════════════════════════╝"""


def _prompt(label: str, required: bool = True) -> str:
    while True:
        val = input(f"  {label}: ").strip()
        if val or not required:
            return val
        print("  (required — please enter a value)")


def _run(agent: DremioAgent, query: str) -> None:
    state = make_initial_state(user_id="cli", role="admin", project_key="ADL", message=query)
    result = agent.run(state)
    print("\n" + str(result.get("agent_output", "")) + "\n")


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,          # suppress INFO noise in menu mode
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )

    # Direct CLI query (non-interactive)
    if len(sys.argv) > 1:
        logging.getLogger().setLevel(logging.INFO)
        agent = DremioAgent()
        query = " ".join(sys.argv[1:])
        state = make_initial_state(user_id="cli", role="admin", project_key="ADL", message=query)
        result = agent.run(state)
        print(result.get("agent_output", ""))
        return

    agent = DremioAgent()

    while True:
        print(_MENU)
        try:
            choice = input("  Select option: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if choice == "0":
            print("Bye.")
            break

        elif choice == "1":
            _run(agent, "List all top-level sources and spaces in the Dremio catalog.")

        elif choice == "2":
            path = _prompt("Folder path (e.g. dremio-db.amos_training_status_report)")
            _run(agent, f"List all views, tables, and sub-folders inside: {path}")

        elif choice == "3":
            path = _prompt("Full path to view/table (e.g. dremio-db.folder.view_name)")
            rows = _prompt("Number of rows to preview [default 20]", required=False) or "20"
            _run(agent, f"Preview {rows} rows from: {path}")

        elif choice == "4":
            print("  Enter SQL (press Enter twice when done):")
            lines = []
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            sql = "\n".join(lines).strip()
            if sql:
                _run(agent, f"Execute this SQL query and show the results:\n{sql}")

        elif choice == "5":
            print("  Enter SQL to validate (press Enter twice when done):")
            lines = []
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            sql = "\n".join(lines).strip()
            if sql:
                _run(agent, f"Validate this SQL query and show the schema:\n{sql}")

        elif choice == "6":
            print("\n  -- Create Virtual Dataset --")
            space       = _prompt("Space / catalog (e.g. dremio-db)")
            folder      = _prompt("Folder path inside space (e.g. amos_training/reports)")
            name        = _prompt("VDS name")
            print("  Enter SQL definition (press Enter twice when done):")
            lines = []
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            sql = "\n".join(lines).strip()
            if sql:
                _run(
                    agent,
                    f"Validate and then create a Virtual Dataset named '{name}' "
                    f"in space '{space}' under folder '{folder}' with this SQL:\n{sql}",
                )

        elif choice == "7":
            print("\n  -- Update Existing VDS --")
            vds_id = _prompt("VDS catalog ID")
            print("  Enter new SQL definition (press Enter twice when done):")
            lines = []
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            sql = "\n".join(lines).strip()
            if sql:
                _run(agent, f"Update the VDS with catalog ID '{vds_id}' using this SQL:\n{sql}")

        elif choice == "8":
            query = _prompt("Your question")
            _run(agent, query)

        else:
            print("  Invalid option — please choose 0–8.\n")


if __name__ == "__main__":
    main()
