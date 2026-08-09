"""Pure governed-actuation execution receipts and canonical evidence rules."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from governance_schemas import ApprovalArea

from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationSourceContext,
)
from ai_governance_api.domain.runtime_assurance_actuation_decisions import (
    RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA,
    RuntimeAssuranceActuationDecision,
    RuntimeAssuranceActuationDecisionOutcome,
)
from ai_governance_api.domain.runtime_control import (
    RuntimeControlState,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
)

RUNTIME_ASSURANCE_ACTUATION_EXECUTION_SCHEMA_VERSION = "1.0"
RUNTIME_ASSURANCE_ACTUATION_EVIDENCE_PREFIX = "runtime-assurance-actuation-decision"
RUNTIME_ASSURANCE_ACTUATION_RUNTIME_REASON = "Governed Runtime Assurance actuation execution"


class RuntimeAssuranceActuationExecutionDomainError(ValueError):
    """Raised when governed execution evidence or preconditions are invalid."""


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceActuationExecutionContext:
    """Trusted approval lineage plus a fresh runtime-control preflight snapshot."""

    decision: RuntimeAssuranceActuationDecision
    request: RuntimeAssuranceActuationRequest
    source: RuntimeAssuranceActuationSourceContext
    agent_version: int
    kill_switch_enabled: bool
    kill_switch_engaged: bool
    incident_status: IncidentStatus
    matching_transition: RuntimeControlTransitionRecord | None


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceActuationExecution:
    """Immutable receipt proving one approved governed action was applied."""

    id: str
    schema_version: str
    decision_id: str
    decision_digest: str
    request_id: str
    request_digest: str
    action: RuntimeAssuranceActuationAction
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


def runtime_actuation_decision_evidence_reference(
    decision: RuntimeAssuranceActuationDecision,
) -> str:
    """Return the bounded Runtime Control evidence key for one approved decision."""
    if not decision.id.strip() or not _is_sha256(decision.decision_digest):
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Actuation decision identity or digest is invalid"
        )
    if decision.action is not RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH:
        raise RuntimeAssuranceActuationExecutionDomainError("Unsupported governed action")
    if decision.decision is not RuntimeAssuranceActuationDecisionOutcome.APPROVED:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Only approved actuation decisions can be executed"
        )
    if decision.approval_area is not RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Actuation decision approval area is invalid"
        )
    return f"{RUNTIME_ASSURANCE_ACTUATION_EVIDENCE_PREFIX}:{decision.id}:{decision.decision_digest}"


def validate_new_execution_preconditions(
    context: RuntimeAssuranceActuationExecutionContext,
) -> None:
    """Require fresh conditions for creating a new Runtime Control transition."""
    decision = context.decision
    request = context.request
    if decision.decision is not RuntimeAssuranceActuationDecisionOutcome.APPROVED:
        raise RuntimeAssuranceActuationExecutionDomainError("Actuation decision is not approved")
    if (
        request.action is not RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH
        or decision.action is not request.action
        or decision.approval_area is not ApprovalArea.SECURITY
    ):
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Governed actuation action or approval binding is invalid"
        )
    if context.matching_transition is not None:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "A Runtime Control transition already exists for this decision"
        )
    if context.incident_status is IncidentStatus.CLOSED:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Cannot execute runtime actuation for a closed incident"
        )
    if not context.kill_switch_enabled:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Agent does not declare an available kill switch"
        )
    if context.kill_switch_engaged:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Kill switch is already engaged by another command"
        )
    if context.agent_version <= 0:
        raise RuntimeAssuranceActuationExecutionDomainError("Agent version is invalid")


def validate_runtime_transition_binding(
    context: RuntimeAssuranceActuationExecutionContext,
    transition: RuntimeControlTransitionRecord,
) -> None:
    """Reject a Runtime Control transition that is not bound to this approval chain."""
    reference = runtime_actuation_decision_evidence_reference(context.decision)
    request = context.request
    if (
        transition.agent_id != request.agent_id
        or transition.ai_system_id != request.ai_system_id
        or transition.incident_id != request.incident_id
        or transition.evidence_reference != reference
        or transition.previous_state is not RuntimeControlState.INACTIVE
        or transition.target_state is not RuntimeControlState.ACTIVE
        or transition.control_epoch <= 0
        or transition.revoked_through_agent_version <= 0
        or not transition.requested_by.strip()
    ):
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Runtime Control transition binding is inconsistent"
        )
    if transition.status is RuntimeControlTransitionStatus.APPLIED:
        if transition.applied_at is None:
            raise RuntimeAssuranceActuationExecutionDomainError(
                "Applied Runtime Control transition is missing its timestamp"
            )
        _require_aware(transition.applied_at, "Runtime Control applied timestamp")


def build_actuation_execution_receipt(
    *,
    execution_id: str,
    context: RuntimeAssuranceActuationExecutionContext,
    transition: RuntimeControlTransitionRecord,
) -> RuntimeAssuranceActuationExecution:
    """Build immutable applied execution evidence from a trusted Runtime Control transition."""
    validate_runtime_transition_binding(context, transition)
    if transition.status is not RuntimeControlTransitionStatus.APPLIED:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Runtime Control transition has not been applied"
        )
    applied_at = transition.applied_at
    if applied_at is None:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Applied Runtime Control transition is missing its timestamp"
        )
    resulting_agent_version = transition.revoked_through_agent_version + 1
    digest = build_actuation_execution_digest(
        execution_id=execution_id,
        decision_id=context.decision.id,
        decision_digest=context.decision.decision_digest,
        request_id=context.request.id,
        request_digest=context.request.request_digest,
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
    return RuntimeAssuranceActuationExecution(
        id=execution_id,
        schema_version=RUNTIME_ASSURANCE_ACTUATION_EXECUTION_SCHEMA_VERSION,
        decision_id=context.decision.id,
        decision_digest=context.decision.decision_digest,
        request_id=context.request.id,
        request_digest=context.request.request_digest,
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


def build_actuation_execution_digest(
    *,
    execution_id: str,
    decision_id: str,
    decision_digest: str,
    request_id: str,
    request_digest: str,
    action: RuntimeAssuranceActuationAction,
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
    schema_version: str = RUNTIME_ASSURANCE_ACTUATION_EXECUTION_SCHEMA_VERSION,
    version: int = 1,
) -> str:
    """Return canonical SHA-256 over the complete immutable execution receipt."""
    if schema_version != RUNTIME_ASSURANCE_ACTUATION_EXECUTION_SCHEMA_VERSION:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Unsupported actuation execution schema version"
        )
    if version != 1:
        raise RuntimeAssuranceActuationExecutionDomainError("Unsupported execution version")
    if not _is_sha256(decision_digest) or not _is_sha256(request_digest):
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Actuation decision or request digest is invalid"
        )
    if action is not RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH:
        raise RuntimeAssuranceActuationExecutionDomainError("Unsupported execution action")
    if previous_state is not RuntimeControlState.INACTIVE:
        raise RuntimeAssuranceActuationExecutionDomainError("Execution previous state is invalid")
    if target_state is not RuntimeControlState.ACTIVE:
        raise RuntimeAssuranceActuationExecutionDomainError("Execution target state is invalid")
    if control_epoch <= 0 or revoked_through_agent_version <= 0:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Runtime Control execution counters are invalid"
        )
    if resulting_agent_version != revoked_through_agent_version + 1:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Resulting Agent version does not match Runtime Control evidence"
        )
    if not executed_by.strip():
        raise RuntimeAssuranceActuationExecutionDomainError("Execution actor is invalid")
    _require_aware(executed_at, "Execution timestamp")

    canonical: Mapping[str, object] = {
        "schema_version": schema_version,
        "execution_id": execution_id,
        "decision_id": decision_id,
        "decision_digest": decision_digest,
        "request_id": request_id,
        "request_digest": request_digest,
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
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_actuation_execution_binding(
    execution: RuntimeAssuranceActuationExecution,
    context: RuntimeAssuranceActuationExecutionContext,
) -> None:
    """Reject cross-decision reuse, transition substitution, or receipt tampering."""
    transition = context.matching_transition
    if transition is None:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Runtime Control transition for execution evidence is missing"
        )
    validate_runtime_transition_binding(context, transition)
    if transition.status is not RuntimeControlTransitionStatus.APPLIED:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Execution evidence references a non-applied Runtime Control transition"
        )
    applied_at = transition.applied_at
    if applied_at is None:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Applied Runtime Control transition is missing its timestamp"
        )
    expected = {
        "decision_id": context.decision.id,
        "decision_digest": context.decision.decision_digest,
        "request_id": context.request.id,
        "request_digest": context.request.request_digest,
        "action": context.request.action,
        "agent_id": context.request.agent_id,
        "ai_system_id": context.request.ai_system_id,
        "incident_id": context.request.incident_id,
        "runtime_transition_id": transition.id,
        "control_epoch": transition.control_epoch,
        "previous_state": transition.previous_state,
        "target_state": transition.target_state,
        "revoked_through_agent_version": transition.revoked_through_agent_version,
        "resulting_agent_version": transition.revoked_through_agent_version + 1,
        "executed_by": transition.requested_by,
        "executed_at": applied_at,
    }
    observed = {
        "decision_id": execution.decision_id,
        "decision_digest": execution.decision_digest,
        "request_id": execution.request_id,
        "request_digest": execution.request_digest,
        "action": execution.action,
        "agent_id": execution.agent_id,
        "ai_system_id": execution.ai_system_id,
        "incident_id": execution.incident_id,
        "runtime_transition_id": execution.runtime_transition_id,
        "control_epoch": execution.control_epoch,
        "previous_state": execution.previous_state,
        "target_state": execution.target_state,
        "revoked_through_agent_version": execution.revoked_through_agent_version,
        "resulting_agent_version": execution.resulting_agent_version,
        "executed_by": execution.executed_by,
        "executed_at": execution.executed_at,
    }
    if observed != expected:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Runtime Assurance actuation execution binding is inconsistent"
        )
    expected_digest = build_actuation_execution_digest(
        execution_id=execution.id,
        decision_id=execution.decision_id,
        decision_digest=execution.decision_digest,
        request_id=execution.request_id,
        request_digest=execution.request_digest,
        action=execution.action,
        agent_id=execution.agent_id,
        ai_system_id=execution.ai_system_id,
        incident_id=execution.incident_id,
        runtime_transition_id=execution.runtime_transition_id,
        control_epoch=execution.control_epoch,
        previous_state=execution.previous_state,
        target_state=execution.target_state,
        revoked_through_agent_version=execution.revoked_through_agent_version,
        resulting_agent_version=execution.resulting_agent_version,
        executed_by=execution.executed_by,
        executed_at=execution.executed_at,
        schema_version=execution.schema_version,
        version=execution.version,
    )
    if execution.execution_digest != expected_digest:
        raise RuntimeAssuranceActuationExecutionDomainError(
            "Runtime Assurance actuation execution digest is inconsistent"
        )


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeAssuranceActuationExecutionDomainError(f"{label} must be timezone-aware")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
