from datetime import UTC, datetime

from ai_governance_api.dependencies import (
    get_authorized_principal,
    get_runtime_assurance_actuation_decision_service,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.runtime_assurance_actuation import RuntimeAssuranceActuationAction
from ai_governance_api.domain.runtime_assurance_actuation_decisions import (
    RUNTIME_ASSURANCE_ACTUATION_DECISION_SCHEMA_VERSION,
    RuntimeAssuranceActuationDecision,
    RuntimeAssuranceActuationDecisionOutcome,
)
from ai_governance_api.main import app
from governance_schemas import ApprovalArea
from httpx import AsyncClient

NOW = datetime(2026, 8, 9, 21, 30, tzinfo=UTC)


async def authorized_security_principal() -> Principal:
    return Principal(
        user_id="security-approver",
        approval_areas=frozenset({ApprovalArea.SECURITY}),
    )


class DecisionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def decide(self, **kwargs):
        self.calls.append(dict(kwargs))
        return actuation_decision(
            decision=kwargs["decision"],
            reason=kwargs["reason"],
            decided_by=kwargs["principal"].user_id,
        )

    async def get(self, **kwargs):
        self.calls.append(dict(kwargs))
        return actuation_decision(
            decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
            reason="Approved by security review.",
            decided_by="security-approver",
        )


def actuation_decision(
    *,
    decision: RuntimeAssuranceActuationDecisionOutcome,
    reason: str,
    decided_by: str,
) -> RuntimeAssuranceActuationDecision:
    return RuntimeAssuranceActuationDecision(
        id="decision-1",
        schema_version=RUNTIME_ASSURANCE_ACTUATION_DECISION_SCHEMA_VERSION,
        request_id="request-1",
        request_digest="b" * 64,
        action=RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH,
        decision=decision,
        approval_area=ApprovalArea.SECURITY,
        decided_by=decided_by,
        decided_at=NOW,
        reason=reason,
        decision_digest="c" * 64,
    )


async def test_actuation_decision_endpoint_records_approval_evidence_only(
    client: AsyncClient,
) -> None:
    service = DecisionService()
    app.dependency_overrides[get_authorized_principal] = authorized_security_principal
    app.dependency_overrides[get_runtime_assurance_actuation_decision_service] = lambda: service
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-actuation-requests/request-1/decision",
            json={
                "decision": "approved",
                "reason": "Reviewed evidence and approved containment.",
            },
            headers={"X-User-Id": "security-approver", "X-User-Areas": "security"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_actuation_decision_service, None)
        app.dependency_overrides.pop(get_authorized_principal, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "request-1"
    assert payload["decision"] == "approved"
    assert payload["action"] == "engage_kill_switch"
    assert payload["approval_area"] == "security"
    assert "kill_switch_engaged" not in payload
    assert "transition_id" not in payload
    assert len(service.calls) == 1


async def test_actuation_decision_endpoint_rejects_client_selected_action(
    client: AsyncClient,
) -> None:
    service = DecisionService()
    app.dependency_overrides[get_authorized_principal] = authorized_security_principal
    app.dependency_overrides[get_runtime_assurance_actuation_decision_service] = lambda: service
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-actuation-requests/request-1/decision",
            json={
                "decision": "approved",
                "reason": "Attempt with client-selected action.",
                "action": "engage_kill_switch",
            },
            headers={"X-User-Id": "security-approver", "X-User-Areas": "security"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_actuation_decision_service, None)
        app.dependency_overrides.pop(get_authorized_principal, None)

    assert response.status_code == 422
    assert service.calls == []


async def test_actuation_decision_endpoint_rejects_force_and_approver_fields(
    client: AsyncClient,
) -> None:
    service = DecisionService()
    app.dependency_overrides[get_authorized_principal] = authorized_security_principal
    app.dependency_overrides[get_runtime_assurance_actuation_decision_service] = lambda: service
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-actuation-requests/request-1/decision",
            json={
                "decision": "approved",
                "reason": "Attempt with forbidden control fields.",
                "force": True,
                "approver": "some-user",
            },
            headers={"X-User-Id": "security-approver", "X-User-Areas": "security"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_actuation_decision_service, None)
        app.dependency_overrides.pop(get_authorized_principal, None)

    assert response.status_code == 422
    assert service.calls == []


async def test_actuation_decision_endpoint_rejects_blank_reason(
    client: AsyncClient,
) -> None:
    service = DecisionService()
    app.dependency_overrides[get_authorized_principal] = authorized_security_principal
    app.dependency_overrides[get_runtime_assurance_actuation_decision_service] = lambda: service
    try:
        response = await client.post(
            "/api/v1/runtime-assurance-actuation-requests/request-1/decision",
            json={"decision": "rejected", "reason": "   "},
            headers={"X-User-Id": "security-approver", "X-User-Areas": "security"},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_assurance_actuation_decision_service, None)
        app.dependency_overrides.pop(get_authorized_principal, None)

    assert response.status_code == 422
    assert service.calls == []
