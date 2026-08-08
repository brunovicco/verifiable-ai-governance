"""HTTP and persistence tests for direct emergency runtime-control operations."""

from ai_governance_api.database import SessionFactory
from ai_governance_api.models import (
    Agent,
    AISystem,
    AuditEvent,
    Initiative,
    RuntimeControlTransitionEntry,
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

OWNER_HEADERS = {"X-User-Id": "runtime-owner"}
STRANGER_HEADERS = {"X-User-Id": "stranger"}


async def _seed_agent() -> str:
    async with SessionFactory() as session:
        initiative = Initiative(
            id="initiative-runtime-control",
            name="Runtime control initiative",
            description="Exercise direct emergency runtime control.",
            business_owner_id="runtime-owner",
            business_area="AI Platform",
            intended_users="Internal services",
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
            id="system-runtime-control",
            initiative=initiative,
            name="Runtime control system",
            purpose="Exercise emergency-stop HTTP semantics.",
            owner_id="runtime-owner",
            status=EntityStatus.ACTIVE,
            risk_tier=RiskTier.MEDIUM,
            production=True,
            metadata_json={},
        )
        agent = Agent(
            id="agent-runtime-control",
            ai_system=ai_system,
            name="Runtime controlled agent",
            purpose="Exercise emergency stop and safe restore.",
            owner_id="runtime-owner",
            agent_version="1.0.0",
            deployment_region="Brazil South",
            autonomy_level=AutonomyLevel.A1_RECOMMENDATION,
            allowed_models=[],
            tools=[],
            permissions=[],
            human_approval_points=[],
            kill_switch_enabled=True,
            status=EntityStatus.DRAFT,
        )
        session.add_all([initiative, ai_system, agent])
        await session.commit()
        return agent.id


async def test_direct_activate_and_restore_are_monotonic_and_audited(
    client: AsyncClient,
) -> None:
    agent_id = await _seed_agent()

    activated = await client.post(
        f"/api/v1/agents/{agent_id}/runtime-control/activate",
        json={"expected_version": 1, "reason": "Emergency containment"},
        headers=OWNER_HEADERS,
    )
    assert activated.status_code == 200
    assert activated.json()["kill_switch_engaged"] is True
    assert activated.json()["control_epoch"] == 1
    assert activated.json()["revoked_through_agent_version"] == 1
    assert activated.json()["agent_version"] == 2

    restored = await client.post(
        f"/api/v1/agents/{agent_id}/runtime-control/deactivate",
        json={"expected_version": 2, "reason": "Remediation verified"},
        headers=OWNER_HEADERS,
    )
    assert restored.status_code == 200
    assert restored.json()["kill_switch_engaged"] is False
    assert restored.json()["control_epoch"] == 2
    assert restored.json()["revoked_through_agent_version"] == 2
    assert restored.json()["agent_version"] == 3

    async with SessionFactory() as session:
        transitions = list(
            await session.scalars(
                select(RuntimeControlTransitionEntry).order_by(
                    RuntimeControlTransitionEntry.control_epoch
                )
            )
        )
        audit_actions = list(
            await session.scalars(
                select(AuditEvent.action)
                .where(AuditEvent.entity_type == "runtime_control_transition")
                .order_by(AuditEvent.occurred_at, AuditEvent.id)
            )
        )

    assert [transition.status for transition in transitions] == ["applied", "applied"]
    assert [transition.control_epoch for transition in transitions] == [1, 2]
    assert set(audit_actions) == {
        "runtime_control.activation_requested",
        "runtime_control.activated",
        "runtime_control.deactivation_requested",
        "runtime_control.deactivated",
    }
    assert len(audit_actions) == 4


async def test_direct_runtime_control_rejects_non_owner(client: AsyncClient) -> None:
    agent_id = await _seed_agent()

    response = await client.post(
        f"/api/v1/agents/{agent_id}/runtime-control/activate",
        json={"expected_version": 1, "reason": "Untrusted attempt"},
        headers=STRANGER_HEADERS,
    )

    assert response.status_code == 403
