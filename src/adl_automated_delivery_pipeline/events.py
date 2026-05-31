"""
Jira webhook event types, EventBus, and agent routing.

Flow:
    Jira POST → webhooks.py → EventBus.publish() → WebhookProcessor.handle()
                                                  → right agent runs in background
                                                  → mutations staged for approval
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Jira event type constants ─────────────────────────────────────────────────

class JiraEvent:
    """Jira webhook event type strings."""

    # Issue lifecycle
    ISSUE_CREATED   = "jira:issue_created"
    ISSUE_UPDATED   = "jira:issue_updated"
    ISSUE_DELETED   = "jira:issue_deleted"

    # Comments
    COMMENT_CREATED = "comment_created"
    COMMENT_UPDATED = "comment_updated"
    COMMENT_DELETED = "comment_deleted"

    # Sprints  (Jira Software)
    SPRINT_CREATED  = "sprint_created"
    SPRINT_UPDATED  = "sprint_updated"
    SPRINT_DELETED  = "sprint_deleted"
    SPRINT_STARTED  = "sprint_started"
    SPRINT_CLOSED   = "sprint_closed"

    # Versions / releases
    VERSION_CREATED  = "jira:version_created"
    VERSION_UPDATED  = "jira:version_updated"
    VERSION_RELEASED = "jira:version_released"

    # Board / backlog
    BOARD_CREATED   = "board_created"
    BOARD_UPDATED   = "board_updated"

    # Worklogs
    WORKLOG_UPDATED = "jira:worklog_updated"


# ── Parsed event envelope ─────────────────────────────────────────────────────

@dataclass
class WebhookEvent:
    """Normalised Jira webhook event passed through the system."""

    event_type: str                         # one of JiraEvent.*
    raw: dict[str, Any]                     # full raw payload from Jira
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = ""

    # Convenience accessors
    @property
    def issue_key(self) -> str | None:
        issue = self.raw.get("issue", {})
        return issue.get("key")

    @property
    def project_key(self) -> str | None:
        issue = self.raw.get("issue", {})
        project = issue.get("fields", {}).get("project", {})
        return project.get("key")

    @property
    def issue_type(self) -> str | None:
        issue = self.raw.get("issue", {})
        return issue.get("fields", {}).get("issuetype", {}).get("name")

    @property
    def summary(self) -> str:
        issue = self.raw.get("issue", {})
        return issue.get("fields", {}).get("summary", "")

    @property
    def sprint_name(self) -> str | None:
        sprint = self.raw.get("sprint", {})
        return sprint.get("name")

    @property
    def sprint_id(self) -> int | None:
        sprint = self.raw.get("sprint", {})
        return sprint.get("id")

    @property
    def actor_email(self) -> str | None:
        """Email of the Jira user who triggered the event."""
        user = self.raw.get("user", {})
        return user.get("emailAddress")

    @property
    def changed_fields(self) -> list[str]:
        """Field names changed in an issue_updated event."""
        changelog = self.raw.get("changelog", {})
        items = changelog.get("items", [])
        return [item.get("field", "") for item in items]


# ── Event → agent routing table ───────────────────────────────────────────────

# Maps event_type → intent name (matches supervisor classify_intent_node values)
EVENT_TO_INTENT: dict[str, str] = {
    JiraEvent.ISSUE_CREATED:    "TICKET_INTELLIGENCE",
    JiraEvent.ISSUE_UPDATED:    "TICKET_INTELLIGENCE",
    JiraEvent.COMMENT_CREATED:  "TICKET_INTELLIGENCE",
    JiraEvent.SPRINT_CREATED:   "SPRINT_MANAGEMENT",
    JiraEvent.SPRINT_STARTED:   "SPRINT_MANAGEMENT",
    JiraEvent.SPRINT_CLOSED:    "SPRINT_MANAGEMENT",
    JiraEvent.SPRINT_UPDATED:   "SPRINT_MANAGEMENT",
    JiraEvent.VERSION_RELEASED: "QA_RELEASE",
    JiraEvent.VERSION_CREATED:  "QA_RELEASE",
    JiraEvent.WORKLOG_UPDATED:  "DEV_PRODUCTIVITY",
}

# Human-readable message generated for each event type (sent to the agent as request)
EVENT_TO_MESSAGE: dict[str, Callable[[WebhookEvent], str]] = {
    JiraEvent.ISSUE_CREATED: lambda e: (
        f"A new {e.issue_type or 'issue'} was just created: {e.issue_key} — '{e.summary}'. "
        f"Check for duplicate tickets, score its quality, and generate acceptance criteria if missing. "
        f"Project: {e.project_key or 'ADL'}."
    ),
    JiraEvent.ISSUE_UPDATED: lambda e: (
        f"Issue {e.issue_key} was updated. Changed fields: {', '.join(e.changed_fields) or 'unknown'}. "
        f"Review the changes and assess if any follow-up action is needed. "
        f"Project: {e.project_key or 'ADL'}."
    ),
    JiraEvent.SPRINT_STARTED: lambda e: (
        f"Sprint '{e.sprint_name}' has just started (ID: {e.sprint_id}). "
        f"Generate a sprint kickoff summary: committed stories, team capacity analysis, "
        f"and any immediate risk flags. Project: {e.project_key or 'ADL'}."
    ),
    JiraEvent.SPRINT_CLOSED: lambda e: (
        f"Sprint '{e.sprint_name}' has just been closed. "
        f"Generate a full retrospective: velocity, completed vs incomplete, "
        f"blockers encountered, and action items. Project: {e.project_key or 'ADL'}."
    ),
    JiraEvent.SPRINT_CREATED: lambda e: (
        f"A new sprint '{e.sprint_name}' was created. "
        f"Analyse the current backlog and suggest which tickets to include based on velocity and priority. "
        f"Project: {e.project_key or 'ADL'}."
    ),
    JiraEvent.VERSION_RELEASED: lambda e: (
        f"A version was just released in Jira. "
        f"Generate release notes for all tickets included in this version. "
        f"Project: {e.project_key or 'ADL'}."
    ),
    JiraEvent.WORKLOG_UPDATED: lambda e: (
        f"Worklog updated on {e.issue_key}. "
        f"Check current team workload distribution and flag any overloaded members. "
        f"Project: {e.project_key or 'ADL'}."
    ),
    JiraEvent.COMMENT_CREATED: lambda e: (
        f"A new comment was added to {e.issue_key}. "
        f"Review the comment for any action items, blockers, or escalation signals. "
        f"Project: {e.project_key or 'ADL'}."
    ),
}

def _default_message(event: WebhookEvent) -> str:
    return (
        f"Jira event received: {event.event_type}. "
        f"Issue: {event.issue_key or 'N/A'}. "
        f"Review and take appropriate action. "
        f"Project: {event.project_key or 'ADL'}."
    )


def build_agent_message(event: WebhookEvent) -> str:
    """Return the natural-language message to send to the agent for this event."""
    builder = EVENT_TO_MESSAGE.get(event.event_type, _default_message)
    return builder(event)


def get_intent(event: WebhookEvent) -> str:
    """Return the routing intent for this event type."""
    return EVENT_TO_INTENT.get(event.event_type, "GENERAL")


# ── EventBus ─────────────────────────────────────────────────────────────────

_handlers: dict[str, list[Callable[[WebhookEvent], None]]] = {}


def subscribe(event_type: str, handler: Callable[[WebhookEvent], None]) -> None:
    """Register a handler for a specific event type (or '*' for all events)."""
    _handlers.setdefault(event_type, []).append(handler)
    logger.debug("EventBus: subscribed handler for '%s'", event_type)


def publish(event: WebhookEvent) -> None:
    """Dispatch event to all registered handlers (wildcard '*' + specific type)."""
    for handler in _handlers.get("*", []):
        try:
            handler(event)
        except Exception as exc:
            logger.exception("EventBus wildcard handler failed for %s: %s", event.event_type, exc)

    for handler in _handlers.get(event.event_type, []):
        try:
            handler(event)
        except Exception as exc:
            logger.exception("EventBus handler failed for %s: %s", event.event_type, exc)
