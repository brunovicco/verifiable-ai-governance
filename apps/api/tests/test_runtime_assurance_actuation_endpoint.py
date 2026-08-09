from datetime import UTC, datetime

from ai_governance_api.dependencies import get_runtime_assurance_actuation_request_service
from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationRequestState,
    build_actuation_request_digest,
)
from ai_governance_api.main import app
from httpx import AsyncClient

NOW = datetime(2026, 8, 9, 21, 0, tzinfo=UTC)


def actuation_request(recommendation_id: str) -> RuntimeAssuranceActuationRequest:
    action = RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH
    state = RuntimeAssuranceActuationRequestState.PENDING
    digest = build_actuation_request_digest(
        request_id="request-1",
        recommendation_id=recommendation_id,
        recommendation_digest="a" * 64,
        promotion_id="promotion-1",
        evaluation_id="evaluation-1",
        incident_id="incident-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        action=action,
        state=state,
        requested_by="system-owner",
        requested_at=NOW,
    )
    return RuntimeAssuranceActuationRequest(
        id="request-1",
        schema_version="1.0",
        recommendation_id=recommendation_id,
        recommendation_digest="a" * 64,
        promotion_id="promotion-1",
        evaluation_id="evaluation-1",
        incident_id="incident-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        action=action,
        state=state,
        requested_by="system-owner",
        requested_at=NOW,
        request_digest=digest,
    )


class ActuationService:
    async def create(self, **kwargs):
        return actuation_request(kwargs["recommendation_id"])

    async def get(self, **kwargs):
        return actuation_request(kwargs["recommendation_id"])


async def test_actuation_request_endpoint_creates_pending_intent_only(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_runtime_assurance_actuation_request_service] = lambda: (
        ActuationService()
    )
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-response-recommendations/recommendation-1/actuation-request",
            json={},
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_actuation_request_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation_id"] == "recommendation-1"
    assert payload["action"] == "engage_kill_switch"
    assert payload["state"] == "pending"
    assert "kill_switch_engaged" not in payload
    assert "transition_id" not in payload


async def test_actuation_request_endpoint_rejects_arbitrary_actuator_fields(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_runtime_assurance_actuation_request_service] = lambda: (
        ActuationService()
    )
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-response-recommendations/recommendation-1/actuation-request",
            json={"force": True},
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_actuation_request_service, None)

    assert response.status_code == 422


async def test_actuation_request_endpoint_rejects_client_selected_action(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_runtime_assurance_actuation_request_service] = lambda: (
        ActuationService()
    )
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-response-recommendations/recommendation-1/actuation-request",
            json={"action": "engage_kill_switch"},
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_actuation_request_service, None)

    assert response.status_code == 422
