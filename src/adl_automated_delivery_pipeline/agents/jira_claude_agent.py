"""
JIRA AGENT — Claude Edition
Token-optimised Jira assistant for ADL project.
LLM: Claude (Anthropic) | Auth: config.env
"""

import os
import sys
import logging
from typing import Any
from jira import JIRA, JIRAError
from langchain_core.tools import tool
from langchain.agents import create_agent

from adl_automated_delivery_pipeline.config import settings
from adl_automated_delivery_pipeline.llm import make_claude

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

DEFAULT_PROJECT = "ADL"
MAX_RESULTS = 5       # keep LLM context small
DESC_LIMIT = 300      # chars — avoids pasting walls of text into LLM context

# ─── Environment ─────────────────────────────────────────────────────────────

def load_environment() -> dict[str, str]:
    """Validate that required credentials are present.

    Environment files are discovered and loaded centrally by
    ``adl_automated_delivery_pipeline.config`` (imported at module load), which
    searches the project root, the package, and the agents sub-package. This
    function only validates that the required keys resolved.
    """
    required: dict[str, str] = {
        "JIRA_INSTANCE_URL":  "Jira instance URL",
        "JIRA_USERNAME":      "Jira email",
        "JIRA_API_TOKEN":     "Jira API token",
        "ANTHROPIC_API_KEY":  "Anthropic API key",
    }

    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.error(
            "Missing required env vars: %s. Set them in config.env at the project root.",
            ", ".join(missing),
        )
        sys.exit(1)

    logger.info("Environment OK — project=%s  model=%s", DEFAULT_PROJECT, settings.CLAUDE_MODEL)
    return {k: os.getenv(k) for k in required}  # type: ignore[return-value]

# ─── Jira helpers ────────────────────────────────────────────────────────────

def _jira() -> Any:
    """Create a fresh Jira connection (stateless per-tool pattern)."""
    return JIRA(
        server=os.getenv("JIRA_INSTANCE_URL"),
        basic_auth=(str(os.getenv("JIRA_USERNAME")), str(os.getenv("JIRA_API_TOKEN"))),
    )

def _trim(text: str | None, limit: int = DESC_LIMIT) -> str:
    if not text:
        return ""
    return (text[:limit] + "…") if len(text) > limit else text

# ─── Tools (token-optimised outputs) ─────────────────────────────────────────

@tool
def get_ticket(ticket_id: str) -> dict[str, Any]:
    """Fetch a Jira ticket. Returns only essential fields."""
    try:
        issue = _jira().issue(ticket_id)
        f = issue.fields
        return {
            "status":      "SUCCESS",
            "id":          issue.key,
            "type":        f.issuetype.name,
            "summary":     f.summary,
            "description": _trim(f.description),
            "state":       f.status.name,
            "priority":    getattr(f.priority, "name", "—"),
            "assignee":    f.assignee.displayName if f.assignee else "Unassigned",
            "reporter":    f.reporter.displayName if f.reporter else "—",
            "created":     f.created[:10],
            "updated":     f.updated[:10],
            "comments":    len(f.comment.comments) if f.comment else 0,
        }
    except JIRAError as e:
        return {"status": "FAILED", "error": e.text}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def search_tickets(jql: str, limit: int = MAX_RESULTS) -> dict[str, Any]:
    """Search Jira with a JQL query. Returns up to 5 results by default."""
    try:
        issues = _jira().search_issues(jql, maxResults=min(limit, 10))
        return {
            "status": "SUCCESS",
            "count":  len(issues),
            "issues": [
                {
                    "id":       i.key,
                    "summary":  i.fields.summary[:120],
                    "state":    i.fields.status.name,
                    "assignee": i.fields.assignee.displayName if i.fields.assignee else "—",
                    "priority": getattr(i.fields.priority, "name", "—"),
                    "type":     i.fields.issuetype.name,
                }
                for i in issues
            ],
        }
    except JIRAError as e:
        return {"status": "FAILED", "error": e.text}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def create_ticket(
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    priority: str = "Medium",
    assignee_account_id: str = "",
) -> dict[str, Any]:
    """Create a ticket in the ADL project."""
    try:
        fields: dict[str, Any] = {
            "project":   {"key": DEFAULT_PROJECT},
            "issuetype": {"name": issue_type},
            "summary":   summary,
            "priority":  {"name": priority},
        }
        if description:
            fields["description"] = description
        if assignee_account_id:
            fields["assignee"] = {"accountId": assignee_account_id}

        issue = _jira().create_issue(fields=fields)
        return {
            "status": "SUCCESS",
            "id":     issue.key,
            "url":    f"{os.getenv('JIRA_INSTANCE_URL')}/browse/{issue.key}",
        }
    except JIRAError as e:
        return {"status": "FAILED", "error": e.text}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def add_comment(ticket_id: str, comment: str) -> dict[str, Any]:
    """Add a comment to a Jira ticket."""
    try:
        _jira().add_comment(ticket_id, comment)
        return {"status": "SUCCESS", "ticket": ticket_id}
    except JIRAError as e:
        return {"status": "FAILED", "error": e.text}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def transition_ticket(ticket_id: str, transition_name: str) -> dict[str, Any]:
    """Move a ticket to a new status. Use exact transition name e.g. 'In Progress', 'Done'."""
    try:
        jira = _jira()
        available = jira.transitions(ticket_id)
        match = next(
            (t for t in available if t["name"].lower() == transition_name.lower()),
            None,
        )
        if not match:
            return {
                "status":    "FAILED",
                "error":     f"Transition '{transition_name}' not found.",
                "available": [t["name"] for t in available],
            }
        jira.transition_issue(ticket_id, match["id"])
        return {"status": "SUCCESS", "ticket": ticket_id, "new_status": transition_name}
    except JIRAError as e:
        return {"status": "FAILED", "error": e.text}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def get_my_tickets(limit: int = MAX_RESULTS) -> dict[str, Any]:
    """Get open tickets assigned to the current user (from JIRA_USERNAME)."""
    try:
        username = os.getenv("JIRA_USERNAME", "")
        jql = f'project = {DEFAULT_PROJECT} AND assignee = "{username}" AND statusCategory != Done ORDER BY updated DESC'
        issues = _jira().search_issues(jql, maxResults=min(limit, 10))
        return {
            "status": "SUCCESS",
            "count":  len(issues),
            "issues": [
                {
                    "id":       i.key,
                    "summary":  i.fields.summary[:120],
                    "state":    i.fields.status.name,
                    "priority": getattr(i.fields.priority, "name", "—"),
                    "updated":  i.fields.updated[:10],
                }
                for i in issues
            ],
        }
    except JIRAError as e:
        return {"status": "FAILED", "error": e.text}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def reassign_ticket(ticket_id: str, assignee_account_id: str) -> dict[str, Any]:
    """Change the assignee of an existing Jira ticket. Use lookup_user first to get the accountId."""
    try:
        _jira().assign_issue(ticket_id, assignee_account_id)
        return {"status": "SUCCESS", "ticket": ticket_id, "new_assignee_account_id": assignee_account_id}
    except JIRAError as e:
        return {"status": "FAILED", "error": e.text}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


@tool
def lookup_user(email_or_name: str) -> dict[str, Any]:
    """Look up a Jira user's accountId by email address or display name.
    Always call this before create_ticket when you have an email/name but no accountId."""
    try:
        users = _jira().search_users(query=email_or_name)
        if not users:
            return {"status": "FAILED", "error": f"No user found for '{email_or_name}'"}
        return {
            "status": "SUCCESS",
            "users": [
                {
                    "account_id":   u.accountId,
                    "display_name": u.displayName,
                    "email":        getattr(u, "emailAddress", "—"),
                }
                for u in users[:5]
            ],
        }
    except JIRAError as e:
        return {"status": "FAILED", "error": e.text}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}

# ─── System prompt (compact — every token counts) ────────────────────────────

_SYSTEM_PROMPT = (
    "You are a Jira assistant for ASL Airlines, ADL project (aslairlines.atlassian.net). "
    "Default project: ADL. "
    "Use tools to answer — never invent ticket data. "
    "To change the assignee of an existing ticket, use reassign_ticket — never create a new ticket for this. "
    "When you need an accountId from an email or name, call lookup_user first. "
    "Reply concisely; skip filler phrases."
)

# ─── Menu helpers ─────────────────────────────────────────────────────────────

_MENU = """
┌─────────────────────────────────────────────────┐
│          ADL Jira Agent  —  Main Menu           │
├─────────────────────────────────────────────────┤
│  1.  View a ticket                              │
│  2.  Search tickets                             │
│  3.  Create a new ticket                        │
│  4.  Reassign a ticket                          │
│  5.  Change ticket status                       │
│  6.  Add a comment to a ticket                  │
│  7.  My open tickets                            │
│  8.  Free-text query                            │
│  0.  Exit                                       │
└─────────────────────────────────────────────────┘"""

_STATUSES = ["To Do", "In Progress", "Done", "On Hold", "Ready for Review"]


def _prompt(label: str) -> str:
    """Read a line from stdin, stripping whitespace."""
    try:
        return input(f"  {label}: ").strip()
    except (KeyboardInterrupt, EOFError):
        raise


def _build_guided_query() -> str | None:
    """Show menu, collect inputs, return a natural-language query for the agent."""
    print(_MENU)
    choice = _prompt("Select option").lower()

    if choice in ("0", "exit", "quit", "q"):
        return "EXIT"

    if choice == "1":
        tid = _prompt("Ticket ID (e.g. ADL-1684)")
        return f"Get ticket {tid}"

    if choice == "2":
        q = _prompt("Search query or JQL")
        return f"Search tickets: {q}"

    if choice == "3":
        summary = _prompt("Summary")
        desc    = _prompt("Description (leave blank to skip)")
        prio    = _prompt("Priority [Medium] (Low / Medium / High / Critical)") or "Medium"
        itype   = _prompt("Issue type [Task] (Task / Bug / Story)") or "Task"
        assignee = _prompt("Assignee email or name (leave blank to skip)")
        query = f"Create a new {itype} in ADL with summary '{summary}', priority {prio}"
        if desc:
            query += f", description: {desc}"
        if assignee:
            query += f", assign to {assignee}"
        return query

    if choice == "4":
        tid      = _prompt("Ticket ID (e.g. ADL-1684)")
        assignee = _prompt("New assignee email or name")
        return f"Reassign ticket {tid} to {assignee}"

    if choice == "5":
        tid = _prompt("Ticket ID (e.g. ADL-1684)")
        print("  Statuses: " + " | ".join(f"{i+1}. {s}" for i, s in enumerate(_STATUSES)))
        raw = _prompt("New status (number or name)")
        if raw.isdigit() and 1 <= int(raw) <= len(_STATUSES):
            status = _STATUSES[int(raw) - 1]
        else:
            status = raw
        return f"Move ticket {tid} to '{status}'"

    if choice == "6":
        tid     = _prompt("Ticket ID (e.g. ADL-1684)")
        comment = _prompt("Comment text")
        return f"Add comment to {tid}: {comment}"

    if choice == "7":
        return "Show my open tickets"

    if choice == "8":
        return _prompt("Your request")

    print("  Invalid option — please try again.")
    return None


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    load_environment()

    llm = make_claude(model=settings.CLAUDE_MODEL, temperature=0)

    tools = [
        get_ticket,
        search_tickets,
        create_ticket,
        add_comment,
        transition_ticket,
        get_my_tickets,
        lookup_user,
        reassign_ticket,
    ]

    agent_executor = create_agent(
        model=llm,
        tools=tools,
        system_prompt=_SYSTEM_PROMPT,
    )

    _invoke_cfg = {"recursion_limit": 15}

    print("\n" + "=" * 60)
    print(f"  ADL Jira Agent  |  {settings.CLAUDE_MODEL}  |  ASL Airlines")
    print("=" * 60)

    # Single-query mode (CLI arg) — bypasses menu
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        response = agent_executor.invoke({"messages": [("human", query)]}, config=_invoke_cfg)
        msg = response["messages"][-1]
        print(getattr(msg, "content", str(msg)))
        return

    # Interactive menu loop
    while True:
        try:
            query = _build_guided_query()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if query is None:
            continue
        if query == "EXIT":
            print("\nBye!")
            break

        try:
            response = agent_executor.invoke({"messages": [("human", query)]}, config=_invoke_cfg)
            msg = response["messages"][-1]
            print(f"\n  Agent: {getattr(msg, 'content', str(msg))}\n")
        except Exception as e:
            logger.error("Agent error: %s", e)


if __name__ == "__main__":
    main()
