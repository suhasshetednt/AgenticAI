"""File-based audit logger — appends JSON lines to AUDIT_LOG_FILE."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from adl_automated_delivery_pipeline.config import settings
from adl_automated_delivery_pipeline.state import AuditEntry

logger = logging.getLogger(__name__)

# Module-level lock so concurrent coroutines/threads don't interleave writes
_write_lock = threading.Lock()


class AuditLogger:
    """Append-only JSON-lines audit logger backed by a local file.

    All methods are class/static methods so callers do not need to manage
    an instance — just ``AuditLogger.log_action(...)``.
    """

    @staticmethod
    def _log_file_path() -> Path:
        """Return the resolved audit log file path, creating parent dirs if needed."""
        path = Path(settings.AUDIT_LOG_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def log(entry: AuditEntry) -> None:
        """Append *entry* as a single JSON line to the audit log file.

        Thread-safe via a module-level lock. Never raises — errors are
        logged to the module logger so they do not crash the agent.

        Args:
            entry: A fully-constructed AuditEntry model instance.
        """
        try:
            line = entry.model_dump_json() + "\n"
            path = AuditLogger._log_file_path()
            with _write_lock:
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
            logger.debug(
                "Audit entry written: entry_id=%s action=%s status=%s",
                entry.entry_id,
                entry.action,
                entry.status,
            )
        except OSError as exc:
            logger.error(
                "Failed to write audit entry entry_id=%s: %s",
                entry.entry_id,
                exc,
            )
        except Exception as exc:  # noqa: BLE001 — last-resort guard for audit path
            logger.error("Unexpected error writing audit entry: %s", exc)

    @staticmethod
    def log_action(
        trace_id: str,
        session_id: str,
        agent: str,
        action: str,
        user_id: str,
        role: str,
        project_key: str,
        input_summary: str,
        output_summary: str,
        mutation_ids: list[str] | None = None,
        latency_ms: int | None = None,
        status: str = "SUCCESS",
        error: str | None = None,
    ) -> AuditEntry:
        """Create an AuditEntry, persist it, and return it.

        Args:
            trace_id: LangGraph trace ID for the current run.
            session_id: Agent session identifier.
            agent: Name of the agent or node that performed the action.
            action: Human-readable action label (e.g. "fetch_issue ADL-123").
            user_id: Identity of the requesting user.
            role: RBAC role of the requesting user.
            project_key: Jira project key (e.g. "ADL").
            input_summary: Short description of the input/request.
            output_summary: Short description of the output/result.
            mutation_ids: Optional list of JiraMutation IDs involved.
            latency_ms: Wall-clock latency in milliseconds, if measured.
            status: "SUCCESS" | "FAILED" | "PARTIAL".
            error: Error message if status != SUCCESS.

        Returns:
            The constructed and persisted AuditEntry.
        """
        entry = AuditEntry(
            trace_id=trace_id,
            session_id=session_id,
            agent=agent,
            action=action,
            user_id=user_id,
            role=role,
            project_key=project_key,
            input_summary=input_summary,
            output_summary=output_summary,
            mutation_ids=mutation_ids or [],
            latency_ms=latency_ms,
            status=status,
            error=error,
        )
        AuditLogger.log(entry)
        return entry

    @staticmethod
    def get_trail(session_id: str) -> list[dict]:
        """Return all audit entries for *session_id* as plain dicts.

        Reads the entire log file and filters by session_id. For large logs
        consider rotating the file or adding an index.

        Args:
            session_id: The session to retrieve entries for.

        Returns:
            List of deserialized audit entry dicts in chronological order.
        """
        path = AuditLogger._log_file_path()
        if not path.exists():
            logger.debug("Audit log file does not exist yet: %s", path)
            return []

        entries: list[dict] = []
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line_no, raw_line in enumerate(fh, start=1):
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        record = json.loads(stripped)
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "Skipping malformed audit line %d: %s", line_no, exc
                        )
                        continue
                    if record.get("session_id") == session_id:
                        entries.append(record)
        except OSError as exc:
            logger.error("Failed to read audit log: %s", exc)

        logger.debug(
            "get_trail: found %d entries for session_id=%s",
            len(entries),
            session_id,
        )
        return entries
