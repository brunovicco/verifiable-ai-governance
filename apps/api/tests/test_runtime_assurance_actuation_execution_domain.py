from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationRequestState,
    RuntimeAssuranceActuationSourceContext,
    build_actuation_request_digest,
)
from ai_governance_api.domain.runtime_assurance_actuation_decisions import (
    RuntimeAssuranceActuationDecision,
    RuntimeAssuranceActuationDecisionOutcome,
    build_actuation_decision_digest,
)
from ai_governance_api.domain.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecutionContext,
    RuntimeAssuranceActuationExecutionDomainError,
    build_actuation_execution_receipt,
    runtime_actuation_decision_evidence_reference,
    validate_actuation_execution_binding,
    validate_new_execution_preconditions,
)
from ai_governance_api.domain.runtime_assurance_responses import RuntimeAssuranceResponseAction
from ai_governance_api.domain.runtime_control import (
    RuntimeControlState,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
)
from governance_schemas import ApprovalArea

REQUESTED_AT = datetime(2026, 8, 9, 20, 0, tzinfo=UTC)
DECIDED_AT = datetime(2026, 8, 9, 20, 5, tzinfo=UTC)
APPLIED_AT = datetime(2026, 8, 9, 20, 10, tzinfo=UTC)


def execution_context(
    *,
    outcome: RuntimeAssuranceActuationDecisionOutcome = (
        RuntimeAssuranceActuationDecisionOutcome.APPROVED
    ),
    incident_status: IncidentStatus = IncidentStatus.OPEN,
    engaged: bool = False,
    transition: RuntimeControlTransitionRecord | None = None,
) -> RuntimeAssuranceActuationExecutionContext:
    source = RuntimeAssuranceActuationSourceContext(
        recommendation_id="recommendation-1",
        recommendation_digest="a" * 64,
        promotion_id="promotion-1",
        evaluation_id="evaluation-1",
        incident_id="incident-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        ai_system_owner_id="system-owner",
        advisory_only=True,
        recommendation_actions=(RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH,),
        current_incident_status=incident_status,
    )
    action = RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH
    state = RuntimeAssuranceActuationRequestState.PENDING
    request_digest = build_actuation_request_digest(
        request_id="request-1",
        recommendation_id=source.recommendation_id,
        recommendation_digest=source.recommendation_digest,
        promotion_id=source.promotion_id,
        evaluation_id=source.evaluation_id,
        incident_id=source.incident_id,
        agent_id=source.agent_id,
        ai_system_id=source.ai_system_id,
        action=action,
        state=state,
        requested_by="system-owner",
        requested_at=REQUESTED_AT,
    )
    request = RuntimeAssuranceActuationRequest(
        id="request-1",
        schema_version="1.0",
        recommendation_id=source.recommendation_id,
        recommendation_digest=source.recommendation_digest,
        promotion_id=source.promotion_id,
        evaluation_id=source.evaluation_id,
        incident_id=source.incident_id,
        agent_id=source.agent_id,
        ai_system_id=source.ai_system_id,
        action=action,
        state=state,
        requested_by="system-owner",
        requested_at=REQUESTED_AT,
        request_digest=request_digest,
    )
    decision_digest = build_actuation_decision_digest(
        decision_id="decision-1",
        request_id=request.id,
        request_digest=request.request_digest,
        action=action,
        decision=outcome,
        approval_area=ApprovalArea.SECURITY,
        decided_by="security-approver",
        decided_at=DECIDED_AT,
        reason="Reviewed by Security.",
    )
    decision = RuntimeAssuranceActuationDecision(
        id="decision-1",
        schema_version="1.0",
        request_id=request.id,
        request_digest=request.request_digest,
        action=action,
        decision=outcome,
        approval_area=ApprovalArea.SECURITY,
        decided_by="security-approver",
        decided_at=DECIDED_AT,
        reason="Reviewed by Security.",
        decision_digest=decision_digest,
    )
    return RuntimeAssuranceActuationExecutionContext(
        decision=decision,
        request=request,
        source=source,
        agent_version=7,
        kill_switch_enabled=True,
        kill_switch_engaged=engaged,
        incident_status=incident_status,
        matching_transition=transition,
    )


def applied_transition(context: RuntimeAssuranceActuationExecutionContext):
    return RuntimeControlTransitionRecord(
        id="transition-1",
        agent_id=context.request.agent_id,
        ai_system_id=context.request.ai_system_id,
        control_epoch=3,
        previous_state=RuntimeControlState.INACTIVE,
        target_state=RuntimeControlState.ACTIVE,
        status=RuntimeControlTransitionStatus.APPLIED,
        revoked_through_agent_version=7,
        reason="Governed Runtime Assurance actuation execution",
        requested_by="system-owner",
        requested_at=APPLIED_AT,
        applied_at=APPLIED_AT,
        incident_id=context.request.incident_id,
        evidence_reference=runtime_actuation_decision_evidence_reference(context.decision),
        version=2,
    )


def test_execution_reference_is_bound_to_approved_decision_digest() -> None:
    context = execution_context()
    reference = runtime_actuation_decision_evidence_reference(context.decision)
    assert context.decision.id in reference
    assert context.decision.decision_digest in reference


def test_rejected_decision_cannot_produce_execution_reference() -> None:
    context = execution_context(outcome=RuntimeAssuranceActuationDecisionOutcome.REJECTED)
    with pytest.raises(RuntimeAssuranceActuationExecutionDomainError):
        runtime_actuation_decision_evidence_reference(context.decision)


def test_new_execution_preconditions_fail_for_closed_incident() -> None:
    context = execution_context(incident_status=IncidentStatus.CLOSED)
    with pytest.raises(RuntimeAssuranceActuationExecutionDomainError):
        validate_new_execution_preconditions(context)


def test_new_execution_preconditions_fail_when_switch_already_engaged() -> None:
    context = execution_context(engaged=True)
    with pytest.raises(RuntimeAssuranceActuationExecutionDomainError):
        validate_new_execution_preconditions(context)


def test_execution_receipt_is_deterministic_and_bound_to_transition() -> None:
    context = execution_context()
    transition = applied_transition(context)
    bound = replace(context, matching_transition=transition)
    first = build_actuation_execution_receipt(
        execution_id="execution-1",
        context=bound,
        transition=transition,
    )
    second = build_actuation_execution_receipt(
        execution_id="execution-1",
        context=bound,
        transition=transition,
    )
    assert first == second
    assert first.decision_digest == context.decision.decision_digest
    assert first.runtime_transition_id == transition.id
    assert first.resulting_agent_version == 8
    validate_actuation_execution_binding(first, bound)


def test_cross_transition_receipt_reuse_fails_closed() -> None:
    context = execution_context()
    transition = applied_transition(context)
    bound = replace(context, matching_transition=transition)
    receipt = build_actuation_execution_receipt(
        execution_id="execution-1",
        context=bound,
        transition=transition,
    )
    other = replace(transition, id="transition-other")
    with pytest.raises(RuntimeAssuranceActuationExecutionDomainError):
        validate_actuation_execution_binding(
            receipt,
            replace(bound, matching_transition=other),
        )
