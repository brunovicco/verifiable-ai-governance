import json

from ai_governance_api.config import Settings, get_settings
from ai_governance_api.dependencies import get_ingest_runtime_telemetry
from ai_governance_api.main import app
from httpx import AsyncClient

AGENT_A = "11111111-1111-4111-8111-111111111111"
AGENT_B = "22222222-2222-4222-8222-222222222222"


class MustNotIngest:
    """Fail the test if authentication lets an invalid request reach the use case."""

    async def execute(self, **_kwargs):
        raise AssertionError("ingestion use case must not be called")


def payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "source_schema_version": 1,
        "event_id": "33333333-3333-4333-8333-333333333333",
        "observed_at": "2026-08-08T22:00:00Z",
        "event_name": "a2a.client.send_message.completed",
        "event_outcome": "success",
        "service": "decisao-agent",
        "environment": "local",
        "version": "0.1.0",
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "operation": "send_message",
    }


async def test_ingestion_rejects_api_key_bound_to_different_agent(
    client: AsyncClient,
) -> None:
    settings = Settings(
        runtime_telemetry_ingest_enabled=True,
        runtime_telemetry_api_keys_json=json.dumps(
            {
                AGENT_A: "agent-a-secret",
                AGENT_B: "agent-b-secret",
            }
        ),
    )

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_ingest_runtime_telemetry] = lambda: MustNotIngest()

    try:
        response = await client.post(
            f"/api/v1/agents/{AGENT_A}/runtime-telemetry",
            json=payload(),
            headers={"X-Telemetry-Api-Key": "agent-b-secret"},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_ingest_runtime_telemetry, None)

    assert response.status_code == 403
    assert response.json() == {"detail": "Missing or invalid runtime telemetry credential"}


async def test_ingestion_rejects_missing_machine_credential(
    client: AsyncClient,
) -> None:
    settings = Settings(
        runtime_telemetry_ingest_enabled=True,
        runtime_telemetry_api_keys_json=json.dumps(
            {
                AGENT_A: "agent-a-secret",
            }
        ),
    )

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_ingest_runtime_telemetry] = lambda: MustNotIngest()

    try:
        response = await client.post(
            f"/api/v1/agents/{AGENT_A}/runtime-telemetry",
            json=payload(),
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_ingest_runtime_telemetry, None)

    assert response.status_code == 403
    assert response.json() == {"detail": "Missing or invalid runtime telemetry credential"}
