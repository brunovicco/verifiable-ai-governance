"""HTTP and persistence tests for incident, kill-switch, and exception management."""

from datetime import UTC, datetime, timedelta

from ai_governance_api.auth import get_principal
from ai_governance_api.database import SessionFactory
from ai_governance_api.domain.identity import Principal
from ai_governance_api.main import app
from ai_governance_api.models import (
    Agent,
    AISystem,
    AuditEvent,
    Incident,
    Initiative,
    PolicyException,
)
from governance_schemas import (
    AutonomyLevel,
    DataClassification,
    DecisionImpact,
    EntityStatus,
    HostingModel,
    RiskTier,
)
from httpx import AsyncClient
from sqlalchemy import select

OWNER_HEADERS = {"X-User-Id": "system-owner"}
STRANGER_HEADERS = {"X-User-Id": "stranger"}
NOW = datetime.now(UTC)


def as_admin(user_id: str = "admin-1") -> None:
    """Override the resolved principal with an administrator for one call."""
    app.dependency_overrides[get_principal] = lambda: Principal(user_id=user_id, is_admin=True)


def clear_principal_override() -> None:
    """Remove any principal override installed by a test."""
    app.dependency_overrides.pop(get_principal, None)


async def seed_system(*, kill_switch_enabled: bool = True) -> tuple[str, str]:
    """Persist an AI system and one agent, returning their ids."""
    async with SessionFactory() as session:
        initiative = Initiative(
            id="initiative-incidents",
            name="Incident-managed initiative",
            description="Exercise incident, kill-switch, and exception governance.",
            business_owner_id="initiative-owner",
            business_area="AI Platform",
            intended_users="Internal platform services",
            decision_impact=DecisionImpact.INFORMATIONAL,
            data_classification=DataClassification.INTERNAL,
            autonomy_level=AutonomyLevel.A1_RECOMMENDATION,
            hosting_model=HostingModel.SELF_HOSTED,
            affects_rights=False,
            executes_actions=False,
            personal_data=False,
            sensitive_data=False,
            children_data=False,
            external_facing=False,
            regulated_context=False,
            international_processing=False,
            inference_countries=[],
            uses_rag=False,
            uses_agents=True,
            uses_mcp=False,
            uses_custom_model=False,
            status=EntityStatus.APPROVED,
            risk_score=20,
            risk_tier=RiskTier.MEDIUM,
            policy_id="governance-policy",
            policy_version="2026.08",
            required_documents=[],
        )
        ai_system = AISystem(
            id="system-incidents",
            initiative=initiative,
            name="Incident-managed system",
            purpose="Exercise incident response endpoints end to end.",
            owner_id="system-owner",
            status=EntityStatus.ACTIVE,
            risk_tier=RiskTier.MEDIUM,
            production=True,
            metadata_json={},
        )
        agent = Agent(
            id="agent-incidents",
            ai_system=ai_system,
            name="Knowledge agent",
            purpose="Extract structured facts from approved internal documents.",
            owner_id="system-owner",
            agent_version="1.0.0",
            deployment_region="Brazil South",
            autonomy_level=AutonomyLevel.A1_RECOMMENDATION,
            allowed_models=[],
            tools=[],
            permissions=[],
            human_approval_points=[],
            kill_switch_enabled=kill_switch_enabled,
            status=EntityStatus.DRAFT,
        )
        session.add_all([initiative, ai_system, agent])
        await session.commit()
    return ai_system.id, agent.id


def report_payload() -> dict[str, object]:
    """Return a valid public incident-report command."""
    return {
        "title": "Agent produced unverified financial figures",
        "severity": "high",
        "description": "Agent output referenced a data source outside its approved scope.",
        "detected_at": NOW.isoformat(),
    }


async def test_incident_lifecycle_report_contain_remediate_close(
    client: AsyncClient,
) -> None:
    system_id, _agent_id = await seed_system()

    reported = await client.post(
        f"/api/v1/systems/{system_id}/incidents",
        json=report_payload(),
        headers=OWNER_HEADERS,
    )
    assert reported.status_code == 201
    incident_id = reported.json()["id"]
    assert reported.json()["status"] == "open"

    fetched = await client.get(f"/api/v1/incidents/{incident_id}", headers=OWNER_HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == incident_id

    forbidden = await client.get(f"/api/v1/incidents/{incident_id}", headers=STRANGER_HEADERS)
    assert forbidden.status_code == 403

    contained = await client.post(
        f"/api/v1/incidents/{incident_id}/contain",
        json={"containment": "Disabled the offending tool.", "expected_version": 1},
        headers=OWNER_HEADERS,
    )
    assert contained.status_code == 200
    assert contained.json()["status"] == "contained"

    plan = await client.post(
        f"/api/v1/incidents/{incident_id}/remediation-plan",
        json={
            "remediation_owner_id": "system-owner",
            "remediation_description": "Rotate credentials and retrain the agent.",
            "remediation_due_at": (NOW + timedelta(days=7)).isoformat(),
            "expected_version": 2,
        },
        headers=OWNER_HEADERS,
    )
    assert plan.status_code == 200
    assert plan.json()["status"] == "remediating"

    closed = await client.post(
        f"/api/v1/incidents/{incident_id}/close",
        json={"expected_version": 3},
        headers=OWNER_HEADERS,
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    listed = await client.get(f"/api/v1/systems/{system_id}/incidents", headers=OWNER_HEADERS)
    assert [item["id"] for item in listed.json()] == [incident_id]

    async with SessionFactory() as session:
        persisted = await session.scalar(select(Incident))
        audit_events = list(
            await session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "incident")
                .order_by(AuditEvent.entity_version)
            )
        )
    assert persisted is not None
    assert persisted.status.value == "closed"
    assert [event.action for event in audit_events] == [
        "incident.reported",
        "incident.contained",
        "incident.remediation_plan_set",
        "incident.closed",
    ]


async def test_close_without_remediation_plan_is_a_conflict(client: AsyncClient) -> None:
    system_id, _agent_id = await seed_system()
    reported = await client.post(
        f"/api/v1/systems/{system_id}/incidents",
        json=report_payload(),
        headers=OWNER_HEADERS,
    )
    incident_id = reported.json()["id"]
    await client.post(
        f"/api/v1/incidents/{incident_id}/contain",
        json={"containment": "Contained.", "expected_version": 1},
        headers=OWNER_HEADERS,
    )

    response = await client.post(
        f"/api/v1/incidents/{incident_id}/close",
        json={"expected_version": 2},
        headers=OWNER_HEADERS,
    )
    assert response.status_code == 409


async def test_incident_endpoints_reject_non_owner_non_admin(client: AsyncClient) -> None:
    system_id, _agent_id = await seed_system()

    response = await client.post(
        f"/api/v1/systems/{system_id}/incidents",
        json=report_payload(),
        headers=STRANGER_HEADERS,
    )
    assert response.status_code == 403


async def test_kill_switch_engage_and_restore_round_trip(client: AsyncClient) -> None:
    system_id, agent_id = await seed_system()
    reported = await client.post(
        f"/api/v1/systems/{system_id}/incidents",
        json=report_payload(),
        headers=OWNER_HEADERS,
    )
    incident_id = reported.json()["id"]

    engaged = await client.post(
        f"/api/v1/incidents/{incident_id}/agents/{agent_id}/kill-switch/engage",
        json={"expected_version": 1},
        headers=OWNER_HEADERS,
    )
    assert engaged.status_code == 200
    assert engaged.json()["kill_switch_engaged"] is True

    restored = await client.post(
        f"/api/v1/incidents/{incident_id}/agents/{agent_id}/kill-switch/restore",
        json={"expected_version": 2},
        headers=OWNER_HEADERS,
    )
    assert restored.status_code == 200
    assert restored.json()["kill_switch_engaged"] is False


async def test_kill_switch_engage_rejects_agent_without_declared_switch(
    client: AsyncClient,
) -> None:
    system_id, agent_id = await seed_system(kill_switch_enabled=False)
    reported = await client.post(
        f"/api/v1/systems/{system_id}/incidents",
        json=report_payload(),
        headers=OWNER_HEADERS,
    )
    incident_id = reported.json()["id"]

    response = await client.post(
        f"/api/v1/incidents/{incident_id}/agents/{agent_id}/kill-switch/engage",
        json={"expected_version": 1},
        headers=OWNER_HEADERS,
    )
    assert response.status_code == 409


async def test_exception_request_decide_and_revoke(client: AsyncClient) -> None:
    system_id, _agent_id = await seed_system()
    reported = await client.post(
        f"/api/v1/systems/{system_id}/incidents",
        json=report_payload(),
        headers=OWNER_HEADERS,
    )
    incident_id = reported.json()["id"]

    requested = await client.post(
        f"/api/v1/incidents/{incident_id}/exceptions",
        json={
            "purpose": "Keep serving cached results while remediation is in progress.",
            "scope_description": "Bypass real-time verification for read-only queries.",
            "compensating_controls": "Manual spot-check every hour by Security.",
            "expires_at": (NOW + timedelta(days=2)).isoformat(),
        },
        headers=OWNER_HEADERS,
    )
    assert requested.status_code == 201
    exception_id = requested.json()["id"]
    assert requested.json()["status"] == "pending"
    assert requested.json()["state"] == "pending"

    try:
        as_admin("system-owner")
        self_decision = await client.post(
            f"/api/v1/exceptions/{exception_id}/decide",
            json={"approved": True, "expected_version": 1},
        )
        assert self_decision.status_code == 403

        as_admin("admin-1")
        decided = await client.post(
            f"/api/v1/exceptions/{exception_id}/decide",
            json={
                "approved": True,
                "decision_reason": "Compensating controls are adequate.",
                "expected_version": 1,
            },
        )
        assert decided.status_code == 200
        assert decided.json()["status"] == "approved"
        assert decided.json()["state"] == "active"

        revoked = await client.post(
            f"/api/v1/exceptions/{exception_id}/revoke",
            json={"decision_reason": "Remediation completed early.", "expected_version": 2},
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
    finally:
        clear_principal_override()

    listed = await client.get(f"/api/v1/incidents/{incident_id}/exceptions", headers=OWNER_HEADERS)
    assert [item["id"] for item in listed.json()] == [exception_id]

    async with SessionFactory() as session:
        persisted = await session.scalar(select(PolicyException))
    assert persisted is not None
    assert persisted.status.value == "revoked"
