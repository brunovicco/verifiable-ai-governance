"""Pure incident lifecycle, kill-switch, and temporary-exception policies."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from governance_schemas import RiskTier


class IncidentDomainError(ValueError):
    """Raised when an incident, kill-switch, or exception command is invalid."""


class IncidentForbidden(IncidentDomainError):
    """Raised when segregation of duties blocks a decision."""


class IncidentStatus(StrEnum):
    """Lifecycle of one operational incident."""

    OPEN = "open"
    CONTAINED = "contained"
    REMEDIATING = "remediating"
    CLOSED = "closed"


class ExceptionStatus(StrEnum):
    """Persisted decision state of one temporary exception request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class ExceptionState(StrEnum):
    """Computed validity of an exception, distinct from its persisted status."""

    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REJECTED = "rejected"
    REVOKED = "revoked"


_ALLOWED_INCIDENT_TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    IncidentStatus.OPEN: frozenset({IncidentStatus.CONTAINED, IncidentStatus.REMEDIATING}),
    IncidentStatus.CONTAINED: frozenset({IncidentStatus.REMEDIATING}),
    IncidentStatus.REMEDIATING: frozenset({IncidentStatus.CLOSED}),
    IncidentStatus.CLOSED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class IncidentSystemContext:
    """Minimal, trusted AI system facts required to authorize incident commands."""

    ai_system_id: str
    ai_system_owner_id: str


@dataclass(frozen=True, slots=True)
class AgentKillSwitchState:
    """Minimal agent facts required to enforce kill-switch commands."""

    id: str
    ai_system_id: str
    kill_switch_enabled: bool
    kill_switch_engaged: bool
    version: int


@dataclass(frozen=True, slots=True)
class IncidentRecord:
    """Durable projection of one operational incident and its remediation plan."""

    id: str
    ai_system_id: str
    title: str
    severity: RiskTier
    status: IncidentStatus
    description: str
    detected_at: datetime
    owner_id: str
    containment: str | None
    remediation_owner_id: str | None
    remediation_description: str | None
    remediation_due_at: datetime | None
    resolved_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PolicyExceptionRecord:
    """Durable projection of one temporary exception requested during an incident."""

    id: str
    incident_id: str
    ai_system_id: str
    requested_by: str
    requested_at: datetime
    purpose: str
    scope_description: str
    compensating_controls: str
    expires_at: datetime
    status: ExceptionStatus
    decided_by: str | None
    decided_at: datetime | None
    decision_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime


def transition_incident_status(current: IncidentStatus, target: IncidentStatus) -> None:
    """Allow only the explicit forward transitions of the incident lifecycle."""
    if target not in _ALLOWED_INCIDENT_TRANSITIONS[current]:
        raise IncidentDomainError(f"Cannot move incident from {current.value} to {target.value}")


def resulting_status_after_remediation_plan(current: IncidentStatus) -> IncidentStatus:
    """Move an open or contained incident into remediation, or keep it there."""
    if current is IncidentStatus.REMEDIATING:
        return current
    transition_incident_status(current, IncidentStatus.REMEDIATING)
    return IncidentStatus.REMEDIATING


def require_remediation_plan_before_close(
    *,
    remediation_owner_id: str | None,
    remediation_due_at: datetime | None,
    remediation_description: str | None,
) -> None:
    """Refuse to close an incident without a recorded remediation plan."""
    if not remediation_owner_id or remediation_due_at is None or not remediation_description:
        raise IncidentDomainError("Incident requires a recorded remediation plan before closing")


def validate_kill_switch_engage(
    *,
    kill_switch_enabled: bool,
    already_engaged: bool,
    status: IncidentStatus,
) -> None:
    """Refuse to engage a kill switch that was never declared, on a closed incident."""
    if status is IncidentStatus.CLOSED:
        raise IncidentDomainError("Cannot engage a kill switch on a closed incident")
    if not kill_switch_enabled:
        raise IncidentDomainError("Agent does not declare an available kill switch")
    if already_engaged:
        raise IncidentDomainError("Kill switch is already engaged")


def validate_kill_switch_restore(*, already_engaged: bool) -> None:
    """Refuse to restore a kill switch that is not currently engaged."""
    if not already_engaged:
        raise IncidentDomainError("Kill switch is not engaged")


def evaluate_exception_state(
    *,
    status: ExceptionStatus,
    expires_at: datetime | None,
    now: datetime,
) -> ExceptionState:
    """Classify a persisted exception without ever rewriting its stored status."""
    if status is ExceptionStatus.PENDING:
        return ExceptionState.PENDING
    if status is ExceptionStatus.REJECTED:
        return ExceptionState.REJECTED
    if status is ExceptionStatus.REVOKED:
        return ExceptionState.REVOKED
    if expires_at is not None and now < expires_at:
        return ExceptionState.ACTIVE
    return ExceptionState.EXPIRED


def validate_exception_decision(
    *,
    requested_by: str,
    decided_by: str,
    current_status: ExceptionStatus,
) -> None:
    """Enforce segregation of duties between an exception's requester and decider."""
    if current_status is not ExceptionStatus.PENDING:
        raise IncidentDomainError("Exception is not pending a decision")
    if requested_by == decided_by:
        raise IncidentForbidden("Exception cannot be approved or rejected by its own requester")


def validate_exception_revocation(*, current_status: ExceptionStatus) -> None:
    """Allow revocation only while an exception is pending or approved."""
    if current_status not in {ExceptionStatus.PENDING, ExceptionStatus.APPROVED}:
        raise IncidentDomainError("Only a pending or approved exception can be revoked")
