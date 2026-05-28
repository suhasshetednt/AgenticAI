"""FastAPI application factory for the LangGraph JIRA Agent."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from adl_automated_delivery_pipeline.api.routes import agent, approvals, audit, health, webhooks
from adl_automated_delivery_pipeline.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("LangGraph JIRA Agent API starting up")
    from adl_automated_delivery_pipeline.config import settings
    from pathlib import Path

    # Ensure file-store directories exist
    Path(settings.APPROVAL_STORE_DIR).mkdir(parents=True, exist_ok=True)

    # Pre-compile the graph so the first webhook doesn't pay cold-start cost
    try:
        from adl_automated_delivery_pipeline.webhook_processor import _get_graph
        _get_graph()
        logger.info("Supervisor graph pre-compiled successfully")
    except Exception as exc:
        logger.warning("Graph pre-compilation failed (will retry on first request): %s", exc)

    logger.info(
        "Webhook endpoint: POST /webhooks/jira  |  HMAC: %s  |  Auto-process: %s",
        "enabled" if settings.JIRA_WEBHOOK_SECRET else "disabled (no secret)",
        settings.WEBHOOK_AUTO_PROCESS,
    )
    yield
    logger.info("LangGraph JIRA Agent API shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="LangGraph JIRA AI Agent",
        description="Production-grade autonomous JIRA sprint management with human-in-the-loop approval",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS_LIST,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
    )

    # Request correlation IDs
    @app.middleware("http")
    async def add_correlation_id(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "request_id": getattr(request.state, "request_id", None)},
        )

    app.include_router(health.router)
    app.include_router(agent.router)
    app.include_router(approvals.router)
    app.include_router(audit.router)
    app.include_router(webhooks.router)

    return app


app = create_app()
