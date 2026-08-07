"""P1.4 tests for binding trusted Router violation evidence to the sent request."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from ai_governance_api.adapters.policy_model_router import _require_violation_binding
from ai_governance_api.application.model_routing import ModelRouterUnavailable
from ai_governance_api.domain.model_routing import PolicyModelRouterRequest, RoutingWorkload
from governance_schemas import (
    DataClassification,
    RiskTier,
    RuntimeViolationAuthorizationContext,
    RuntimeViolationAuthorizationState,
    RuntimeViolationCategory,
    RuntimeViolationEnvelope,
    RuntimeViolationEvent,
    RuntimeViolationRequestContext,
    SignedRuntimeAuthorization,
)


def _authorization() -> SignedRuntimeAuthorization:
    path = (
        Path(__file__).resolve().parents[3]
        / "contracts/runtime-authorization/examples/credit-pj-v1.json"
    )
    return SignedRuntimeAuthorization.model_validate_json(path.read_text(encoding="utf-8"))


def _request() -> PolicyModelRouterRequest:
    authorization = _authorization()
    return PolicyModelRouterRequest(
        schema_version="1.0",
        requested_at=authorization.claims.issued_at,
        workflow_id=authorization.claims.request.workflow_id,
        task_id=authorization.claims.request.task_id,
        agent_name="Agente de Parecer de Crédito PJ",
        workload=RoutingWorkload.OPINION_DRAFTING,
        risk_level=RiskTier.HIGH,
        data_classification=DataClassification.RESTRICTED,
        context_tokens_estimated=authorization.claims.request.context_tokens_estimated,
        max_output_tokens_estimated=(authorization.claims.request.max_output_tokens_estimated),
        structured_output_required=(authorization.claims.request.structured_output_required),
        max_latency_ms=authorization.claims.request.max_latency_ms,
        max_cost_usd=Decimal("0.30"),
        runtime_authorization=authorization,
    )


def _violation(correlation_id: str) -> RuntimeViolationEnvelope:
    request = _request()
    authorization = request.runtime_authorization
    assert authorization is not None
    event = RuntimeViolationEvent(
        event_id="66666666-6666-4666-8666-666666666666",
        occurred_at=datetime(2026, 8, 7, 20, 30, tzinfo=UTC),
        service_version="0.4.0",
        environment="production",
        correlation_id=correlation_id,
        category=RuntimeViolationCategory.MODEL_SCOPE,
        code="selected_model_group_not_authorized",
        request=RuntimeViolationRequestContext(
            workflow_id=request.workflow_id,
            task_id=request.task_id,
            agent_name=request.agent_name,
            workload=request.workload.value,
        ),
        authorization=RuntimeViolationAuthorizationContext(
            state=RuntimeViolationAuthorizationState.VERIFIED,
            authorization_id=authorization.claims.authorization_id,
            key_id=authorization.protected.kid,
            signing_digest=authorization.signing_digest(),
            scope_digest=authorization.claims.scope_digest,
        ),
        selected_model_group="reasoning-medium",
    )
    return RuntimeViolationEnvelope.from_event(event)


def test_matching_violation_is_accepted() -> None:
    request = _request()
    correlation_id = "route-123"

    _require_violation_binding(request, correlation_id, _violation(correlation_id))


def test_mismatched_correlation_is_untrusted() -> None:
    with pytest.raises(ModelRouterUnavailable):
        _require_violation_binding(_request(), "route-123", _violation("route-other"))
