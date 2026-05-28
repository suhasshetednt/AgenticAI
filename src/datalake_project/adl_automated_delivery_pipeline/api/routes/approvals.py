"""Human approval management endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from adl_automated_delivery_pipeline.approval import ApprovalStore
from adl_automated_delivery_pipeline.config import settings
from adl_automated_delivery_pipeline.rbac import RBACEnforcer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class ApprovalDecision(BaseModel):
    approver_id: str
    reason: Optional[str] = None


def _get_approver_role(x_api_key: str = Header(default="")) -> str:
    """Resolve the caller's role from the X-API-Key header."""
    if not settings.API_SECRET_KEY:
        logger.debug("API_SECRET_KEY not configured — granting admin role (dev mode)")
        return "admin"
    if x_api_key == settings.API_SECRET_KEY:
        return "admin"
    raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/pending")
async def list_pending_approvals(
    approver_role: str = Depends(_get_approver_role),
) -> list[dict]:
    """List all pending approvals visible to the given role."""
    records = ApprovalStore.list_pending()
    visible = [
        r.model_dump() for r in records
        if RBACEnforcer.can_approve(approver_role, r.operation_type)
    ]
    return visible


@router.get("/{approval_id}")
async def get_approval(approval_id: str) -> dict:
    record = ApprovalStore.get(approval_id)
    if not record:
        raise HTTPException(status_code=404, detail="Approval not found")
    return record.model_dump()


@router.post("/{approval_id}/approve")
async def approve(
    approval_id: str,
    decision: ApprovalDecision,
    approver_role: str = Depends(_get_approver_role),
) -> dict:
    """Approve a pending operation. Enforces RBAC on approver role."""
    record = ApprovalStore.get(approval_id)
    if not record:
        raise HTTPException(status_code=404, detail="Approval not found")
    if record.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Approval already {record.status}")

    try:
        RBACEnforcer.assert_can_approve(approver_role, record.operation_type)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    updated = ApprovalStore.approve(approval_id, decision.approver_id)

    # Resume the suspended graph session if session_id is set
    if record.session_id:
        try:
            from adl_automated_delivery_pipeline.api.routes.agent import _get_graph
            graph = _get_graph()
            config = {"configurable": {"thread_id": record.session_id}}
            graph.invoke(
                {"decision": "APPROVED", "approver": decision.approver_id, "approver_role": approver_role},
                config=config,
            )
        except Exception as exc:
            logger.warning("Graph resume after approval failed: %s", exc)

    return {"status": "approved", "approval_id": approval_id, "record": updated.model_dump()}


@router.post("/{approval_id}/reject")
async def reject(
    approval_id: str,
    decision: ApprovalDecision,
    approver_role: str = Depends(_get_approver_role),
) -> dict:
    """Reject a pending operation."""
    record = ApprovalStore.get(approval_id)
    if not record:
        raise HTTPException(status_code=404, detail="Approval not found")
    if record.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Approval already {record.status}")

    try:
        RBACEnforcer.assert_can_approve(approver_role, record.operation_type)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    updated = ApprovalStore.reject(
        approval_id, decision.approver_id, decision.reason or "No reason given"
    )
    return {"status": "rejected", "approval_id": approval_id, "record": updated.model_dump()}


@router.get("/")
async def list_all_approvals(status: Optional[str] = None) -> list[dict]:
    """List all approval records, optionally filtered by status."""
    from pathlib import Path
    import json

    store_dir = Path(ApprovalStore._store_dir())
    records = []
    for f in store_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if status is None or data.get("status") == status:
                records.append(data)
        except (ValueError, KeyError, OSError):
            continue
    records.sort(key=lambda r: r.get("requested_at", ""), reverse=True)
    return records
