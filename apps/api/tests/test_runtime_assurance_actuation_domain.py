from datetime import UTC, datetime

import pytest
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationDomainError,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationRequestState,
    RuntimeAssuranceActuationSourceContext,
    build_actuation_request_digest,
    derive_actuation_action,
    validate_actuation_request_binding,
)
from ai_governance_api.domain.runtime_assurance_responses import RuntimeAssuranceResponseAction

NOW = datetime(2026, 8, 9, 20, 30, tzinfo=UTC)


def context(*, include_kill_switch: bool = True) -> RuntimeAssuranceActuationSourceContext:
    actions = (RuntimeAssuranceResponseAction.INVESTIGATE_FAILURES,)
    if include_kill_switch:
        actions += (RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH,)
    return RuntimeAssuranceActuationSourceContext(
        recommendation_id="recommendation-1",
        recommendation_digest="a" * 64,
        promotion_id="promotion-1",
        evaluation_id="evaluation-1",
        incident_id="incident-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        ai_system_owner_id="system-owner",
        advisory_only=True,
        recommendation_actions=actions,
        current_incident_status=IncidentStatus.OPEN,
    )


def request_for(source: RuntimeAssuranceActuationSourceContext) -> RuntimeAssuranceActuationRequest:
    action = RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH
    state = RuntimeAssuranceActuationRequestState.PENDING
    digest = build_actuation_request_digest(
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
        requested_at=NOW,
    )
    return RuntimeAssuranceActuationRequest(
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
        requested_at=NOW,
        request_digest=digest,
    )


def test_consider_kill_switch_maps_to_distinct_governed_action() -> None:
    action = derive_actuation_action(context())
    assert action is RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH
    assert action.value != RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH.value


def test_recommendation_without_consider_kill_switch_fails_closed() -> None:
    with pytest.raises(RuntimeAssuranceActuationDomainError, match="does not support"):
        derive_actuation_action(context(include_kill_switch=False))


def test_request_digest_is_canonical_and_deterministic() -> None:
    source = context()
    first = request_for(source)
    second = request_for(source)
    assert first.request_digest == second.request_digest
    assert len(first.request_digest) == 64


def test_request_binding_rejects_cross_agent_reuse() -> None:
    source = context()
    request = request_for(source)
    other = RuntimeAssuranceActuationSourceContext(
        recommendation_id=source.recommendation_id,
        recommendation_digest=source.recommendation_digest,
        promotion_id=source.promotion_id,
        evaluation_id=source.evaluation_id,
        incident_id=source.incident_id,
        agent_id="agent-2",
        ai_system_id=source.ai_system_id,
        ai_system_owner_id=source.ai_system_owner_id,
        advisory_only=source.advisory_only,
        recommendation_actions=source.recommendation_actions,
        current_incident_status=source.current_incident_status,
    )
    with pytest.raises(RuntimeAssuranceActuationDomainError, match="binding"):
        validate_actuation_request_binding(
            request,
            other,
            RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH,
        )


def test_duplicate_recommendation_actions_fail_closed() -> None:
    source = context()
    duplicate = RuntimeAssuranceActuationSourceContext(
        recommendation_id=source.recommendation_id,
        recommendation_digest=source.recommendation_digest,
        promotion_id=source.promotion_id,
        evaluation_id=source.evaluation_id,
        incident_id=source.incident_id,
        agent_id=source.agent_id,
        ai_system_id=source.ai_system_id,
        ai_system_owner_id=source.ai_system_owner_id,
        advisory_only=source.advisory_only,
        recommendation_actions=(
            RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH,
            RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH,
        ),
        current_incident_status=source.current_incident_status,
    )
    with pytest.raises(RuntimeAssuranceActuationDomainError, match="duplicate actions"):
        derive_actuation_action(duplicate)
