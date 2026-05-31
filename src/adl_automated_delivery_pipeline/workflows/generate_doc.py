"""Non-interactive Technical Implementation Document generator.

Fetches a Jira ticket, extracts structured requirements (Jira Agent -> Claude),
and runs the Documentation Agent to produce a .docx. No menus, no mutations to
Jira or Dremio — it only reads the ticket and writes a local Word document.

The document is written to ``<cwd>/Project Documentation/`` (run from the
project root). Exposed as the ``adl-doc`` console script:

    adl-doc ADL-1721
    # or: python -m adl_automated_delivery_pipeline.workflows.generate_doc ADL-1721
"""

from __future__ import annotations

import argparse
import logging

from adl_automated_delivery_pipeline.agents.doc_agent import DocumentationAgent
from adl_automated_delivery_pipeline.workflows.adl_automated_delivery_pipeline import (
    _extract_requirements,
    _fetch_ticket,
)

logger = logging.getLogger("generate_doc")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="adl-doc",
        description="Generate a Technical Implementation Document (.docx) for a Jira ticket.",
    )
    parser.add_argument("ticket", help="Jira ticket key, e.g. ADL-1721")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    )

    print(f"Fetching ticket {args.ticket} ...")
    ticket = _fetch_ticket(args.ticket)
    if ticket.get("status") != "SUCCESS":
        print(f"  Failed to fetch ticket: {ticket.get('error')}")
        return 1
    print(f"  {ticket['id']}: {ticket['summary']}  [{ticket['state']}]")

    print("Extracting requirements (Jira Agent -> Claude) ...")
    reqs = _extract_requirements(ticket)
    if reqs is None:
        print("  Requirement extraction failed.")
        return 1

    print("Generating Technical Implementation Document (Documentation Agent -> Claude) ...")
    path = DocumentationAgent().generate(reqs)
    print(f"\nDocument saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
