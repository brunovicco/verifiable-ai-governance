import pytest
from ai_governance_api.config import AppEnvironment
from ai_governance_api.database import SessionFactory
from ai_governance_api.models import (
    Agent,
    AISystem,
    Approval,
    Assessment,
    Evidence,
    Initiative,
    ModelAsset,
    ModelRoutingDecisionEntry,
    ReviewSubmission,
)
from governance_schemas import EntityStatus
from sqlalchemy import delete, select

from scripts.canonical_demo_identity import (
    CANONICAL_DEMO_AGENT_ID,
    CANONICAL_DEMO_APPROVED_MODEL_ID,
    CANONICAL_DEMO_INITIATIVE_ID,
    CANONICAL_DEMO_INITIATIVE_NAME,
    CANONICAL_DEMO_OUT_OF_SCOPE_MODEL_ID,
    CANONICAL_DEMO_SCENARIO_ID,
    CANONICAL_DEMO_SYSTEM_ID,
    canonical_demo_id,
    install_canonical_demo_identity_listener,
)
from scripts.canonical_demo_seed import (
    AGENT_NAME,
    ALLOWED_TASK_ID,
    APPROVED_MODEL_NAME,
    BLOCKED_TASK_ID,
    INITIATIVE_NAME,
    OUT_OF_SCOPE_MODEL_NAME,
    RESET_CONFIRMATION,
    SCENARIO_ID,
    SYSTEM_NAME,
    CanonicalDemoDriftError,
    DemoResetRefused,
    ensure_canonical_demo,
    inspect_canonical_demo,
    reset_application_data,
    validate_reset_request,
)

install_canonical_demo_identity_listener()


async def test_canonical_seed_is_complete_and_idempotent() -> None:
    created = await ensure_canonical_demo()
    current = await ensure_canonical_demo()

    assert created.state == "created"
    assert current.state == "current"
    assert current.initiative_id == created.initiative_id
    assert current.ai_system_id == created.ai_system_id
    assert current.agent_id == created.agent_id
    assert current.allowed_routing_decision_id == created.allowed_routing_decision_id
    assert current.blocked_routing_decision_id == created.blocked_routing_decision_id
    assert current.assessment_count == 3
    assert current.approval_count >= 1
    assert current.evidence_count >= 6

    async with SessionFactory() as session:
        initiative = await session.scalar(
            select(Initiative).where(Initiative.name == INITIATIVE_NAME)
        )
        agent = await session.get(Agent, current.agent_id)
        decisions = tuple(
            await session.scalars(
                select(ModelRoutingDecisionEntry).where(
                    ModelRoutingDecisionEntry.agent_id == current.agent_id
                )
            )
        )

    assert initiative is not None
    assert initiative.status is EntityStatus.APPROVED
    assert agent is not None
    assert "credit:approve" not in agent.permissions
    assert {decision.task_id for decision in decisions} == {
        ALLOWED_TASK_ID,
        BLOCKED_TASK_ID,
    }


def test_canonical_identity_contract_is_version_independent() -> None:
    assert CANONICAL_DEMO_SCENARIO_ID == SCENARIO_ID
    assert CANONICAL_DEMO_INITIATIVE_NAME == INITIATIVE_NAME
    assert SYSTEM_NAME == "Mesa de Crédito PJ Governada"
    assert APPROVED_MODEL_NAME == "credit-opinion-approved"
    assert OUT_OF_SCOPE_MODEL_NAME == "credit-opinion-experimental"
    assert AGENT_NAME == "Agente de Parecer de Crédito PJ"

    assert CANONICAL_DEMO_INITIATIVE_ID == "e3095057-9408-561b-a755-cfc9f1453af5"
    assert CANONICAL_DEMO_SYSTEM_ID == "eabfd874-b6ca-5319-b7e1-30cae5d798df"
    assert CANONICAL_DEMO_APPROVED_MODEL_ID == "9a798288-ea72-5e4d-ac33-dfc7533d80cb"
    assert CANONICAL_DEMO_OUT_OF_SCOPE_MODEL_ID == "150df55c-7ca6-551b-826d-545ccbe1dff5"
    assert CANONICAL_DEMO_AGENT_ID == "565aa2b9-ead9-59e6-89a9-18920cced7ce"
    assert canonical_demo_id("initiative") == CANONICAL_DEMO_INITIATIVE_ID


async def test_seed_assigns_deterministic_canonical_entity_ids() -> None:
    summary = await ensure_canonical_demo()

    assert summary.initiative_id == CANONICAL_DEMO_INITIATIVE_ID
    assert summary.ai_system_id == CANONICAL_DEMO_SYSTEM_ID
    assert summary.approved_model_id == CANONICAL_DEMO_APPROVED_MODEL_ID
    assert summary.out_of_scope_model_id == CANONICAL_DEMO_OUT_OF_SCOPE_MODEL_ID
    assert summary.agent_id == CANONICAL_DEMO_AGENT_ID

    snapshot = await _canonical_identity_snapshot(summary.initiative_id, summary.ai_system_id)
    assert snapshot


async def test_partial_existing_scenario_fails_closed() -> None:
    summary = await ensure_canonical_demo()
    async with SessionFactory() as session:
        await session.execute(
            delete(ModelRoutingDecisionEntry).where(
                ModelRoutingDecisionEntry.id == summary.blocked_routing_decision_id
            )
        )
        await session.commit()

    with pytest.raises(
        CanonicalDemoDriftError,
        match="incomplete or inconsistent",
    ):
        await inspect_canonical_demo()


def test_reset_requires_exact_confirmation() -> None:
    with pytest.raises(DemoResetRefused, match="exact confirmation"):
        validate_reset_request(
            environment=AppEnvironment.LOCAL,
            confirmation="yes",
        )

    validate_reset_request(
        environment=AppEnvironment.LOCAL,
        confirmation=RESET_CONFIRMATION,
    )


def test_reset_is_disabled_in_production() -> None:
    with pytest.raises(DemoResetRefused, match="APP_ENV=production"):
        validate_reset_request(
            environment=AppEnvironment.PRODUCTION,
            confirmation=RESET_CONFIRMATION,
        )


async def test_explicit_reset_preserves_all_canonical_identities() -> None:
    first = await ensure_canonical_demo()
    first_snapshot = await _canonical_identity_snapshot(
        first.initiative_id,
        first.ai_system_id,
    )

    await reset_application_data(confirmation=RESET_CONFIRMATION)

    assert await inspect_canonical_demo() is None
    second = await ensure_canonical_demo()
    second_snapshot = await _canonical_identity_snapshot(
        second.initiative_id,
        second.ai_system_id,
    )

    assert second.initiative_id == first.initiative_id
    assert second.ai_system_id == first.ai_system_id
    assert second.approved_model_id == first.approved_model_id
    assert second.out_of_scope_model_id == first.out_of_scope_model_id
    assert second.agent_id == first.agent_id
    assert second.allowed_routing_decision_id == first.allowed_routing_decision_id
    assert second.blocked_routing_decision_id == first.blocked_routing_decision_id
    assert second.incident_id == first.incident_id
    assert second.scenario_id == first.scenario_id
    assert second.scenario_version == first.scenario_version
    assert second.assessment_count == first.assessment_count
    assert second.control_ids == first.control_ids
    assert second_snapshot == first_snapshot


async def _canonical_identity_snapshot(
    initiative_id: str,
    ai_system_id: str,
) -> tuple[str, ...]:
    """Return every seeded business-row identifier in a stable comparable form."""
    async with SessionFactory() as session:
        systems = tuple(
            await session.scalars(select(AISystem).where(AISystem.initiative_id == initiative_id))
        )
        models = tuple(
            await session.scalars(select(ModelAsset).where(ModelAsset.ai_system_id == ai_system_id))
        )
        agents = tuple(
            await session.scalars(select(Agent).where(Agent.ai_system_id == ai_system_id))
        )
        assessments = tuple(
            await session.scalars(
                select(Assessment).where(Assessment.initiative_id == initiative_id)
            )
        )
        approvals = tuple(
            await session.scalars(select(Approval).where(Approval.initiative_id == initiative_id))
        )
        evidence = tuple(
            await session.scalars(select(Evidence).where(Evidence.initiative_id == initiative_id))
        )
        submissions = tuple(
            await session.scalars(
                select(ReviewSubmission).where(ReviewSubmission.initiative_id == initiative_id)
            )
        )

    identities = [f"ai-system:{item.id}" for item in systems]
    identities.extend(f"model:{item.id}" for item in models)
    identities.extend(f"agent:{item.id}" for item in agents)
    identities.extend(f"assessment:{item.id}" for item in assessments)
    identities.extend(f"approval:{item.id}" for item in approvals)
    identities.extend(f"evidence:{item.id}" for item in evidence)
    identities.extend(f"review-submission:{item.id}" for item in submissions)
    return tuple(sorted(identities))
