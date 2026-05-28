"""
Jira Cloud webhook receiver.

Jira POSTs events here. The endpoint:
  1. Verifies the HMAC-SHA256 signature (if JIRA_WEBHOOK_SECRET is set)
  2. Parses the event payload
  3. Records it in the event log
  4. Dispatches processing to a background thread
  5. Returns 200 immediately (Jira requires < 5 s response time)

Configure in Jira:
  Project Settings → Webhooks → Create webhook
  URL: https://<your-host>/webhooks/jira
  Events: Issue (created, updated), Sprint (created, started, closed), Comment (created)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from adl_automated_delivery_pipeline.config import settings
from adl_automated_delivery_pipeline.events import JiraEvent, WebhookEvent, publish
from adl_automated_delivery_pipeline.webhook_processor import get_event_log, process_event_background, record_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── HMAC verification ─────────────────────────────────────────────────────────

def _verify_signature(body: bytes, signature_header: str | None) -> None:
    """
    Verify the X-Hub-Signature header sent by Jira.
    Jira format: 'sha256=<hex_digest>'
    Skipped when JIRA_WEBHOOK_SECRET is not configured.
    """
    if not settings.JIRA_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook signature verification not configured")

    if not signature_header:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Hub-Signature header. Set JIRA_WEBHOOK_SECRET in config.env.",
        )

    parts = signature_header.split("=", 1)
    if len(parts) != 2 or parts[0] != "sha256":
        raise HTTPException(status_code=401, detail="Invalid signature format. Expected 'sha256=<hex>'")

    expected = hmac.new(
        settings.JIRA_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, parts[1]):
        logger.warning("Webhook: HMAC signature mismatch — possible spoofed request")
        raise HTTPException(status_code=401, detail="Signature verification failed")


# ── Main webhook receiver ─────────────────────────────────────────────────────

@router.post("/jira")
async def receive_jira_webhook(
    request: Request,
    x_hub_signature: str | None = Header(default=None),
) -> JSONResponse:
    """
    Receive all Jira webhook events.
    Returns 200 immediately; processing happens in a background thread.
    """
    body = await request.body()

    # Verify signature before parsing
    _verify_signature(body, x_hub_signature)

    # Parse JSON
    try:
        import json
        payload: dict = json.loads(body)
    except (ValueError, KeyError) as exc:
        logger.warning("Webhook: failed to parse JSON body: %s", exc)
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    event_type: str = payload.get("webhookEvent", "unknown")
    event_id = str(uuid.uuid4())

    event = WebhookEvent(
        event_type=event_type,
        raw=payload,
        received_at=datetime.now(timezone.utc),
        event_id=event_id,
    )

    logger.info(
        "Webhook received: type=%s issue=%s project=%s actor=%s",
        event_type, event.issue_key, event.project_key, event.actor_email,
    )

    # Record in ring buffer (for /webhooks/events endpoint)
    record_event(event)

    # Publish to EventBus (for any external subscribers)
    publish(event)

    # Dispatch background processing (runs agent, stages mutations)
    _should_process = event_type in {
        JiraEvent.ISSUE_CREATED,
        JiraEvent.ISSUE_UPDATED,
        JiraEvent.SPRINT_CREATED,
        JiraEvent.SPRINT_STARTED,
        JiraEvent.SPRINT_CLOSED,
        JiraEvent.VERSION_RELEASED,
        JiraEvent.WORKLOG_UPDATED,
        JiraEvent.COMMENT_CREATED,
    }

    if _should_process:
        process_event_background(event)
        status = "queued"
    else:
        logger.info("Webhook: event type %s not mapped to an agent — acknowledged only", event_type)
        status = "acknowledged"

    # Jira requires a fast 200 response
    return JSONResponse(
        status_code=200,
        content={
            "status": status,
            "event_id": event_id,
            "event_type": event_type,
            "issue_key": event.issue_key,
        },
    )


# ── Diagnostics endpoints ─────────────────────────────────────────────────────

@router.get("/events")
async def list_received_events(limit: int = 50) -> list[dict]:
    """
    Return the most recently received webhook events (newest first).
    Useful for confirming Jira is successfully delivering webhooks.
    """
    return get_event_log(limit=limit)


@router.get("/events/latest")
async def latest_event() -> dict:
    """Return the single most recently received webhook event."""
    log = get_event_log(limit=1)
    if not log:
        return {"message": "No webhook events received yet"}
    return log[0]


@router.get("/config")
async def webhook_config() -> dict:
    """Show webhook configuration (no secrets exposed)."""
    return {
        "endpoint": "POST /webhooks/jira",
        "hmac_verification": bool(settings.JIRA_WEBHOOK_SECRET),
        "auto_process": settings.WEBHOOK_AUTO_PROCESS,
        "require_approval": settings.WEBHOOK_REQUIRE_APPROVAL,
        "supported_events": [
            JiraEvent.ISSUE_CREATED,
            JiraEvent.ISSUE_UPDATED,
            JiraEvent.SPRINT_CREATED,
            JiraEvent.SPRINT_STARTED,
            JiraEvent.SPRINT_CLOSED,
            JiraEvent.VERSION_RELEASED,
            JiraEvent.WORKLOG_UPDATED,
            JiraEvent.COMMENT_CREATED,
        ],
    }


@router.post("/test")
async def test_webhook(event_type: str = "jira:issue_created") -> dict:
    """
    Fire a synthetic webhook event for local testing.
    Simulates Jira sending a real event — useful before setting up ngrok.
    Disabled entirely in production (returns 404).
    """
    if settings.ENV == "production":
        raise HTTPException(status_code=404, detail="Not found")
    fake_payload = {
        "webhookEvent": event_type,
        "issue": {
            "key": f"{settings.DEFAULT_PROJECT}-TEST",
            "fields": {
                "summary": "Synthetic test webhook event",
                "issuetype": {"name": "Story"},
                "project": {"key": settings.DEFAULT_PROJECT},
                "status": {"name": "To Do"},
                "priority": {"name": "Medium"},
                "assignee": None,
            },
        },
        "user": {"emailAddress": "webhook-test@local"},
        "sprint": {"id": 1, "name": "Test Sprint"},
    }

    event = WebhookEvent(
        event_type=event_type,
        raw=fake_payload,
        received_at=datetime.now(timezone.utc),
        event_id=str(uuid.uuid4()),
    )

    record_event(event)
    publish(event)
    process_event_background(event)

    return {
        "status": "test_event_fired",
        "event_type": event_type,
        "event_id": event.event_id,
        "message": "Check server logs and run 'python run_langgraph_agent.py --approvals' to see results",
    }
