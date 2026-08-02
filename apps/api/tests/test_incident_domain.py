"""Pure policy tests for incident lifecycle, kill-switch, and exception rules."""

from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.domain.incidents import (
    ExceptionState,
    ExceptionStatus,
    IncidentDomainError,
    IncidentForbidden,
    IncidentStatus,
    evaluate_exception_state,
    require_remediation_plan_before_close,
    resulting_status_after_remediation_plan,
    transition_incident_status,
    validate_exception_decision,
    validate_exception_revocation,
    validate_kill_switch_engage,
    validate_kill_switch_restore,
)

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def test_incident_transitions_follow_the_allowed_forward_map() -> None:
    transition_incident_status(IncidentStatus.OPEN, IncidentStatus.CONTAINED)
    transition_incident_status(IncidentStatus.OPEN, IncidentStatus.REMEDIATING)
    transition_incident_status(IncidentStatus.CONTAINED, IncidentStatus.REMEDIATING)
    transition_incident_status(IncidentStatus.REMEDIATING, IncidentStatus.CLOSED)

    with pytest.raises(IncidentDomainError):
        transition_incident_status(IncidentStatus.CLOSED, IncidentStatus.OPEN)
    with pytest.raises(IncidentDomainError):
        transition_incident_status(IncidentStatus.CONTAINED, IncidentStatus.OPEN)
    with pytest.raises(IncidentDomainError):
        transition_incident_status(IncidentStatus.REMEDIATING, IncidentStatus.CONTAINED)


def test_remediation_plan_moves_open_or_contained_forward_and_is_idempotent() -> None:
    assert (
        resulting_status_after_remediation_plan(IncidentStatus.OPEN)
        is IncidentStatus.REMEDIATING
    )
    assert (
        resulting_status_after_remediation_plan(IncidentStatus.CONTAINED)
        is IncidentStatus.REMEDIATING
    )
    assert (
        resulting_status_after_remediation_plan(IncidentStatus.REMEDIATING)
        is IncidentStatus.REMEDIATING
    )
    with pytest.raises(IncidentDomainError):
        resulting_status_after_remediation_plan(IncidentStatus.CLOSED)


def test_closing_requires_a_complete_remediation_plan() -> None:
    with pytest.raises(IncidentDomainError):
        require_remediation_plan_before_close(
            remediation_owner_id=None,
            remediation_due_at=NOW,
            remediation_description="Rotate credentials",
        )
    with pytest.raises(IncidentDomainError):
        require_remediation_plan_before_close(
            remediation_owner_id="owner-1",
            remediation_due_at=None,
            remediation_description="Rotate credentials",
        )
    with pytest.raises(IncidentDomainError):
        require_remediation_plan_before_close(
            remediation_owner_id="owner-1",
            remediation_due_at=NOW,
            remediation_description="",
        )
    require_remediation_plan_before_close(
        remediation_owner_id="owner-1",
        remediation_due_at=NOW,
        remediation_description="Rotate credentials",
    )


def test_kill_switch_engage_requires_declared_switch_and_refuses_double_engagement() -> None:
    with pytest.raises(IncidentDomainError, match="closed"):
        validate_kill_switch_engage(
            kill_switch_enabled=True,
            already_engaged=False,
            status=IncidentStatus.CLOSED,
        )
    with pytest.raises(IncidentDomainError, match="declare"):
        validate_kill_switch_engage(
            kill_switch_enabled=False,
            already_engaged=False,
            status=IncidentStatus.OPEN,
        )
    with pytest.raises(IncidentDomainError, match="already engaged"):
        validate_kill_switch_engage(
            kill_switch_enabled=True,
            already_engaged=True,
            status=IncidentStatus.OPEN,
        )
    validate_kill_switch_engage(
        kill_switch_enabled=True,
        already_engaged=False,
        status=IncidentStatus.OPEN,
    )


def test_kill_switch_restore_requires_a_current_engagement() -> None:
    with pytest.raises(IncidentDomainError):
        validate_kill_switch_restore(already_engaged=False)
    validate_kill_switch_restore(already_engaged=True)


def test_exception_state_never_rewrites_status_and_expires_by_deadline() -> None:
    assert (
        evaluate_exception_state(status=ExceptionStatus.PENDING, expires_at=None, now=NOW)
        is ExceptionState.PENDING
    )
    assert (
        evaluate_exception_state(status=ExceptionStatus.REJECTED, expires_at=None, now=NOW)
        is ExceptionState.REJECTED
    )
    assert (
        evaluate_exception_state(status=ExceptionStatus.REVOKED, expires_at=None, now=NOW)
        is ExceptionState.REVOKED
    )
    assert (
        evaluate_exception_state(
            status=ExceptionStatus.APPROVED,
            expires_at=NOW + timedelta(days=1),
            now=NOW,
        )
        is ExceptionState.ACTIVE
    )
    assert (
        evaluate_exception_state(
            status=ExceptionStatus.APPROVED,
            expires_at=NOW - timedelta(seconds=1),
            now=NOW,
        )
        is ExceptionState.EXPIRED
    )


def test_exception_decision_enforces_segregation_of_duties() -> None:
    with pytest.raises(IncidentDomainError):
        validate_exception_decision(
            requested_by="requester",
            decided_by="admin",
            current_status=ExceptionStatus.APPROVED,
        )
    with pytest.raises(IncidentForbidden):
        validate_exception_decision(
            requested_by="requester",
            decided_by="requester",
            current_status=ExceptionStatus.PENDING,
        )
    validate_exception_decision(
        requested_by="requester",
        decided_by="admin",
        current_status=ExceptionStatus.PENDING,
    )


def test_exception_revocation_allowed_only_while_pending_or_approved() -> None:
    validate_exception_revocation(current_status=ExceptionStatus.PENDING)
    validate_exception_revocation(current_status=ExceptionStatus.APPROVED)
    with pytest.raises(IncidentDomainError):
        validate_exception_revocation(current_status=ExceptionStatus.REJECTED)
    with pytest.raises(IncidentDomainError):
        validate_exception_revocation(current_status=ExceptionStatus.REVOKED)
