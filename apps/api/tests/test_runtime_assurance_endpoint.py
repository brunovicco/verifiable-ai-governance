from datetime import UTC, datetime

from ai_governance_api.dependencies import get_runtime_assurance_service
from ai_governance_api.domain.runtime_assurance import RuntimeAssurancePolicy
from ai_governance_api.main import app
from governance_schemas import RiskTier
from httpx import AsyncClient

AGENT_ID = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 8, 9, 18, 0, tzinfo=UTC)


class PolicyService:
    async def put_policy(self, **kwargs):
        return RuntimeAssurancePolicy(
            agent_id=kwargs["agent_id"],
            ai_system_id="system-1",
            enabled=kwargs["enabled"],
            lookback_seconds=kwargs["lookback_seconds"],
            evaluation_sample_size=kwargs["evaluation_sample_size"],
            minimum_samples=kwargs["minimum_samples"],
            max_failure_rate=kwargs["max_failure_rate"],
            max_p95_duration_ms=kwargs["max_p95_duration_ms"],
            max_consecutive_failures=kwargs["max_consecutive_failures"],
            breach_severity=kwargs["breach_severity"],
            version=1,
            created_at=NOW,
            updated_at=NOW,
        )


def payload() -> dict[str, object]:
    return {
        "enabled": True,
        "lookback_seconds": 300,
        "evaluation_sample_size": 20,
        "minimum_samples": 5,
        "max_failure_rate": 0.1,
        "max_p95_duration_ms": 500,
        "max_consecutive_failures": 3,
        "breach_severity": "high",
        "expected_version": None,
    }


async def test_policy_endpoint_exposes_closed_contract(client: AsyncClient) -> None:
    app.dependency_overrides[get_runtime_assurance_service] = lambda: PolicyService()
    try:
        response = await client.put(
            f"/api/v1/agents/{AGENT_ID}/runtime-assurance-policy",
            json=payload(),
            headers={"X-User-Id": "agent-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_service, None)
    assert response.status_code == 200
    document = response.json()
    assert document["agent_id"] == AGENT_ID
    assert document["breach_severity"] == RiskTier.HIGH.value
    assert document["version"] == 1


async def test_policy_endpoint_rejects_incoherent_sample_bounds(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_runtime_assurance_service] = lambda: PolicyService()
    invalid = payload()
    invalid["minimum_samples"] = 21
    try:
        response = await client.put(
            f"/api/v1/agents/{AGENT_ID}/runtime-assurance-policy",
            json=invalid,
            headers={"X-User-Id": "agent-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_service, None)
    assert response.status_code == 422


async def test_policy_endpoint_forbids_arbitrary_fields(client: AsyncClient) -> None:
    app.dependency_overrides[get_runtime_assurance_service] = lambda: PolicyService()
    invalid = payload()
    invalid["auto_engage_kill_switch"] = True
    try:
        response = await client.put(
            f"/api/v1/agents/{AGENT_ID}/runtime-assurance-policy",
            json=invalid,
            headers={"X-User-Id": "agent-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_service, None)
    assert response.status_code == 422
