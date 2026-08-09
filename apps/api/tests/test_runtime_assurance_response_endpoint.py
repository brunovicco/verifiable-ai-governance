from datetime import UTC, datetime

from ai_governance_api.dependencies import get_runtime_assurance_response_service
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_responses import (
    RuntimeAssuranceResponseAction,
    RuntimeAssuranceResponseRationale,
    RuntimeAssuranceResponseRecommendation,
)
from ai_governance_api.main import app
from governance_schemas import RiskTier
from httpx import AsyncClient

NOW = datetime(2026, 8, 9, 19, 45, tzinfo=UTC)


class ResponseService:
    async def generate(self, **kwargs):
        return recommendation(kwargs["promotion_id"])

    async def get(self, **kwargs):
        return recommendation(kwargs["promotion_id"])


def recommendation(promotion_id: str) -> RuntimeAssuranceResponseRecommendation:
    return RuntimeAssuranceResponseRecommendation(
        id="recommendation-1",
        promotion_id=promotion_id,
        evaluation_id="evaluation-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        incident_id="incident-1",
        breach_fingerprint="b" * 64,
        source_evidence_digest="e" * 64,
        policy_id="runtime-assurance-response",
        policy_version="1.0",
        policy_digest="p" * 64,
        incident_status=IncidentStatus.OPEN,
        incident_severity=RiskTier.CRITICAL,
        incident_version=3,
        kill_switch_enabled=True,
        kill_switch_engaged=False,
        actions=(
            RuntimeAssuranceResponseAction.INVESTIGATE_FAILURES,
            RuntimeAssuranceResponseAction.PREPARE_CONTAINMENT,
            RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH,
        ),
        rationale_codes=(
            RuntimeAssuranceResponseRationale.FAILURE_RATE_EXCEEDED,
            RuntimeAssuranceResponseRationale.ELEVATED_SEVERITY,
            RuntimeAssuranceResponseRationale.CRITICAL_KILL_SWITCH_AVAILABLE,
        ),
        advisory_only=True,
        generated_by="system-owner",
        generated_at=NOW,
        recommendation_digest="r" * 64,
    )


async def test_response_recommendation_endpoint_returns_advisory_evidence(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_runtime_assurance_response_service] = lambda: ResponseService()
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-incident-promotions/promotion-1/response-recommendations",
            json={},
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_response_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["promotion_id"] == "promotion-1"
    assert payload["advisory_only"] is True
    assert payload["actions"][-1] == "consider_kill_switch"
    assert "execute" not in payload


async def test_response_recommendation_endpoint_rejects_actuator_fields(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_runtime_assurance_response_service] = lambda: ResponseService()
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-incident-promotions/promotion-1/response-recommendations",
            json={"engage_kill_switch": True},
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_response_service, None)

    assert response.status_code == 422
