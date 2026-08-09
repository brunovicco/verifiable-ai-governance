from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationRequestState,
    RuntimeAssuranceActuationSourceContext,
)
from ai_governance_api.domain.runtime_assurance_actuation_decisions import (
    RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA,
    RUNTIME_ASSURANCE_ACTUATION_DECISION_SCHEMA_VERSION,
    RuntimeAssuranceActuationDecision,
    RuntimeAssuranceActuationDecisionContext,
    RuntimeAssuranceActuationDecisionDomainError,
    RuntimeAssuranceActuationDecisionOutcome,
    build_actuation_decision_digest,
    normalize_actuation_decision_reason,
    validate_actuation_decision_binding,
)
from ai_governance_api.domain.runtime_assurance_responses import RuntimeAssuranceResponseAction
from governance_schemas import ApprovalArea

NOW = datetime(2026, 8, 9, 21, 0, tzinfo=UTC)


def _context() -> RuntimeAssuranceActuationDecisionContext:
    request = RuntimeAssuranceActuationRequest(
        id="request-1",
        schema_version="1.0",
        recommendation_id="recommendation-1",
        recommendation_digest="a" * 64,
        promotion_id="promotion-1",
        evaluation_id="evaluation-1",
        incident_id="incident-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        action=RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH,
        state=RuntimeAssuranceActuationRequestState.PENDING,
        requested_by="requester-1",
        requested_at=NOW,
        request_digest="b" * 64,
    )
    source = RuntimeAssuranceActuationSourceContext(
        recommendation_id=request.recommendation_id,
        recommendation_digest=request.recommendation_digest,
        promotion_id=request.promotion_id,
        evaluation_id=request.evaluation_id,
        incident_id=request.incident_id,
        agent_id=request.agent_id,
        ai_system_id=request.ai_system_id,
        ai_system_owner_id="owner-1",
        advisory_only=True,
        recommendation_actions=(RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH,),
        current_incident_status=IncidentStatus.OPEN,
    )
    return RuntimeAssuranceActuationDecisionContext(request=request, source=source)


def _decision(
    context: RuntimeAssuranceActuationDecisionContext,
) -> RuntimeAssuranceActuationDecision:
    request = context.request
    digest = build_actuation_decision_digest(
        decision_id="decision-1",
        request_id=request.id,
        request_digest=request.request_digest,
        action=request.action,
        decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
        approval_area=RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA,
        decided_by="security-approver",
        decided_at=NOW,
        reason="Validated containment evidence.",
    )
    return RuntimeAssuranceActuationDecision(
        id="decision-1",
        schema_version=RUNTIME_ASSURANCE_ACTUATION_DECISION_SCHEMA_VERSION,
        request_id=request.id,
        request_digest=request.request_digest,
        action=request.action,
        decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
        approval_area=RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA,
        decided_by="security-approver",
        decided_at=NOW,
        reason="Validated containment evidence.",
        decision_digest=digest,
    )


def test_decision_digest_is_canonical_and_deterministic() -> None:
    context = _context()
    decision = _decision(context)
    repeated = build_actuation_decision_digest(
        decision_id=decision.id,
        request_id=decision.request_id,
        request_digest=decision.request_digest,
        action=decision.action,
        decision=decision.decision,
        approval_area=decision.approval_area,
        decided_by=decision.decided_by,
        decided_at=decision.decided_at,
        reason=decision.reason,
    )
    assert repeated == decision.decision_digest
    assert len(repeated) == 64


def test_decision_digest_binds_reason_and_request_digest() -> None:
    context = _context()
    decision = _decision(context)
    changed_reason = build_actuation_decision_digest(
        decision_id=decision.id,
        request_id=decision.request_id,
        request_digest=decision.request_digest,
        action=decision.action,
        decision=decision.decision,
        approval_area=decision.approval_area,
        decided_by=decision.decided_by,
        decided_at=decision.decided_at,
        reason="Different reason.",
    )
    changed_request = build_actuation_decision_digest(
        decision_id=decision.id,
        request_id=decision.request_id,
        request_digest="c" * 64,
        action=decision.action,
        decision=decision.decision,
        approval_area=decision.approval_area,
        decided_by=decision.decided_by,
        decided_at=decision.decided_at,
        reason=decision.reason,
    )
    assert changed_reason != decision.decision_digest
    assert changed_request != decision.decision_digest


def test_validate_decision_binding_rejects_cross_request_reuse() -> None:
    context = _context()
    decision = _decision(context)
    wrong_context = RuntimeAssuranceActuationDecisionContext(
        request=replace(context.request, id="request-2"),
        source=context.source,
    )
    with pytest.raises(RuntimeAssuranceActuationDecisionDomainError):
        validate_actuation_decision_binding(decision, wrong_context)


def test_validate_decision_binding_rejects_tampered_digest() -> None:
    context = _context()
    decision = _decision(context)
    tampered = RuntimeAssuranceActuationDecision(
        id=decision.id,
        schema_version=decision.schema_version,
        request_id=decision.request_id,
        request_digest=decision.request_digest,
        action=decision.action,
        decision=decision.decision,
        approval_area=decision.approval_area,
        decided_by=decision.decided_by,
        decided_at=decision.decided_at,
        reason=decision.reason,
        decision_digest="0" * 64,
    )
    with pytest.raises(RuntimeAssuranceActuationDecisionDomainError):
        validate_actuation_decision_binding(tampered, context)


def test_decision_reason_is_canonical_and_bounded() -> None:
    assert normalize_actuation_decision_reason("  valid reason  ") == "valid reason"
    with pytest.raises(RuntimeAssuranceActuationDecisionDomainError):
        normalize_actuation_decision_reason("   ")


def test_decision_approval_area_is_security() -> None:
    assert RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA is ApprovalArea.SECURITY
