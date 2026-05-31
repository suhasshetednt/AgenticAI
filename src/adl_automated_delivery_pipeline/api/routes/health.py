"""Health and readiness endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from adl_automated_delivery_pipeline.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "langgraph-jira-agent",
    }


@router.get("/ready")
async def readiness_check() -> dict:
    """Check connectivity to Jira and LLM availability."""
    checks: dict[str, str] = {}

    # Jira check
    try:
        from jira import JIRA
        jira = JIRA(
            server=settings.JIRA_INSTANCE_URL,
            basic_auth=(settings.JIRA_USERNAME, settings.JIRA_API_TOKEN),
        )
        jira.myself()
        checks["jira"] = "ok"
    except Exception as exc:
        logger.warning("Jira readiness check failed: %s", exc)
        checks["jira"] = f"error: {exc}"

    # LLM check — Claude is primary; Gemini/OpenAI are optional fallbacks.
    if settings.ANTHROPIC_API_KEY:
        checks["llm"] = f"claude (configured: {settings.CLAUDE_MODEL})"
    elif settings.OPENAI_API_KEY:
        checks["llm"] = f"openai fallback (configured: {settings.OPENAI_MODEL})"
    elif settings.GOOGLE_API_KEY:
        checks["llm"] = f"gemini fallback (configured: {settings.GEMINI_MODEL})"
    else:
        checks["llm"] = "error: no API key"

    overall = "ready" if all("error" not in v for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}


@router.get("/config")
async def show_config() -> dict:
    """Show non-sensitive configuration."""
    return {
        "default_project": settings.DEFAULT_PROJECT,
        "primary_llm": settings.PRIMARY_LLM,
        "claude_model": settings.CLAUDE_MODEL,
        "providers_configured": {
            "claude": bool(settings.ANTHROPIC_API_KEY),
            "openai": bool(settings.OPENAI_API_KEY),
            "gemini": bool(settings.GOOGLE_API_KEY),
        },
        "openai_model": settings.OPENAI_MODEL,
        "gemini_model": settings.GEMINI_MODEL,
        "jira_instance": settings.JIRA_INSTANCE_URL,
        "approval_store": settings.APPROVAL_STORE_DIR,
    }
