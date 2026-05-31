"""Role-Based Access Control enforcement for the LangGraph JIRA AI Agent."""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class Role(str, Enum):
    DEVELOPER = "developer"
    TECH_LEAD = "tech_lead"
    SCRUM_MASTER = "scrum_master"
    PRODUCT_OWNER = "product_owner"
    ADMIN = "admin"


# Numeric rank — higher is more privileged
ROLE_HIERARCHY: dict[Role, int] = {
    Role.DEVELOPER: 0,
    Role.TECH_LEAD: 1,
    Role.SCRUM_MASTER: 2,
    Role.PRODUCT_OWNER: 3,
    Role.ADMIN: 4,
}

# operation_type -> minimum Role required to approve
APPROVAL_POLICY: dict[str, Role] = {
    "TICKET_CREATE": Role.TECH_LEAD,
    "TICKET_UPDATE": Role.TECH_LEAD,
    "TICKET_DELETE": Role.SCRUM_MASTER,
    "BULK_PRIORITY_UPDATE": Role.SCRUM_MASTER,
    "SPRINT_CREATE": Role.SCRUM_MASTER,
    "SPRINT_CLOSE": Role.PRODUCT_OWNER,
    "ASSIGNMENT_CHANGE": Role.TECH_LEAD,
    "RELEASE_ACTION": Role.PRODUCT_OWNER,
    "ESCALATION": Role.SCRUM_MASTER,
    "EPIC_DECOMPOSE": Role.TECH_LEAD,
    "ADD_TO_SPRINT": Role.SCRUM_MASTER,
    "TRANSITION": Role.TECH_LEAD,
}

# Operations that any authenticated user can initiate (request/stage), even if
# they cannot approve. If an operation is NOT in this set, only TECH_LEAD+
# may even initiate it.
_INITIATE_POLICY: dict[str, Role] = {
    "TICKET_CREATE": Role.DEVELOPER,
    "TICKET_UPDATE": Role.DEVELOPER,
    "TICKET_DELETE": Role.TECH_LEAD,
    "BULK_PRIORITY_UPDATE": Role.TECH_LEAD,
    "SPRINT_CREATE": Role.SCRUM_MASTER,
    "SPRINT_CLOSE": Role.SCRUM_MASTER,
    "ASSIGNMENT_CHANGE": Role.DEVELOPER,
    "RELEASE_ACTION": Role.PRODUCT_OWNER,
    "ESCALATION": Role.DEVELOPER,
    "EPIC_DECOMPOSE": Role.DEVELOPER,
    "ADD_TO_SPRINT": Role.DEVELOPER,
    "TRANSITION": Role.DEVELOPER,
}


class PermissionDeniedError(PermissionError):
    """Raised when an RBAC check fails."""


class UnknownOperationError(ValueError):
    """Raised when an operation_type is not registered in the policy."""


class RBACEnforcer:
    """Stateless RBAC enforcement helpers."""

    @staticmethod
    def _resolve_role(role: str) -> Role:
        """Parse a role string into a Role enum, raising ValueError if invalid."""
        try:
            return Role(role.lower())
        except ValueError as exc:
            valid = [r.value for r in Role]
            raise ValueError(
                f"Unknown role '{role}'. Valid roles: {valid}"
            ) from exc

    @staticmethod
    def minimum_role_for(operation_type: str) -> Role:
        """Return the minimum Role that may approve *operation_type*.

        Raises UnknownOperationError if the operation is not in APPROVAL_POLICY.
        """
        op = operation_type.upper()
        if op not in APPROVAL_POLICY:
            raise UnknownOperationError(
                f"No approval policy defined for operation '{operation_type}'. "
                f"Registered operations: {list(APPROVAL_POLICY.keys())}"
            )
        return APPROVAL_POLICY[op]

    @staticmethod
    def can_approve(role: str, operation_type: str) -> bool:
        """Return True if *role* has sufficient privilege to approve *operation_type*.

        Unknown roles return False; unknown operations return False (fail-safe).
        """
        try:
            resolved = RBACEnforcer._resolve_role(role)
            min_role = RBACEnforcer.minimum_role_for(operation_type)
        except (ValueError, UnknownOperationError) as exc:
            logger.warning("RBAC can_approve check failed: %s", exc)
            return False

        caller_rank = ROLE_HIERARCHY.get(resolved, -1)
        required_rank = ROLE_HIERARCHY.get(min_role, 999)
        return caller_rank >= required_rank

    @staticmethod
    def assert_can_approve(role: str, operation_type: str) -> None:
        """Raise PermissionDeniedError if *role* cannot approve *operation_type*.

        Args:
            role: The caller's role string (e.g. "tech_lead").
            operation_type: The operation being approved (e.g. "TICKET_CREATE").

        Raises:
            PermissionDeniedError: If the role is insufficient.
            UnknownOperationError: If the operation is not in the policy.
            ValueError: If the role string is not a valid Role.
        """
        resolved = RBACEnforcer._resolve_role(role)
        min_role = RBACEnforcer.minimum_role_for(operation_type)

        caller_rank = ROLE_HIERARCHY.get(resolved, -1)
        required_rank = ROLE_HIERARCHY.get(min_role, 999)

        if caller_rank < required_rank:
            raise PermissionDeniedError(
                f"Role '{role}' (rank {caller_rank}) cannot approve "
                f"'{operation_type}'. Minimum required: '{min_role.value}' "
                f"(rank {required_rank})."
            )
        logger.debug(
            "RBAC APPROVED: role=%s operation=%s", role, operation_type
        )

    @staticmethod
    def can_initiate(role: str, operation_type: str) -> bool:
        """Return True if *role* may initiate (stage/request) *operation_type*.

        Unknown roles/operations return False (fail-safe).
        """
        try:
            resolved = RBACEnforcer._resolve_role(role)
            op = operation_type.upper()
            min_role = _INITIATE_POLICY.get(op)
            if min_role is None:
                # Not explicitly listed — fall back to approval policy minimum
                min_role = RBACEnforcer.minimum_role_for(op)
        except (ValueError, UnknownOperationError) as exc:
            logger.warning("RBAC can_initiate check failed: %s", exc)
            return False

        caller_rank = ROLE_HIERARCHY.get(resolved, -1)
        required_rank = ROLE_HIERARCHY.get(min_role, 999)
        return caller_rank >= required_rank

    @staticmethod
    def assert_can_initiate(role: str, operation_type: str) -> None:
        """Raise PermissionDeniedError if *role* may not initiate *operation_type*.

        Args:
            role: The caller's role string.
            operation_type: The operation being staged.

        Raises:
            PermissionDeniedError: If the role is insufficient to even initiate.
            ValueError: If the role string is invalid.
        """
        resolved = RBACEnforcer._resolve_role(role)
        op = operation_type.upper()

        min_role = _INITIATE_POLICY.get(op)
        if min_role is None:
            try:
                min_role = RBACEnforcer.minimum_role_for(op)
            except UnknownOperationError:
                # If we have no policy at all, require ADMIN to be safe
                min_role = Role.ADMIN

        caller_rank = ROLE_HIERARCHY.get(resolved, -1)
        required_rank = ROLE_HIERARCHY.get(min_role, 999)

        if caller_rank < required_rank:
            raise PermissionDeniedError(
                f"Role '{role}' (rank {caller_rank}) cannot initiate "
                f"'{operation_type}'. Minimum required: '{min_role.value}' "
                f"(rank {required_rank})."
            )
        logger.debug(
            "RBAC INITIATE OK: role=%s operation=%s", role, operation_type
        )
