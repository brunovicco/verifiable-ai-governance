"""PostgreSQL regression for the changes-requested governance workflow."""

import asyncio
import os

import pytest
from ai_governance_api.database import SessionFactory
from ai_governance_api.models import Approval, Initiative
from governance_schemas import ApprovalArea, ApprovalStatus, EntityStatus
from sqlalchemy import select

from scripts.seed_demo_data import DEMO_PREFIX, seed_case_03

CASE_NAME = f"{DEMO_PREFIX}Recomendador de conteúdo de treinamento"


async def _exercise_changes_requested_workflow() -> None:
    """Persist and reload the lifecycle state that exceeded the legacy width."""
    await seed_case_03()

    async with SessionFactory() as session:
        initiative = await session.scalar(select(Initiative).where(Initiative.name == CASE_NAME))

        assert initiative is not None
        assert initiative.status is EntityStatus.CHANGES_REQUESTED
        assert initiative.current_review_round == 1

        approval = await session.scalar(
            select(Approval).where(
                Approval.initiative_id == initiative.id,
                Approval.area == ApprovalArea.PRIVACY,
                Approval.status == ApprovalStatus.CHANGES_REQUESTED,
            )
        )

        assert approval is not None
        assert approval.status is ApprovalStatus.CHANGES_REQUESTED
        assert approval.review_round == 1


def test_changes_requested_persists_on_postgresql() -> None:
    """Exercise the production database behavior that failed in v0.2.0."""
    database_url = os.environ.get("DATABASE_URL", "")

    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("requires PostgreSQL through asyncpg")

    asyncio.run(_exercise_changes_requested_workflow())
