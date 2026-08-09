from datetime import UTC, datetime

from ai_governance_api.dependencies import (
    get_runtime_assurance_incident_promotion_service,
)
from ai_governance_api.domain.incidents import IncidentRecord, IncidentStatus
from ai_governance_api.domain.runtime_assurance_incidents import (
    RuntimeAssuranceIncidentDisposition,
    RuntimeAssuranceIncidentPromotion,
    RuntimeAssuranceIncidentPromotionResult,
)
from ai_governance_api.main import app
from governance_schemas import RiskTier
from httpx import AsyncClient

NOW = datetime(2026, 8, 9, 18, 30, tzinfo=UTC)


class PromotionService:
    async def promote(self, **kwargs):
        return result(kwargs["evaluation_id"])

    async def get_promotion(self, **kwargs):
        return result(kwargs["evaluation_id"])


def result(evaluation_id: str) -> RuntimeAssuranceIncidentPromotionResult:
    promotion = RuntimeAssuranceIncidentPromotion(
        id="promotion-1",
        evaluation_id=evaluation_id,
        agent_id="agent-1",
        ai_system_id="system-1",
        incident_id="incident-1",
        breach_fingerprint="b" * 64,
        disposition=RuntimeAssuranceIncidentDisposition.CREATED,
        promoted_by="system-owner",
        promoted_at=NOW,
        evidence_digest="a" * 64,
    )
    incident = IncidentRecord(
        id="incident-1",
        ai_system_id="system-1",
        title="Runtime assurance breach",
        severity=RiskTier.HIGH,
        status=IncidentStatus.OPEN,
        description="structural",
        detected_at=NOW,
        owner_id="system-owner",
        containment=None,
        remediation_owner_id=None,
        remediation_description=None,
        remediation_due_at=None,
        resolved_at=None,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    return RuntimeAssuranceIncidentPromotionResult(
        promotion=promotion,
        incident=incident,
    )


async def test_promote_endpoint_returns_minimized_linkage(client: AsyncClient) -> None:
    app.dependency_overrides[get_runtime_assurance_incident_promotion_service] = lambda: (
        PromotionService()
    )
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-evaluations/eval-1/incident-promotion",
            json={},
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(
            get_runtime_assurance_incident_promotion_service,
            None,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evaluation_id"] == "eval-1"
    assert payload["incident_id"] == "incident-1"
    assert payload["disposition"] == "created"
    assert payload["incident_status"] == "open"
    assert payload["incident_severity"] == "high"
    assert "description" not in payload


async def test_promote_endpoint_rejects_arbitrary_command_fields(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_runtime_assurance_incident_promotion_service] = lambda: (
        PromotionService()
    )
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-evaluations/eval-1/incident-promotion",
            json={"auto_engage_kill_switch": True},
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(
            get_runtime_assurance_incident_promotion_service,
            None,
        )

    assert response.status_code == 422
