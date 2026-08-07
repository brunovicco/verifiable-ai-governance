import pytest
from ai_governance_api.config import AppEnvironment
from ai_governance_api.database import SessionFactory
from ai_governance_api.models import (
    Agent,
    Initiative,
    ModelRoutingDecisionEntry,
)
from governance_schemas import EntityStatus
from sqlalchemy import delete, select

from scripts.canonical_demo_seed import (
    ALLOWED_TASK_ID,
    BLOCKED_TASK_ID,
    INITIATIVE_NAME,
    RESET_CONFIRMATION,
    CanonicalDemoDriftError,
    DemoResetRefused,
    ensure_canonical_demo,
    inspect_canonical_demo,
    reset_application_data,
    validate_reset_request,
)


async def test_canonical_seed_is_complete_and_idempotent() -> None:
    created = await ensure_canonical_demo()
    current = await ensure_canonical_demo()

    assert created.state == "created"
    assert current.state == "current"
    assert current.initiative_id == created.initiative_id
    assert current.ai_system_id == created.ai_system_id
    assert current.agent_id == created.agent_id
    assert current.allowed_routing_decision_id == (
        created.allowed_routing_decision_id
    )
    assert current.blocked_routing_decision_id == (
        created.blocked_routing_decision_id
    )
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


async def test_partial_existing_scenario_fails_closed() -> None:
    summary = await ensure_canonical_demo()
    async with SessionFactory() as session:
        await session.execute(
            delete(ModelRoutingDecisionEntry).where(
                ModelRoutingDecisionEntry.id
                == summary.blocked_routing_decision_id
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


async def test_explicit_reset_clears_and_allows_reproducible_reseed() -> None:
    first = await ensure_canonical_demo()

    await reset_application_data(confirmation=RESET_CONFIRMATION)

    assert await inspect_canonical_demo() is None
    second = await ensure_canonical_demo()

    assert second.initiative_id != first.initiative_id
    assert second.scenario_id == first.scenario_id
    assert second.scenario_version == first.scenario_version
    assert second.assessment_count == first.assessment_count
    assert second.control_ids == first.control_ids
