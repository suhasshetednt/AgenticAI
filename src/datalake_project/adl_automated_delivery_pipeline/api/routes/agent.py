"""Agent invocation endpoints."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adl_automated_delivery_pipeline.state import make_initial_state
from adl_automated_delivery_pipeline.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])

# Lazy-loaded graph (initialised on first request)
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        from adl_automated_delivery_pipeline.graphs.supervisor import build_supervisor_graph
        _graph = build_supervisor_graph()
    return _graph


class RunRequest(BaseModel):
    message: str
    project_key: str = settings.DEFAULT_PROJECT
    session_id: Optional[str] = None


class RunResponse(BaseModel):
    session_id: str
    trace_id: str
    status: str
    intent: str
    output: Optional[str]
    pending_approvals: list[dict]
    mutations_staged: int
    mutations_executed: int
    error: Optional[str]


@router.post("/run", response_model=RunResponse)
async def run_agent(req: RunRequest) -> RunResponse:
    """Invoke the supervisor agent graph with a natural language request."""
    state = make_initial_state(
        user_id="api_user",
        role="developer",
        project_key=req.project_key,
        message=req.message,
    )
    if req.session_id:
        state["session_id"] = req.session_id

    config = {"configurable": {"thread_id": state["session_id"]}}

    try:
        graph = _get_graph()
        result = graph.invoke(state, config=config)
    except Exception as exc:
        logger.exception("Graph invocation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent invocation failed")

    mutations = result.get("jira_mutations", [])
    pending = result.get("pending_approvals", [])

    return RunResponse(
        session_id=result["session_id"],
        trace_id=result["trace_id"],
        status=result.get("workflow_phase", "COMPLETE"),
        intent=result.get("intent", "GENERAL"),
        output=result.get("agent_output"),
        pending_approvals=[a.model_dump() if hasattr(a, "model_dump") else a for a in pending],
        mutations_staged=len(mutations),
        mutations_executed=sum(1 for m in mutations if m.executed),
        error=result.get("error"),
    )


@router.get("/sessions/{session_id}/state")
async def get_session_state(session_id: str) -> dict:
    """Retrieve current state of a suspended graph session."""
    graph = _get_graph()
    config = {"configurable": {"thread_id": session_id}}
    try:
        snapshot = graph.get_state(config)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Session not found")
        values = snapshot.values
        return {
            "session_id": session_id,
            "workflow_phase": values.get("workflow_phase"),
            "intent": values.get("intent"),
            "pending_approvals": len(values.get("pending_approvals", [])),
            "mutations_staged": len(values.get("jira_mutations", [])),
            "error": values.get("error"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Session state retrieval failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent invocation failed")


@router.post("/sessions/{session_id}/resume")
async def resume_session(session_id: str, payload: dict) -> dict:
    """Resume a graph suspended at an interrupt() node (API approval flow)."""
    graph = _get_graph()
    config = {"configurable": {"thread_id": session_id}}
    try:
        result = graph.invoke(payload, config=config)
        return {
            "session_id": session_id,
            "status": result.get("workflow_phase"),
            "output": result.get("agent_output"),
            "error": result.get("error"),
        }
    except Exception as exc:
        logger.exception("Session resume failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent invocation failed")
