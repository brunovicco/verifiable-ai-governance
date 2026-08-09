from datetime import UTC, datetime

from ai_governance_api.dependencies import (
    get_authorized_principal,
    get_runtime_assurance_restore_decision_service,
    get_runtime_assurance_restore_execution_service,
    get_runtime_assurance_restore_request_service,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_restore import (
    RuntimeAssuranceRestoreAction,
    RuntimeAssuranceRestoreDecision,
    RuntimeAssuranceRestoreDecisionOutcome,
    RuntimeAssuranceRestoreExecution,
    RuntimeAssuranceRestoreRequest,
    RuntimeAssuranceRestoreRequestState,
)
from ai_governance_api.domain.runtime_control import RuntimeControlState
from ai_governance_api.main import app
from governance_schemas import ApprovalArea
from httpx import AsyncClient

NOW = datetime(2026, 8, 9, 23, 0, tzinfo=UTC)


async def authorized_principal() -> Principal:
    return Principal(
        user_id="system-owner",
        approval_areas=frozenset({ApprovalArea.SECURITY}),
    )


def restore_request() -> RuntimeAssuranceRestoreRequest:
    return RuntimeAssuranceRestoreRequest(
        id="restore-request-1",
        schema_version="1.0",
        source_execution_id="engage-execution-1",
        source_execution_digest="a" * 64,
        agent_id="agent-1",
        ai_system_id="system-1",
        incident_id="incident-1",
        action=RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH,
        state=RuntimeAssuranceRestoreRequestState.PENDING,
        remediation_digest="b" * 64,
        incident_status=IncidentStatus.REMEDIATING,
        incident_version=3,
        requested_by="system-owner",
        requested_at=NOW,
        request_digest="c" * 64,
    )


def restore_decision() -> RuntimeAssuranceRestoreDecision:
    return RuntimeAssuranceRestoreDecision(
        id="restore-decision-1",
        schema_version="1.0",
        request_id="restore-request-1",
        request_digest="c" * 64,
        source_execution_id="engage-execution-1",
        source_execution_digest="a" * 64,
        action=RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH,
        decision=RuntimeAssuranceRestoreDecisionOutcome.APPROVED,
        approval_area=ApprovalArea.SECURITY,
        decided_by="security-approver",
        decided_at=NOW,
        reason="Recovery evidence reviewed.",
        decision_digest="d" * 64,
    )


def restore_execution() -> RuntimeAssuranceRestoreExecution:
    return RuntimeAssuranceRestoreExecution(
        id="restore-execution-1",
        schema_version="1.0",
        decision_id="restore-decision-1",
        decision_digest="d" * 64,
        request_id="restore-request-1",
        request_digest="c" * 64,
        source_execution_id="engage-execution-1",
        source_execution_digest="a" * 64,
        action=RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH,
        agent_id="agent-1",
        ai_system_id="system-1",
        incident_id="incident-1",
        runtime_transition_id="restore-transition-1",
        control_epoch=5,
        previous_state=RuntimeControlState.ACTIVE,
        target_state=RuntimeControlState.INACTIVE,
        revoked_through_agent_version=8,
        resulting_agent_version=9,
        executed_by="system-owner",
        executed_at=NOW,
        execution_digest="e" * 64,
    )


class RequestService:
    async def create(self, **kwargs):
        return restore_request()

    async def get(self, **kwargs):
        return restore_request()


class DecisionService:
    async def decide(self, **kwargs):
        return restore_decision()

    async def get(self, **kwargs):
        return restore_decision()


class ExecutionService:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, **kwargs):
        self.calls += 1
        return restore_execution()

    async def get(self, **kwargs):
        return restore_execution()


async def test_restore_request_endpoint_accepts_empty_body_only(client: AsyncClient) -> None:
    app.dependency_overrides[get_authorized_principal] = authorized_principal
    app.dependency_overrides[get_runtime_assurance_restore_request_service] = (
        lambda: RequestService()
    )
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-actuation-executions/engage-execution-1/restore-request",
            json={},
            headers={"X-User-Id": "system-owner"},
        )
        forbidden = await client.post(
            "/api/v1/runtime-assurance-actuation-executions/engage-execution-1/restore-request",
            json={"force": True},
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_restore_request_service, None)
        app.dependency_overrides.pop(get_authorized_principal, None)
    assert response.status_code == 200
    assert response.json()["action"] == "restore_kill_switch"
    assert forbidden.status_code == 422


async def test_restore_decision_endpoint_rejects_client_selected_action(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_authorized_principal] = authorized_principal
    app.dependency_overrides[get_runtime_assurance_restore_decision_service] = (
        lambda: DecisionService()
    )
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-restore-requests/restore-request-1/decision",
            json={
                "decision": "approved",
                "reason": "Recovery evidence reviewed.",
                "action": "restore_kill_switch",
            },
            headers={"X-User-Id": "security-approver", "X-User-Areas": "security"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_restore_decision_service, None)
        app.dependency_overrides.pop(get_authorized_principal, None)
    assert response.status_code == 422


async def test_restore_execution_endpoint_executes_server_derived_restore_only(
    client: AsyncClient,
) -> None:
    service = ExecutionService()
    app.dependency_overrides[get_authorized_principal] = authorized_principal
    app.dependency_overrides[get_runtime_assurance_restore_execution_service] = lambda: service
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-restore-decisions/restore-decision-1/execution",
            json={},
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_restore_execution_service, None)
        app.dependency_overrides.pop(get_authorized_principal, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "restore_kill_switch"
    assert payload["previous_state"] == "active"
    assert payload["target_state"] == "inactive"
    assert service.calls == 1


async def test_restore_execution_endpoint_rejects_force_and_target_state(
    client: AsyncClient,
) -> None:
    service = ExecutionService()
    app.dependency_overrides[get_authorized_principal] = authorized_principal
    app.dependency_overrides[get_runtime_assurance_restore_execution_service] = lambda: service
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-restore-decisions/restore-decision-1/execution",
            json={"force": True, "target_state": "inactive"},
            headers={"X-User-Id": "system-owner"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_restore_execution_service, None)
        app.dependency_overrides.pop(get_authorized_principal, None)
    assert response.status_code == 422
    assert service.calls == 0
