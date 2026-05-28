"""Audit trail query endpoints."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from adl_automated_delivery_pipeline.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/trail")
async def get_audit_trail(
    session_id: Optional[str] = Query(None),
    agent: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
) -> list[dict]:
    """Query the audit log with optional filters."""
    log_path = Path(settings.AUDIT_LOG_FILE)
    if not log_path.exists():
        return []

    entries = []
    try:
        with log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                if session_id and entry.get("session_id") != session_id:
                    continue
                if agent and entry.get("agent") != agent:
                    continue
                if status and entry.get("status") != status:
                    continue

                entries.append(entry)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read audit log: {exc}")

    # Return most-recent first, capped at limit
    return list(reversed(entries))[-limit:]


@router.get("/trail/{session_id}")
async def get_session_audit(session_id: str) -> list[dict]:
    """Get full audit trail for a specific session."""
    return await get_audit_trail(session_id=session_id, limit=500)


@router.get("/mutations")
async def get_mutation_audit(
    executed_only: bool = Query(False),
    limit: int = Query(100, le=1000),
) -> list[dict]:
    """Query audit entries that have associated JIRA mutations."""
    entries = await get_audit_trail(limit=1000)
    mutation_entries = [e for e in entries if e.get("mutation_ids")]
    if executed_only:
        mutation_entries = [e for e in mutation_entries if e.get("status") == "SUCCESS"]
    return mutation_entries[:limit]


@router.get("/stats")
async def get_audit_stats() -> dict:
    """Aggregate stats over the full audit log."""
    entries = await get_audit_trail(limit=10000)
    agents: dict[str, int] = {}
    statuses: dict[str, int] = {}
    total_mutations = 0

    for entry in entries:
        a = entry.get("agent", "unknown")
        agents[a] = agents.get(a, 0) + 1
        s = entry.get("status", "unknown")
        statuses[s] = statuses.get(s, 0) + 1
        total_mutations += len(entry.get("mutation_ids", []))

    return {
        "total_entries": len(entries),
        "total_mutations": total_mutations,
        "by_agent": agents,
        "by_status": statuses,
    }
