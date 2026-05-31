"""
Background webhook processor.

When Jira sends an event, the webhook endpoint returns 200 immediately,
then this module processes the event in a background thread — running the
appropriate agent, staging mutations, and queuing approvals.
"""

from __future__ import annotations

import sys
from pathlib import Path
import logging

# Allow direct execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import threading
import uuid

from adl_automated_delivery_pipeline.config import settings
from adl_automated_delivery_pipeline.events import WebhookEvent, build_agent_message, get_intent
from adl_automated_delivery_pipeline.state import make_initial_state
from adl_automated_delivery_pipeline.audit import AuditLogger

logger = logging.getLogger(__name__)

# How many webhook events can be processed concurrently
_SEMAPHORE = threading.Semaphore(4)

# Lazy-cached graph (avoids rebuilding on every event)
_graph = None
_graph_lock = threading.Lock()


def _get_graph():
    global _graph
    if _graph is None:
        with _graph_lock:
            if _graph is None:
                from adl_automated_delivery_pipeline.graphs.supervisor import build_supervisor_graph
                _graph = build_supervisor_graph()
                logger.info("WebhookProcessor: supervisor graph compiled")
    return _graph


def process_event_background(event: WebhookEvent) -> None:
    """
    Spawn a daemon thread to process this event.
    Returns immediately — the webhook endpoint can respond 200 right away.
    """
    if not settings.WEBHOOK_AUTO_PROCESS:
        logger.info("WebhookProcessor: auto-processing disabled, skipping %s", event.event_type)
        return

    thread = threading.Thread(
        target=_process_event,
        args=(event,),
        name=f"webhook-{event.event_type}-{event.event_id[:8]}",
        daemon=True,
    )
    thread.start()
    logger.info("WebhookProcessor: dispatched thread for %s (issue=%s)", event.event_type, event.issue_key)


def _process_event(event: WebhookEvent) -> None:
    """Run in background thread — invoke the agent graph for this event."""
    with _SEMAPHORE:
        trace_id = str(uuid.uuid4())
        project = event.project_key or settings.DEFAULT_PROJECT
        message = build_agent_message(event)
        intent = get_intent(event)

        logger.info(
            "WebhookProcessor: processing event=%s issue=%s project=%s intent=%s trace=%s",
            event.event_type, event.issue_key, project, intent, trace_id,
        )

        # Build initial state — webhook events run as "system" user with scrum_master role
        state = make_initial_state(
            user_id=f"webhook:{event.actor_email or 'jira-system'}",
            role="scrum_master",
            project_key=project,
            message=message,
        )
        state["trace_id"] = trace_id
        state["intent"] = intent          # pre-set intent so classifier is skipped

        try:
            graph = _get_graph()
            config = {"configurable": {"thread_id": state["session_id"]}}
            result = graph.invoke(state, config=config)

            mutations = result.get("jira_mutations", [])
            pending = result.get("pending_approvals", [])

            logger.info(
                "WebhookProcessor: completed event=%s session=%s mutations=%d approvals=%d output_len=%d",
                event.event_type,
                result.get("session_id"),
                len(mutations),
                len(pending),
                len(result.get("agent_output") or ""),
            )

            # Log summary to audit
            AuditLogger.log_action(
                trace_id=trace_id,
                session_id=state["session_id"],
                agent="webhook_processor",
                action=f"auto_triggered:{event.event_type}",
                user_id=state["user_id"],
                role=state["role"],
                project_key=project,
                input_summary=f"Event: {event.event_type} | Issue: {event.issue_key}",
                output_summary=f"Staged {len(mutations)} mutations, {len(pending)} approvals pending",
                mutation_ids=[m.mutation_id for m in mutations],
                status="SUCCESS" if not result.get("error") else "PARTIAL",
                error=result.get("error"),
            )

            # Print pending approvals to console (visible in API server logs)
            if pending:
                logger.warning(
                    "WebhookProcessor: %d approval(s) pending for event %s — "
                    "run 'python run_langgraph_agent.py --approvals' to review",
                    len(pending), event.event_type,
                )
                for ap in pending:
                    label = ap.operation_label if hasattr(ap, "operation_label") else str(ap)
                    aid = ap.approval_id if hasattr(ap, "approval_id") else "?"
                    logger.warning("  PENDING: %s  [ID: %s]", label, aid)

        except Exception as exc:
            logger.exception(
                "WebhookProcessor: failed processing event=%s issue=%s: %s",
                event.event_type, event.issue_key, exc,
            )
            AuditLogger.log_action(
                trace_id=trace_id,
                session_id=state["session_id"],
                agent="webhook_processor",
                action=f"auto_triggered:{event.event_type}",
                user_id=state["user_id"],
                role=state["role"],
                project_key=project,
                input_summary=f"Event: {event.event_type} | Issue: {event.issue_key}",
                output_summary="",
                status="FAILED",
                error=str(exc),
            )


# ── Event log (in-memory ring buffer for /webhooks/events endpoint) ───────────

_event_log: list[dict[str, object]] = []
_event_log_lock = threading.Lock()
_MAX_EVENT_LOG = 200


def record_event(event: WebhookEvent) -> None:
    """Store a compact event record in the in-memory ring buffer."""
    record: dict[str, object] = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "issue_key": event.issue_key,
        "project_key": event.project_key,
        "actor": event.actor_email,
        "received_at": event.received_at.isoformat(),
    }
    with _event_log_lock:
        _event_log.append(record)
        if len(_event_log) > _MAX_EVENT_LOG:
            _event_log.pop(0)


def get_event_log(limit: int = 50) -> list[dict[str, object]]:
    """Return the most recent webhook events (newest first)."""
    with _event_log_lock:
        return list(reversed(_event_log[-limit:]))

