"""File-based approval store and CLI approval gate."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from adl_automated_delivery_pipeline.config import settings
from adl_automated_delivery_pipeline.state import ApprovalRecord, JiraMutation

logger = logging.getLogger(__name__)

_RISK_LABELS: dict[str, str] = {
    "LOW": "LOW",
    "MEDIUM": "MEDIUM",
    "HIGH": "HIGH",
    "CRITICAL": "CRITICAL",
}


class ApprovalNotFoundError(KeyError):
    """Raised when an approval_id cannot be found in the store."""


class ApprovalAlreadyDecidedError(RuntimeError):
    """Raised when attempting to approve/reject an already-decided record."""


class ApprovalStore:
    """File-backed approval queue.

    Each approval is persisted as a single JSON file named ``{approval_id}.json``
    inside APPROVAL_STORE_DIR.  The interface is intentionally class-method-only so
    a Redis-backed implementation can drop in by subclassing or replacing this class.
    """

    @classmethod
    def _store_dir(cls) -> Path:
        """Return the approval store directory, creating it if it does not exist."""
        path = Path(settings.APPROVAL_STORE_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def _record_path(cls, approval_id: str) -> Path:
        return cls._store_dir() / f"{approval_id}.json"

    @classmethod
    def _write_record(cls, record: ApprovalRecord) -> None:
        """Serialize and write a record atomically via a temp-then-rename pattern."""
        target = cls._record_path(record.approval_id)
        tmp = target.with_suffix(".tmp")
        try:
            tmp.write_text(record.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(target)
        except OSError as exc:
            logger.error(
                "Failed to write approval record %s: %s", record.approval_id, exc
            )
            raise

    @classmethod
    def _read_record(cls, approval_id: str) -> Optional[ApprovalRecord]:
        """Load and deserialize a record from disk, returning None if not found."""
        path = cls._record_path(approval_id)
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
            return ApprovalRecord.model_validate_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error(
                "Corrupt approval record file %s: %s", path, exc
            )
            return None
        except OSError as exc:
            logger.error("Failed to read approval record %s: %s", path, exc)
            return None

    # ── Public API ────────────────────────────────────────────────────

    @classmethod
    def enqueue(cls, record: ApprovalRecord) -> str:
        """Persist *record* to disk and return its approval_id.

        Args:
            record: A fully-constructed ApprovalRecord (status should be PENDING).

        Returns:
            The approval_id string.
        """
        cls._write_record(record)
        logger.info(
            "Approval enqueued: approval_id=%s operation=%s risk=%s",
            record.approval_id,
            record.operation_type,
            record.risk_level,
        )
        return record.approval_id

    @classmethod
    def get(cls, approval_id: str) -> Optional[ApprovalRecord]:
        """Retrieve an approval record by ID.  Returns None if not found."""
        return cls._read_record(approval_id)

    @classmethod
    def approve(cls, approval_id: str, approved_by: str) -> ApprovalRecord:
        """Mark the approval record as APPROVED, persist, and return updated record.

        Args:
            approval_id: The ID of the approval to approve.
            approved_by: Identity of the approver.

        Returns:
            Updated ApprovalRecord with status=APPROVED.

        Raises:
            ApprovalNotFoundError: If no record exists for approval_id.
            ApprovalAlreadyDecidedError: If the record is not PENDING.
        """
        record = cls._read_record(approval_id)
        if record is None:
            raise ApprovalNotFoundError(
                f"Approval record '{approval_id}' not found."
            )
        if record.status != "PENDING":
            raise ApprovalAlreadyDecidedError(
                f"Approval '{approval_id}' is already in status '{record.status}'."
            )

        updated = record.model_copy(
            update={
                "status": "APPROVED",
                "approved_by": approved_by,
                "approved_at": datetime.now(timezone.utc),
            }
        )
        cls._write_record(updated)
        logger.info(
            "Approval APPROVED: approval_id=%s by=%s", approval_id, approved_by
        )
        return updated

    @classmethod
    def reject(
        cls, approval_id: str, rejected_by: str, reason: str
    ) -> ApprovalRecord:
        """Mark the approval record as REJECTED, persist, and return updated record.

        Args:
            approval_id: The ID of the approval to reject.
            rejected_by: Identity of the person rejecting.
            reason: Human-readable reason for rejection.

        Returns:
            Updated ApprovalRecord with status=REJECTED.

        Raises:
            ApprovalNotFoundError: If no record exists for approval_id.
            ApprovalAlreadyDecidedError: If the record is not PENDING.
        """
        record = cls._read_record(approval_id)
        if record is None:
            raise ApprovalNotFoundError(
                f"Approval record '{approval_id}' not found."
            )
        if record.status != "PENDING":
            raise ApprovalAlreadyDecidedError(
                f"Approval '{approval_id}' is already in status '{record.status}'."
            )

        updated = record.model_copy(
            update={
                "status": "REJECTED",
                "approved_by": rejected_by,
                "approved_at": datetime.now(timezone.utc),
                "rejection_reason": reason,
            }
        )
        cls._write_record(updated)
        logger.info(
            "Approval REJECTED: approval_id=%s by=%s reason=%s",
            approval_id,
            rejected_by,
            reason,
        )
        return updated

    @classmethod
    def list_pending(cls) -> list[ApprovalRecord]:
        """Return all approval records whose status is PENDING.

        Returns:
            List of ApprovalRecord instances, newest-first by requested_at.
        """
        store = cls._store_dir()
        pending: list[ApprovalRecord] = []
        for json_file in store.glob("*.json"):
            record = cls._read_record(json_file.stem)
            if record is not None and record.status == "PENDING":
                pending.append(record)

        pending.sort(key=lambda r: r.requested_at, reverse=True)
        return pending

    @classmethod
    def is_approved(cls, approval_id: str) -> bool:
        """Return True if the approval record exists and has status APPROVED."""
        record = cls._read_record(approval_id)
        return record is not None and record.status == "APPROVED"

    @classmethod
    def mark_mutations_approved(
        cls,
        mutations: list[JiraMutation],
        approval_id: str,
    ) -> list[JiraMutation]:
        """Set approved=True on mutations linked to an APPROVED approval record.

        Checks that the approval record exists and is APPROVED, then returns a
        new list of JiraMutation objects with approved=True for those whose
        mutation_id is referenced in the approval payload (key "mutation_ids"),
        or — if the payload has no such key — sets all passed mutations approved.

        Args:
            mutations: The mutations to potentially approve.
            approval_id: The approval record to check.

        Returns:
            A new list of JiraMutation instances (approved flag updated).
        """
        if not cls.is_approved(approval_id):
            logger.warning(
                "mark_mutations_approved called for non-approved approval_id=%s",
                approval_id,
            )
            return mutations

        record = cls._read_record(approval_id)
        if record is None:
            return mutations

        # If the approval payload carries explicit mutation IDs, use them;
        # otherwise approve all passed mutations.
        approved_ids: set[str] | None = None
        raw_ids = record.payload.get("mutation_ids")
        if isinstance(raw_ids, list):
            approved_ids = set(raw_ids)

        updated: list[JiraMutation] = []
        for mut in mutations:
            if approved_ids is None or mut.mutation_id in approved_ids:
                updated.append(mut.model_copy(update={"approved": True}))
            else:
                updated.append(mut)

        approved_count = sum(1 for m in updated if m.approved)
        logger.info(
            "Marked %d/%d mutations approved via approval_id=%s",
            approved_count,
            len(mutations),
            approval_id,
        )
        return updated


# ── CLI approval gate ─────────────────────────────────────────────────


def cli_approval_gate(record: ApprovalRecord) -> bool:
    """Interactive CLI prompt for human approval of a staged operation.

    Displays the operation details, risk level, and payload, then prompts
    the operator for a yes/no decision.  The decision is persisted back to
    the ApprovalStore.

    Args:
        record: The ApprovalRecord requiring a decision.

    Returns:
        True if the operator approved, False if rejected or an error occurred.
    """
    border = "=" * 60
    print(border)
    print("  APPROVAL REQUIRED")
    print(border)
    print(f"  Approval ID   : {record.approval_id}")
    print(f"  Operation     : {record.operation_type}")
    print(f"  Label         : {record.operation_label}")
    print(f"  Risk Level    : {record.risk_level}")
    print(f"  Requires Role : {record.requires_role}")
    print(f"  Requested By  : {record.requested_by or 'unknown'}")
    print(f"  Requested At  : {record.requested_at.isoformat()}")
    print(f"  Session ID    : {record.session_id}")
    print(f"  Trace ID      : {record.trace_id}")
    print()
    print("  Payload:")
    for key, value in record.payload.items():
        print(f"    {key}: {value}")
    print(border)

    try:
        response = input("  Approve this operation? [yes/no]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Approval cancelled — treating as REJECTED.")
        try:
            ApprovalStore.reject(
                record.approval_id,
                rejected_by="cli_operator",
                reason="Input cancelled by operator.",
            )
        except (ApprovalNotFoundError, ApprovalAlreadyDecidedError) as exc:
            logger.warning("Could not persist rejection after cancelled input: %s", exc)
        return False

    if response in {"yes", "y"}:
        try:
            approver = input("  Enter your name/ID [cli_operator]: ").strip() or "cli_operator"
        except (EOFError, KeyboardInterrupt):
            approver = "cli_operator"

        try:
            ApprovalStore.approve(record.approval_id, approved_by=approver)
        except (ApprovalNotFoundError, ApprovalAlreadyDecidedError) as exc:
            logger.error("Failed to persist approval: %s", exc)
            print(f"  ERROR: Could not save approval — {exc}")
            return False

        print(f"  Approved by {approver}.")
        print(border)
        return True

    # Any response other than yes is treated as a rejection
    try:
        reason = input("  Rejection reason (optional): ").strip() or "Rejected via CLI."
    except (EOFError, KeyboardInterrupt):
        reason = "Rejected via CLI."

    try:
        ApprovalStore.reject(
            record.approval_id,
            rejected_by="cli_operator",
            reason=reason,
        )
    except (ApprovalNotFoundError, ApprovalAlreadyDecidedError) as exc:
        logger.error("Failed to persist rejection: %s", exc)
        print(f"  ERROR: Could not save rejection — {exc}")

    print("  Operation REJECTED.")
    print(border)
    return False
