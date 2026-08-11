"""Pure governed kill-switch restore contracts and canonical evidence rules."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from governance_schemas import ApprovalArea

from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecution,
)
from ai_governance_api.domain.runtime_control import (
    RuntimeControlState,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
)

RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION = "1.0"
RUNTIME_ASSURANCE_RESTORE_APPROVAL_AREA = ApprovalArea.SECURITY
RUNTIME_ASSURANCE_RESTORE_EVIDENCE_PREFIX = "runtime-assurance-restore-decision"
RUNTIME_ASSURANCE_RESTORE_RUNTIME_REASON = "Governed Runtime Assurance kill-switch restore"
MAX_RUNTIME_ASSURANCE_RESTORE_REASON_LENGTH = 2000


class RuntimeAssuranceRestoreDomainError(ValueError):
    """Raised when governed restore evidence or preconditions are invalid."""


class RuntimeAssuranceRestoreAction(StrEnum):
    """Closed governed restore vocabulary for P1.9d."""

    RESTORE_KILL_SWITCH = "restore_kill_switch"


class RuntimeAssuranceRestoreRequestState(StrEnum):
    """Immutable genesis state of one restore request."""

    PENDING = "pending"


class RuntimeAssuranceRestoreDecisionOutcome(StrEnum):
    """Terminal human decisions supported by the restore workflow."""

    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceRestoreSourceContext:
    """Validated engage execution plus fresh incident and Agent recovery facts."""

    source_execution: RuntimeAssuranceActuationExecution
    ai_system_owner_id: str
    agent_version: int
    kill_switch_enabled: bool
    kill_switch_engaged: bool
    incident_status: IncidentStatus
    incident_version: int
    remediation_owner_id: str | None
    remediation_description: str | None
    remediation_due_at: datetime | None
    resolved_at: datetime | None
    latest_transition: RuntimeControlTransitionRecord | None


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceRestoreRequest:
    """Immutable restore intent bound to one engage execution and remediation snapshot."""

    id: str
    schema_version: str
    source_execution_id: str
    source_execution_digest: str
    agent_id: str
    ai_system_id: str
    incident_id: str
    action: RuntimeAssuranceRestoreAction
    state: RuntimeAssuranceRestoreRequestState
    remediation_digest: str
    incident_status: IncidentStatus
    incident_version: int
    requested_by: str
    requested_at: datetime
    request_digest: str
    version: int = 1


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceRestoreDecision:
    """Append-only terminal human decision for one immutable restore request."""

    id: str
    schema_version: str
    request_id: str
    request_digest: str
    source_execution_id: str
    source_execution_digest: str
    action: RuntimeAssuranceRestoreAction
    decision: RuntimeAssuranceRestoreDecisionOutcome
    approval_area: ApprovalArea
    decided_by: str
    decided_at: datetime
    reason: str
    decision_digest: str
    version: int = 1


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceRestoreExecutionContext:
    """Approved restore lineage plus fresh execution-time Runtime Control state."""

    decision: RuntimeAssuranceRestoreDecision
    request: RuntimeAssuranceRestoreRequest
    source: RuntimeAssuranceRestoreSourceContext
    matching_transition: RuntimeControlTransitionRecord | None


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceRestoreExecution:
    """Immutable receipt proving one approved restore was applied."""

    id: str
    schema_version: str
    decision_id: str
    decision_digest: str
    request_id: str
    request_digest: str
    source_execution_id: str
    source_execution_digest: str
    action: RuntimeAssuranceRestoreAction
    agent_id: str
    ai_system_id: str
    incident_id: str
    runtime_transition_id: str
    control_epoch: int
    previous_state: RuntimeControlState
    target_state: RuntimeControlState
    revoked_through_agent_version: int
    resulting_agent_version: int
    executed_by: str
    executed_at: datetime
    execution_digest: str
    version: int = 1


def normalize_restore_reason(reason: str) -> str:
    """Return a canonical bounded human reason or fail closed."""
    normalized = reason.strip()
    if not normalized:
        raise RuntimeAssuranceRestoreDomainError("Restore decision reason must not be empty")
    if len(normalized) > MAX_RUNTIME_ASSURANCE_RESTORE_REASON_LENGTH:
        raise RuntimeAssuranceRestoreDomainError("Restore decision reason exceeds its size limit")
    return normalized


def build_remediation_digest(context: RuntimeAssuranceRestoreSourceContext) -> str:
    """Commit to the exact remediation evidence visible when restore is requested."""
    _validate_remediation_snapshot(context)
    canonical: Mapping[str, object] = {
        "incident_id": context.source_execution.incident_id,
        "incident_status": context.incident_status.value,
        "incident_version": context.incident_version,
        "remediation_owner_id": context.remediation_owner_id,
        "remediation_description": context.remediation_description,
        "remediation_due_at": _iso(context.remediation_due_at),
        "resolved_at": _iso(context.resolved_at),
    }
    return _sha(canonical)


def validate_restore_source_eligibility(context: RuntimeAssuranceRestoreSourceContext) -> None:
    """Require recovery evidence and the original engage transition to still be authoritative."""
    execution = context.source_execution
    if context.incident_status not in {IncidentStatus.REMEDIATING, IncidentStatus.CLOSED}:
        raise RuntimeAssuranceRestoreDomainError(
            "Restore requires an incident in remediating or closed state"
        )
    _validate_remediation_snapshot(context)
    if not context.kill_switch_enabled:
        raise RuntimeAssuranceRestoreDomainError("Agent does not declare an available kill switch")
    if not context.kill_switch_engaged:
        raise RuntimeAssuranceRestoreDomainError("Kill switch is not currently engaged")
    if context.agent_version <= 0:
        raise RuntimeAssuranceRestoreDomainError("Agent version is invalid")
    latest = context.latest_transition
    if latest is None:
        raise RuntimeAssuranceRestoreDomainError(
            "Runtime Control transition history is unavailable"
        )
    if (
        latest.id != execution.runtime_transition_id
        or latest.status is not RuntimeControlTransitionStatus.APPLIED
        or latest.previous_state is not RuntimeControlState.INACTIVE
        or latest.target_state is not RuntimeControlState.ACTIVE
        or latest.agent_id != execution.agent_id
        or latest.ai_system_id != execution.ai_system_id
        or latest.incident_id != execution.incident_id
    ):
        raise RuntimeAssuranceRestoreDomainError(
            "The source engage execution is no longer the authoritative Runtime Control state"
        )


def build_restore_request_digest(
    *,
    request_id: str,
    source_execution_id: str,
    source_execution_digest: str,
    agent_id: str,
    ai_system_id: str,
    incident_id: str,
    action: RuntimeAssuranceRestoreAction,
    state: RuntimeAssuranceRestoreRequestState,
    remediation_digest: str,
    incident_status: IncidentStatus,
    incident_version: int,
    requested_by: str,
    requested_at: datetime,
    schema_version: str = RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION,
    version: int = 1,
) -> str:
    """Return canonical SHA-256 over immutable restore request evidence."""
    _require_schema_version(schema_version, version)
    if not _is_sha256(source_execution_digest) or not _is_sha256(remediation_digest):
        raise RuntimeAssuranceRestoreDomainError("Restore source or remediation digest is invalid")
    if action is not RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH:
        raise RuntimeAssuranceRestoreDomainError("Unsupported restore action")
    if state is not RuntimeAssuranceRestoreRequestState.PENDING:
        raise RuntimeAssuranceRestoreDomainError("Unsupported restore request state")
    if incident_status not in {IncidentStatus.REMEDIATING, IncidentStatus.CLOSED}:
        raise RuntimeAssuranceRestoreDomainError("Invalid restore incident snapshot")
    if incident_version <= 0:
        raise RuntimeAssuranceRestoreDomainError("Restore incident version is invalid")
    _require_identity(request_id, "Restore request ID")
    _require_identity(source_execution_id, "Source execution ID")
    _require_identity(agent_id, "Agent ID")
    _require_identity(ai_system_id, "AI System ID")
    _require_identity(incident_id, "Incident ID")
    _require_identity(requested_by, "Restore requester")
    _require_aware(requested_at, "Restore request timestamp")
    canonical: Mapping[str, object] = {
        "schema_version": schema_version,
        "request_id": request_id,
        "source_execution_id": source_execution_id,
        "source_execution_digest": source_execution_digest,
        "agent_id": agent_id,
        "ai_system_id": ai_system_id,
        "incident_id": incident_id,
        "action": action.value,
        "state": state.value,
        "remediation_digest": remediation_digest,
        "incident_status": incident_status.value,
        "incident_version": incident_version,
        "requested_by": requested_by,
        "requested_at": requested_at.astimezone(UTC).isoformat(),
        "version": version,
    }
    return _sha(canonical)


def validate_restore_request_binding(
    request: RuntimeAssuranceRestoreRequest,
    source_execution: RuntimeAssuranceActuationExecution,
) -> None:
    """Reject cross-execution reuse or tampered restore request evidence."""
    if (
        request.source_execution_id != source_execution.id
        or request.source_execution_digest != source_execution.execution_digest
        or request.agent_id != source_execution.agent_id
        or request.ai_system_id != source_execution.ai_system_id
        or request.incident_id != source_execution.incident_id
        or request.action is not RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH
        or request.state is not RuntimeAssuranceRestoreRequestState.PENDING
        or request.schema_version != RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION
        or request.version != 1
    ):
        raise RuntimeAssuranceRestoreDomainError("Restore request binding is inconsistent")
    expected = build_restore_request_digest(
        request_id=request.id,
        source_execution_id=request.source_execution_id,
        source_execution_digest=request.source_execution_digest,
        agent_id=request.agent_id,
        ai_system_id=request.ai_system_id,
        incident_id=request.incident_id,
        action=request.action,
        state=request.state,
        remediation_digest=request.remediation_digest,
        incident_status=request.incident_status,
        incident_version=request.incident_version,
        requested_by=request.requested_by,
        requested_at=request.requested_at,
        schema_version=request.schema_version,
        version=request.version,
    )
    if request.request_digest != expected:
        raise RuntimeAssuranceRestoreDomainError("Restore request digest is inconsistent")


def validate_restore_request_current(
    request: RuntimeAssuranceRestoreRequest,
    source: RuntimeAssuranceRestoreSourceContext,
) -> None:
    """Require the immutable request's remediation snapshot to still be current."""
    validate_restore_request_binding(request, source.source_execution)
    validate_restore_source_eligibility(source)
    current_digest = build_remediation_digest(source)
    if current_digest != request.remediation_digest:
        raise RuntimeAssuranceRestoreDomainError("Restore request remediation evidence is stale")


def build_restore_decision_digest(
    *,
    decision_id: str,
    request_id: str,
    request_digest: str,
    source_execution_id: str,
    source_execution_digest: str,
    action: RuntimeAssuranceRestoreAction,
    decision: RuntimeAssuranceRestoreDecisionOutcome,
    approval_area: ApprovalArea,
    decided_by: str,
    decided_at: datetime,
    reason: str,
    schema_version: str = RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION,
    version: int = 1,
) -> str:
    """Return canonical SHA-256 over immutable restore decision evidence."""
    _require_schema_version(schema_version, version)
    if not _is_sha256(request_digest) or not _is_sha256(source_execution_digest):
        raise RuntimeAssuranceRestoreDomainError("Restore decision source digest is invalid")
    if action is not RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH:
        raise RuntimeAssuranceRestoreDomainError("Unsupported restore decision action")
    if approval_area is not RUNTIME_ASSURANCE_RESTORE_APPROVAL_AREA:
        raise RuntimeAssuranceRestoreDomainError("Restore approval area is invalid")
    _require_identity(decision_id, "Restore decision ID")
    _require_identity(request_id, "Restore request ID")
    _require_identity(source_execution_id, "Source execution ID")
    _require_identity(decided_by, "Restore approver")
    _require_aware(decided_at, "Restore decision timestamp")
    canonical_reason = normalize_restore_reason(reason)
    canonical: Mapping[str, object] = {
        "schema_version": schema_version,
        "decision_id": decision_id,
        "request_id": request_id,
        "request_digest": request_digest,
        "source_execution_id": source_execution_id,
        "source_execution_digest": source_execution_digest,
        "action": action.value,
        "decision": decision.value,
        "approval_area": approval_area.value,
        "decided_by": decided_by,
        "decided_at": decided_at.astimezone(UTC).isoformat(),
        "reason": canonical_reason,
        "version": version,
    }
    return _sha(canonical)


def validate_restore_decision_binding(
    decision: RuntimeAssuranceRestoreDecision,
    request: RuntimeAssuranceRestoreRequest,
) -> None:
    """Reject cross-request reuse or tampered restore decision evidence."""
    if (
        decision.request_id != request.id
        or decision.request_digest != request.request_digest
        or decision.source_execution_id != request.source_execution_id
        or decision.source_execution_digest != request.source_execution_digest
        or decision.action is not request.action
        or decision.approval_area is not RUNTIME_ASSURANCE_RESTORE_APPROVAL_AREA
        or decision.schema_version != RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION
        or decision.version != 1
    ):
        raise RuntimeAssuranceRestoreDomainError("Restore decision binding is inconsistent")
    expected = build_restore_decision_digest(
        decision_id=decision.id,
        request_id=decision.request_id,
        request_digest=decision.request_digest,
        source_execution_id=decision.source_execution_id,
        source_execution_digest=decision.source_execution_digest,
        action=decision.action,
        decision=decision.decision,
        approval_area=decision.approval_area,
        decided_by=decision.decided_by,
        decided_at=decision.decided_at,
        reason=decision.reason,
        schema_version=decision.schema_version,
        version=decision.version,
    )
    if decision.decision_digest != expected:
        raise RuntimeAssuranceRestoreDomainError("Restore decision digest is inconsistent")


def restore_decision_evidence_reference(decision: RuntimeAssuranceRestoreDecision) -> str:
    """Return the Runtime Control evidence reference for one approved restore decision."""
    if decision.decision is not RuntimeAssuranceRestoreDecisionOutcome.APPROVED:
        raise RuntimeAssuranceRestoreDomainError("Only approved restore decisions can be executed")
    if decision.action is not RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH:
        raise RuntimeAssuranceRestoreDomainError("Unsupported restore decision action")
    if not decision.id.strip() or not _is_sha256(decision.decision_digest):
        raise RuntimeAssuranceRestoreDomainError("Restore decision identity or digest is invalid")
    return f"{RUNTIME_ASSURANCE_RESTORE_EVIDENCE_PREFIX}:{decision.id}:{decision.decision_digest}"


def validate_new_restore_execution_preconditions(
    context: RuntimeAssuranceRestoreExecutionContext,
) -> None:
    """Require fresh recovery and Runtime Control state before a new restore transition."""
    decision = context.decision
    request = context.request
    source = context.source
    if decision.decision is not RuntimeAssuranceRestoreDecisionOutcome.APPROVED:
        raise RuntimeAssuranceRestoreDomainError("Restore decision is not approved")
    validate_restore_decision_binding(decision, request)
    validate_restore_request_current(request, source)
    if context.matching_transition is not None:
        raise RuntimeAssuranceRestoreDomainError(
            "A Runtime Control restore transition already exists for this decision"
        )


def validate_restore_transition_binding(
    context: RuntimeAssuranceRestoreExecutionContext,
    transition: RuntimeControlTransitionRecord,
) -> None:
    """Reject Runtime Control evidence not bound to the approved restore chain."""
    reference = restore_decision_evidence_reference(context.decision)
    request = context.request
    if (
        transition.agent_id != request.agent_id
        or transition.ai_system_id != request.ai_system_id
        or transition.incident_id != request.incident_id
        or transition.evidence_reference != reference
        or transition.previous_state is not RuntimeControlState.ACTIVE
        or transition.target_state is not RuntimeControlState.INACTIVE
        or transition.control_epoch <= context.source.source_execution.control_epoch
        or transition.revoked_through_agent_version <= 0
        or not transition.requested_by.strip()
    ):
        raise RuntimeAssuranceRestoreDomainError(
            "Runtime Control restore transition binding is inconsistent"
        )
    if transition.status is RuntimeControlTransitionStatus.APPLIED:
        if transition.applied_at is None:
            raise RuntimeAssuranceRestoreDomainError(
                "Applied Runtime Control restore transition is missing its timestamp"
            )
        _require_aware(transition.applied_at, "Runtime Control restore applied timestamp")


def build_restore_execution_receipt(
    *,
    execution_id: str,
    context: RuntimeAssuranceRestoreExecutionContext,
    transition: RuntimeControlTransitionRecord,
) -> RuntimeAssuranceRestoreExecution:
    """Build immutable restore execution evidence from an applied transition."""
    validate_restore_transition_binding(context, transition)
    if transition.status is not RuntimeControlTransitionStatus.APPLIED:
        raise RuntimeAssuranceRestoreDomainError(
            "Runtime Control restore transition has not been applied"
        )
    applied_at = transition.applied_at
    if applied_at is None:
        raise RuntimeAssuranceRestoreDomainError(
            "Applied Runtime Control restore transition is missing its timestamp"
        )
    resulting_agent_version = transition.revoked_through_agent_version + 1
    digest = build_restore_execution_digest(
        execution_id=execution_id,
        decision_id=context.decision.id,
        decision_digest=context.decision.decision_digest,
        request_id=context.request.id,
        request_digest=context.request.request_digest,
        source_execution_id=context.request.source_execution_id,
        source_execution_digest=context.request.source_execution_digest,
        action=context.request.action,
        agent_id=context.request.agent_id,
        ai_system_id=context.request.ai_system_id,
        incident_id=context.request.incident_id,
        runtime_transition_id=transition.id,
        control_epoch=transition.control_epoch,
        previous_state=transition.previous_state,
        target_state=transition.target_state,
        revoked_through_agent_version=transition.revoked_through_agent_version,
        resulting_agent_version=resulting_agent_version,
        executed_by=transition.requested_by,
        executed_at=applied_at,
    )
    return RuntimeAssuranceRestoreExecution(
        id=execution_id,
        schema_version=RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION,
        decision_id=context.decision.id,
        decision_digest=context.decision.decision_digest,
        request_id=context.request.id,
        request_digest=context.request.request_digest,
        source_execution_id=context.request.source_execution_id,
        source_execution_digest=context.request.source_execution_digest,
        action=context.request.action,
        agent_id=context.request.agent_id,
        ai_system_id=context.request.ai_system_id,
        incident_id=context.request.incident_id,
        runtime_transition_id=transition.id,
        control_epoch=transition.control_epoch,
        previous_state=transition.previous_state,
        target_state=transition.target_state,
        revoked_through_agent_version=transition.revoked_through_agent_version,
        resulting_agent_version=resulting_agent_version,
        executed_by=transition.requested_by,
        executed_at=applied_at,
        execution_digest=digest,
    )


def build_restore_execution_digest(
    *,
    execution_id: str,
    decision_id: str,
    decision_digest: str,
    request_id: str,
    request_digest: str,
    source_execution_id: str,
    source_execution_digest: str,
    action: RuntimeAssuranceRestoreAction,
    agent_id: str,
    ai_system_id: str,
    incident_id: str,
    runtime_transition_id: str,
    control_epoch: int,
    previous_state: RuntimeControlState,
    target_state: RuntimeControlState,
    revoked_through_agent_version: int,
    resulting_agent_version: int,
    executed_by: str,
    executed_at: datetime,
    schema_version: str = RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION,
    version: int = 1,
) -> str:
    """Return canonical SHA-256 over one applied restore execution receipt."""
    _require_schema_version(schema_version, version)
    if not all(
        _is_sha256(value) for value in (decision_digest, request_digest, source_execution_digest)
    ):
        raise RuntimeAssuranceRestoreDomainError("Restore execution source digest is invalid")
    if action is not RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH:
        raise RuntimeAssuranceRestoreDomainError("Unsupported restore execution action")
    if (
        previous_state is not RuntimeControlState.ACTIVE
        or target_state is not RuntimeControlState.INACTIVE
    ):
        raise RuntimeAssuranceRestoreDomainError("Restore execution states are invalid")
    if control_epoch <= 0 or revoked_through_agent_version <= 0:
        raise RuntimeAssuranceRestoreDomainError("Restore execution runtime version is invalid")
    if resulting_agent_version != revoked_through_agent_version + 1:
        raise RuntimeAssuranceRestoreDomainError("Restore resulting Agent version is invalid")
    for value, label in (
        (execution_id, "Restore execution ID"),
        (decision_id, "Restore decision ID"),
        (request_id, "Restore request ID"),
        (source_execution_id, "Source execution ID"),
        (agent_id, "Agent ID"),
        (ai_system_id, "AI System ID"),
        (incident_id, "Incident ID"),
        (runtime_transition_id, "Runtime transition ID"),
        (executed_by, "Restore executor"),
    ):
        _require_identity(value, label)
    _require_aware(executed_at, "Restore execution timestamp")
    canonical: Mapping[str, object] = {
        "schema_version": schema_version,
        "execution_id": execution_id,
        "decision_id": decision_id,
        "decision_digest": decision_digest,
        "request_id": request_id,
        "request_digest": request_digest,
        "source_execution_id": source_execution_id,
        "source_execution_digest": source_execution_digest,
        "action": action.value,
        "agent_id": agent_id,
        "ai_system_id": ai_system_id,
        "incident_id": incident_id,
        "runtime_transition_id": runtime_transition_id,
        "control_epoch": control_epoch,
        "previous_state": previous_state.value,
        "target_state": target_state.value,
        "revoked_through_agent_version": revoked_through_agent_version,
        "resulting_agent_version": resulting_agent_version,
        "executed_by": executed_by,
        "executed_at": executed_at.astimezone(UTC).isoformat(),
        "version": version,
    }
    return _sha(canonical)


def validate_restore_execution_binding(
    execution: RuntimeAssuranceRestoreExecution,
    context: RuntimeAssuranceRestoreExecutionContext,
) -> None:
    """Reject cross-decision reuse, transition substitution, or receipt tampering."""
    transition = context.matching_transition
    if transition is None:
        raise RuntimeAssuranceRestoreDomainError(
            "Runtime Control transition for restore execution evidence is missing"
        )
    validate_restore_transition_binding(context, transition)
    if transition.status is not RuntimeControlTransitionStatus.APPLIED:
        raise RuntimeAssuranceRestoreDomainError(
            "Restore execution evidence references a non-applied Runtime Control transition"
        )
    expected = build_restore_execution_receipt(
        execution_id=execution.id,
        context=context,
        transition=transition,
    )
    if execution != expected:
        raise RuntimeAssuranceRestoreDomainError(
            "Runtime Assurance restore execution binding is inconsistent"
        )


def _validate_remediation_snapshot(context: RuntimeAssuranceRestoreSourceContext) -> None:
    if context.incident_version <= 0:
        raise RuntimeAssuranceRestoreDomainError("Incident version is invalid")
    if not context.remediation_owner_id or not context.remediation_description:
        raise RuntimeAssuranceRestoreDomainError("Restore requires a recorded remediation plan")
    if context.remediation_due_at is None:
        raise RuntimeAssuranceRestoreDomainError("Restore requires a recorded remediation due date")
    _require_aware(context.remediation_due_at, "Remediation due timestamp")
    if context.incident_status is IncidentStatus.CLOSED:
        if context.resolved_at is None:
            raise RuntimeAssuranceRestoreDomainError(
                "Closed incident is missing its resolution timestamp"
            )
        _require_aware(context.resolved_at, "Incident resolution timestamp")
    elif context.resolved_at is not None:
        _require_aware(context.resolved_at, "Incident resolution timestamp")


def _require_schema_version(schema_version: str, version: int) -> None:
    if schema_version != RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION or version != 1:
        raise RuntimeAssuranceRestoreDomainError("Unsupported restore evidence version")


def _require_identity(value: str, label: str) -> None:
    if not value.strip():
        raise RuntimeAssuranceRestoreDomainError(f"{label} must not be empty")


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeAssuranceRestoreDomainError(f"{label} must be timezone-aware")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    _require_aware(value, "Canonical timestamp")
    return value.astimezone(UTC).isoformat()


def _sha(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
