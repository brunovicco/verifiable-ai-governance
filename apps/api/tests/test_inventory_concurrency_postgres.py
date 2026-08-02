import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.domain.identity import Principal
from ai_governance_api.errors import ApplicationError, ErrorKind
from ai_governance_api.models import AISystem, Base, Initiative, ModelAsset
from ai_governance_api.schemas import AssetReviewRequest, ModelAssetUpdate
from ai_governance_api.services.inventory import InventoryService
from governance_schemas import (
    ApprovalArea,
    AutonomyLevel,
    DataClassification,
    DecisionImpact,
    EntityStatus,
    HostingModel,
    RiskTier,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

POSTGRES_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")


@pytest.mark.skipif(
    POSTGRES_TEST_DATABASE_URL is None,
    reason="POSTGRES_TEST_DATABASE_URL is required for row-lock verification",
)
async def test_concurrent_model_update_and_review_are_serialized() -> None:
    """Allow one command and reject the stale command after the system lock."""
    assert POSTGRES_TEST_DATABASE_URL is not None
    postgres_engine = create_async_engine(POSTGRES_TEST_DATABASE_URL)
    session_factory = async_sessionmaker(
        postgres_engine,
        expire_on_commit=False,
    )
    try:
        async with postgres_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        model_id = await _seed_reviewable_model(session_factory)
        start = asyncio.Event()

        async def update_model() -> ModelAsset:
            await start.wait()
            async with session_factory() as session:
                return await InventoryService(session).update_model(
                    model_id,
                    ModelAssetUpdate(
                        expected_version=1,
                        deployment_region="Brazil Southeast",
                    ),
                    Principal(user_id="system-owner"),
                )

        async def review_model() -> ModelAsset:
            await start.wait()
            async with session_factory() as session:
                return await InventoryService(session).review_model(
                    model_id,
                    AssetReviewRequest(
                        expected_version=1,
                        next_review_at=datetime.now(UTC) + timedelta(days=30),
                        reference="ARCH-CONCURRENCY-001",
                    ),
                    Principal(
                        user_id="architecture-reviewer",
                        approval_areas=frozenset({ApprovalArea.ARCHITECTURE}),
                    ),
                )

        start.set()
        results = await asyncio.gather(
            update_model(),
            review_model(),
            return_exceptions=True,
        )

        successes = [result for result in results if isinstance(result, ModelAsset)]
        conflicts = [
            result
            for result in results
            if isinstance(result, ApplicationError)
            and result.kind is ErrorKind.CONFLICT
        ]
        assert len(successes) == 1
        assert len(conflicts) == 1

        async with session_factory() as session:
            persisted = await session.scalar(
                select(ModelAsset).where(ModelAsset.id == model_id)
            )
            assert persisted is not None
            assert persisted.version == 2
            if persisted.status is EntityStatus.APPROVED:
                assert persisted.deployment_region == "Brazil South"
                assert persisted.approved_scope_digest is not None
            else:
                assert persisted.status is EntityStatus.DRAFT
                assert persisted.deployment_region == "Brazil Southeast"
                assert persisted.approved_scope_digest is None
    finally:
        async with postgres_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await postgres_engine.dispose()


async def _seed_reviewable_model(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    """Create one minimal approved system and draft model in PostgreSQL."""
    async with session_factory() as session:
        initiative = Initiative(
            name="Concurrent inventory validation",
            description="Validates serialization of governed inventory commands.",
            business_owner_id="initiative-owner",
            business_area="Architecture",
            intended_users="Platform maintainers",
            decision_impact=DecisionImpact.INFORMATIONAL,
            data_classification=DataClassification.INTERNAL,
            autonomy_level=AutonomyLevel.A0_INFORMATION,
            hosting_model=HostingModel.SELF_HOSTED,
            status=EntityStatus.APPROVED,
            risk_score=20,
            risk_tier=RiskTier.MEDIUM,
            policy_id="baseline",
            policy_version="1.0.0",
        )
        ai_system = AISystem(
            initiative=initiative,
            name="Concurrent system",
            purpose="Exercise transactional inventory guarantees.",
            owner_id="system-owner",
            status=EntityStatus.APPROVED,
            risk_tier=RiskTier.MEDIUM,
            production=False,
        )
        model = ModelAsset(
            ai_system=ai_system,
            provider="Example AI",
            model_name="governed-medium",
            model_version="2026-08-01",
            routing_group="reasoning-medium",
            deployment_region="Brazil South",
            approved_use_cases=["knowledge assistance"],
            prohibited_use_cases=["employment decision"],
            allowed_data_classes=["internal"],
            status=EntityStatus.DRAFT,
            evaluation_baseline={"dataset": "baseline-v1"},
        )
        session.add_all([initiative, ai_system, model])
        await session.commit()
        return model.id
