from datetime import UTC, datetime

from ai_governance_api.dependencies import (
    get_authorized_principal,
    get_runtime_assurance_actuation_execution_service,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.runtime_assurance_actuation import RuntimeAssuranceActuationAction
from ai_governance_api.domain.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecution,
)
from ai_governance_api.domain.runtime_control import RuntimeControlState
from ai_governance_api.main import app
from httpx import AsyncClient

NOW = datetime(2026, 8, 9, 22, 30, tzinfo=UTC)


async def authorized_executor() -> Principal:
    return Principal(user_id="system-owner")


class ExecutionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs):
        self.calls.append(dict(kwargs))
        return execution_receipt()

    async def get(self, **kwargs):
        self.calls.append(dict(kwargs))
        return execution_receipt()


def execution_receipt() -> RuntimeAssuranceActuationExecution:
    return RuntimeAssuranceActuationExecution(
        id="execution-1",
        schema_version="1.0",
        decision_id="decision-1",
        decision_digest="c" * 64,
        request_id="request-1",
        request_digest="b" * 64,
        action=RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH,
        agent_id="agent-1",
        ai_system_id="system-1",
        incident_id="incident-1",
        runtime_transition_id="transition-1",
        control_epoch=3,
        previous_state=RuntimeControlState.INACTIVE,
        target_state=RuntimeControlState.ACTIVE,
        revoked_through_agent_version=7,
        resulting_agent_version=8,
        executed_by="system-owner",
        executed_at=NOW,
        execution_digest="d" * 64,
    )


async def test_execution_endpoint_applies_only_server_derived_approved_action(
    client: AsyncClient,
) -> None:
    service = ExecutionService()
    app.dependency_overrides[get_authorized_principal] = authorized_executor
    app.dependency_overrides[get_runtime_assurance_actuation_execution_service] = lambda: service
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-actuation-decisions/decision-1/execution",
            json={},
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_actuation_execution_service, None)
        app.dependency_overrides.pop(get_authorized_principal, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision_id"] == "decision-1"
    assert payload["action"] == "engage_kill_switch"
    assert payload["previous_state"] == "inactive"
    assert payload["target_state"] == "active"
    assert payload["runtime_transition_id"] == "transition-1"
    assert "decision_reason" not in payload
    assert "restore" not in payload
    assert len(service.calls) == 1


async def test_execution_endpoint_rejects_client_selected_actuator_fields(
    client: AsyncClient,
) -> None:
    service = ExecutionService()
    app.dependency_overrides[get_authorized_principal] = authorized_executor
    app.dependency_overrides[get_runtime_assurance_actuation_execution_service] = lambda: service
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-actuation-decisions/decision-1/execution",
            json={
                "action": "engage_kill_switch",
                "force": True,
                "expected_version": 7,
                "target_state": "active",
            },
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_actuation_execution_service, None)
        app.dependency_overrides.pop(get_authorized_principal, None)

    assert response.status_code == 422
    assert service.calls == []


async def test_execution_get_returns_immutable_receipt(client: AsyncClient) -> None:
    service = ExecutionService()
    app.dependency_overrides[get_authorized_principal] = authorized_executor
    app.dependency_overrides[get_runtime_assurance_actuation_execution_service] = lambda: service
    try:
        response = await client.get(
            "/api/v1/runtime-assurance-actuation-decisions/decision-1/execution",
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_actuation_execution_service, None)
        app.dependency_overrides.pop(get_authorized_principal, None)

    assert response.status_code == 200
    assert response.json()["execution_digest"] == "d" * 64
