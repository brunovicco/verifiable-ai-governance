from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import RuntimeAssuranceActuationAction
from ai_governance_api.domain.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecution,
)
from ai_governance_api.domain.runtime_assurance_restore import (
    RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION,
    RuntimeAssuranceRestoreAction,
    RuntimeAssuranceRestoreDecision,
    RuntimeAssuranceRestoreDecisionOutcome,
    RuntimeAssuranceRestoreDomainError,
    RuntimeAssuranceRestoreExecutionContext,
    RuntimeAssuranceRestoreRequest,
    RuntimeAssuranceRestoreRequestState,
    RuntimeAssuranceRestoreSourceContext,
    build_remediation_digest,
    build_restore_decision_digest,
    build_restore_execution_receipt,
    build_restore_request_digest,
    restore_decision_evidence_reference,
    validate_restore_request_current,
    validate_restore_source_eligibility,
)
from ai_governance_api.domain.runtime_control import (
    RuntimeControlState,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
)
from governance_schemas import ApprovalArea

NOW = datetime(2026, 8, 9, 22, 0, tzinfo=UTC)


def engage_execution() -> RuntimeAssuranceActuationExecution:
    return RuntimeAssuranceActuationExecution(
        id="engage-execution-1",
        schema_version="1.0",
        decision_id="engage-decision-1",
        decision_digest="a" * 64,
        request_id="engage-request-1",
        request_digest="b" * 64,
        action=RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH,
        agent_id="agent-1",
        ai_system_id="system-1",
        incident_id="incident-1",
        runtime_transition_id="engage-transition-1",
        control_epoch=4,
        previous_state=RuntimeControlState.INACTIVE,
        target_state=RuntimeControlState.ACTIVE,
        revoked_through_agent_version=7,
        resulting_agent_version=8,
        executed_by="system-owner",
        executed_at=NOW,
        execution_digest="c" * 64,
    )


def engage_transition() -> RuntimeControlTransitionRecord:
    return RuntimeControlTransitionRecord(
        id="engage-transition-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        control_epoch=4,
        previous_state=RuntimeControlState.INACTIVE,
        target_state=RuntimeControlState.ACTIVE,
        status=RuntimeControlTransitionStatus.APPLIED,
        revoked_through_agent_version=7,
        reason="Governed Runtime Assurance actuation execution",
        requested_by="system-owner",
        requested_at=NOW,
        applied_at=NOW,
        incident_id="incident-1",
        evidence_reference="runtime-assurance-actuation-decision:engage-decision-1:" + "a" * 64,
        version=2,
    )


def source_context() -> RuntimeAssuranceRestoreSourceContext:
    return RuntimeAssuranceRestoreSourceContext(
        source_execution=engage_execution(),
        ai_system_owner_id="system-owner",
        agent_version=8,
        kill_switch_enabled=True,
        kill_switch_engaged=True,
        incident_status=IncidentStatus.REMEDIATING,
        incident_version=3,
        remediation_owner_id="remediation-owner",
        remediation_description="Validated fix and regression checks.",
        remediation_due_at=NOW + timedelta(days=1),
        resolved_at=None,
        latest_transition=engage_transition(),
    )


def restore_request(source: RuntimeAssuranceRestoreSourceContext) -> RuntimeAssuranceRestoreRequest:
    remediation_digest = build_remediation_digest(source)
    digest = build_restore_request_digest(
        request_id="restore-request-1",
        source_execution_id=source.source_execution.id,
        source_execution_digest=source.source_execution.execution_digest,
        agent_id=source.source_execution.agent_id,
        ai_system_id=source.source_execution.ai_system_id,
        incident_id=source.source_execution.incident_id,
        action=RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH,
        state=RuntimeAssuranceRestoreRequestState.PENDING,
        remediation_digest=remediation_digest,
        incident_status=source.incident_status,
        incident_version=source.incident_version,
        requested_by="system-owner",
        requested_at=NOW,
    )
    return RuntimeAssuranceRestoreRequest(
        id="restore-request-1",
        schema_version=RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION,
        source_execution_id=source.source_execution.id,
        source_execution_digest=source.source_execution.execution_digest,
        agent_id=source.source_execution.agent_id,
        ai_system_id=source.source_execution.ai_system_id,
        incident_id=source.source_execution.incident_id,
        action=RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH,
        state=RuntimeAssuranceRestoreRequestState.PENDING,
        remediation_digest=remediation_digest,
        incident_status=source.incident_status,
        incident_version=source.incident_version,
        requested_by="system-owner",
        requested_at=NOW,
        request_digest=digest,
    )


def restore_decision(request: RuntimeAssuranceRestoreRequest) -> RuntimeAssuranceRestoreDecision:
    digest = build_restore_decision_digest(
        decision_id="restore-decision-1",
        request_id=request.id,
        request_digest=request.request_digest,
        source_execution_id=request.source_execution_id,
        source_execution_digest=request.source_execution_digest,
        action=request.action,
        decision=RuntimeAssuranceRestoreDecisionOutcome.APPROVED,
        approval_area=ApprovalArea.SECURITY,
        decided_by="security-approver",
        decided_at=NOW,
        reason="Recovery evidence reviewed.",
    )
    return RuntimeAssuranceRestoreDecision(
        id="restore-decision-1",
        schema_version=RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION,
        request_id=request.id,
        request_digest=request.request_digest,
        source_execution_id=request.source_execution_id,
        source_execution_digest=request.source_execution_digest,
        action=request.action,
        decision=RuntimeAssuranceRestoreDecisionOutcome.APPROVED,
        approval_area=ApprovalArea.SECURITY,
        decided_by="security-approver",
        decided_at=NOW,
        reason="Recovery evidence reviewed.",
        decision_digest=digest,
    )


def test_restore_source_requires_remediation_and_authoritative_engage_transition() -> None:
    validate_restore_source_eligibility(source_context())
    with pytest.raises(RuntimeAssuranceRestoreDomainError):
        validate_restore_source_eligibility(
            replace(source_context(), incident_status=IncidentStatus.CONTAINED)
        )
    with pytest.raises(RuntimeAssuranceRestoreDomainError):
        validate_restore_source_eligibility(
            replace(source_context(), remediation_description=None)
        )
    with pytest.raises(RuntimeAssuranceRestoreDomainError):
        validate_restore_source_eligibility(
            replace(source_context(), latest_transition=replace(engage_transition(), id="other"))
        )


def test_remediation_digest_is_deterministic_and_version_bound() -> None:
    source = source_context()
    assert build_remediation_digest(source) == build_remediation_digest(source)
    assert build_remediation_digest(source) != build_remediation_digest(
        replace(source, incident_version=source.incident_version + 1)
    )


def test_restore_request_becomes_stale_when_remediation_changes() -> None:
    source = source_context()
    request = restore_request(source)
    validate_restore_request_current(request, source)
    with pytest.raises(RuntimeAssuranceRestoreDomainError, match="stale"):
        validate_restore_request_current(
            request,
            replace(source, remediation_description="Updated remediation evidence."),
        )


def test_restore_decision_reference_is_distinct_from_engage_reference() -> None:
    decision = restore_decision(restore_request(source_context()))
    reference = restore_decision_evidence_reference(decision)
    assert reference.startswith("runtime-assurance-restore-decision:")
    assert "runtime-assurance-actuation-decision:" not in reference


def test_rejected_restore_decision_cannot_produce_runtime_reference() -> None:
    approved = restore_decision(restore_request(source_context()))
    rejected = replace(
        approved,
        decision=RuntimeAssuranceRestoreDecisionOutcome.REJECTED,
    )
    with pytest.raises(RuntimeAssuranceRestoreDomainError):
        restore_decision_evidence_reference(rejected)


def test_restore_execution_receipt_requires_active_to_inactive_transition() -> None:
    source = source_context()
    request = restore_request(source)
    decision = restore_decision(request)
    transition = RuntimeControlTransitionRecord(
        id="restore-transition-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        control_epoch=5,
        previous_state=RuntimeControlState.ACTIVE,
        target_state=RuntimeControlState.INACTIVE,
        status=RuntimeControlTransitionStatus.APPLIED,
        revoked_through_agent_version=8,
        reason="Governed Runtime Assurance kill-switch restore",
        requested_by="system-owner",
        requested_at=NOW,
        applied_at=NOW,
        incident_id="incident-1",
        evidence_reference=restore_decision_evidence_reference(decision),
        version=2,
    )
    context = RuntimeAssuranceRestoreExecutionContext(
        decision=decision,
        request=request,
        source=source,
        matching_transition=transition,
    )
    receipt = build_restore_execution_receipt(
        execution_id="restore-execution-1",
        context=context,
        transition=transition,
    )
    assert receipt.previous_state is RuntimeControlState.ACTIVE
    assert receipt.target_state is RuntimeControlState.INACTIVE
    assert receipt.resulting_agent_version == 9
    with pytest.raises(RuntimeAssuranceRestoreDomainError):
        build_restore_execution_receipt(
            execution_id="restore-execution-2",
            context=context,
            transition=replace(transition, target_state=RuntimeControlState.ACTIVE),
        )
