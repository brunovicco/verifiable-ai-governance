"""PostgreSQL concurrency proof for idempotent advisory finding review."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
from ai_governance_api.adapters import SqlAlchemyInitiativeFindingReviewAuthorizer
from ai_governance_api.adapters.governance_intelligence_review_persistence import (
    SqlAlchemyGovernanceFindingReviewUnitOfWork,
)
from ai_governance_api.application.governance_intelligence_review import (
    GovernanceFindingReviewAccess,
    GovernanceFindingReviewDisposition,
    GovernanceFindingReviewError,
    GovernanceFindingReviewFailure,
    GovernanceFindingReviewReceipt,
    ReviewGovernanceFinding,
)
from ai_governance_api.models import (
    AuditEvent,
    Base,
    GovernanceFindingReviewReceiptEntry,
    Initiative,
)
from governance_schemas import (
    AgentRunProvenance,
    AutonomyLevel,
    DataClassification,
    DecisionImpact,
    GovernanceFindingCandidate,
    GovernanceFindingEnvelope,
    GovernanceFindingType,
    GovernanceSourceReference,
    HostingModel,
    RiskTier,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

POSTGRES_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
INITIATIVE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
REQUEST_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
FINDING_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
RUN_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
CORRELATION_ID = "corr:gi-3b-postgres-concurrency"
OWNER_ID = "initiative-owner"


@pytest.mark.skipif(
    POSTGRES_TEST_DATABASE_URL is None,
    reason="POSTGRES_TEST_DATABASE_URL is required for review concurrency verification",
)
async def test_concurrent_identical_review_requests_converge_to_one_receipt() -> None:
    """Require unique-request serialization and exact replay after the winning commit."""
    assert POSTGRES_TEST_DATABASE_URL is not None
    postgres_engine = create_async_engine(POSTGRES_TEST_DATABASE_URL)
    session_factory = async_sessionmaker(postgres_engine, expire_on_commit=False)
    try:
        async with postgres_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await _seed_initiative(session_factory)
        start = asyncio.Event()

        async def review() -> object:
            service = _service(session_factory)
            await start.wait()
            return await service.execute(
                request_id=REQUEST_ID,
                finding=_finding(),
                disposition=GovernanceFindingReviewDisposition.ACCEPTED_FOR_CONSIDERATION,
                access=GovernanceFindingReviewAccess(
                    actor_id=OWNER_ID,
                    subject_id=INITIATIVE_ID,
                    correlation_id=CORRELATION_ID,
                ),
            )

        first_task = asyncio.create_task(review())
        second_task = asyncio.create_task(review())
        start.set()
        first, second = await asyncio.gather(first_task, second_task)

        assert first == second
        async with session_factory() as session:
            receipt_count = await session.scalar(
                select(func.count()).select_from(GovernanceFindingReviewReceiptEntry)
            )
            audit_count = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "governance_intelligence.finding_reviewed")
            )
        assert receipt_count == 1
        assert audit_count == 1
    finally:
        async with postgres_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await postgres_engine.dispose()


@pytest.mark.skipif(
    POSTGRES_TEST_DATABASE_URL is None,
    reason="POSTGRES_TEST_DATABASE_URL is required for review concurrency verification",
)
async def test_concurrent_divergent_review_requests_preserve_one_winner() -> None:
    """Require one immutable winner and a conflict for divergent request reuse."""
    assert POSTGRES_TEST_DATABASE_URL is not None
    postgres_engine = create_async_engine(POSTGRES_TEST_DATABASE_URL)
    session_factory = async_sessionmaker(postgres_engine, expire_on_commit=False)
    try:
        async with postgres_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await _seed_initiative(session_factory)
        start = asyncio.Event()

        async def review(
            disposition: GovernanceFindingReviewDisposition,
        ) -> GovernanceFindingReviewReceipt:
            service = _service(session_factory)
            await start.wait()
            return await service.execute(
                request_id=REQUEST_ID,
                finding=_finding(),
                disposition=disposition,
                access=GovernanceFindingReviewAccess(
                    actor_id=OWNER_ID,
                    subject_id=INITIATIVE_ID,
                    correlation_id=CORRELATION_ID,
                ),
            )

        accepted_task = asyncio.create_task(
            review(GovernanceFindingReviewDisposition.ACCEPTED_FOR_CONSIDERATION)
        )
        rejected_task = asyncio.create_task(
            review(GovernanceFindingReviewDisposition.REJECTED)
        )
        start.set()
        results = await asyncio.gather(
            accepted_task,
            rejected_task,
            return_exceptions=True,
        )

        receipts = [
            result for result in results if isinstance(result, GovernanceFindingReviewReceipt)
        ]
        conflicts = [
            result for result in results if isinstance(result, GovernanceFindingReviewError)
        ]
        assert len(receipts) == 1
        assert len(conflicts) == 1
        assert conflicts[0].reason is GovernanceFindingReviewFailure.CONFLICT
        async with session_factory() as session:
            receipt_count = await session.scalar(
                select(func.count()).select_from(GovernanceFindingReviewReceiptEntry)
            )
            audit_count = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "governance_intelligence.finding_reviewed")
            )
        assert receipt_count == 1
        assert audit_count == 1
    finally:
        async with postgres_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await postgres_engine.dispose()


def _service(
    session_factory: async_sessionmaker[AsyncSession],
) -> ReviewGovernanceFinding:
    """Compose independent units sharing only the PostgreSQL database."""
    authorizer = SqlAlchemyInitiativeFindingReviewAuthorizer(session_factory)
    unit = SqlAlchemyGovernanceFindingReviewUnitOfWork(session_factory)
    return ReviewGovernanceFinding(authorizer, unit, unit, unit)


async def _seed_initiative(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Persist the exact initiative ownership boundary used by both requests."""
    async with session_factory() as session:
        session.add(
            Initiative(
                id=INITIATIVE_ID,
                name="GI-3B concurrency fixture",
                description="Serializes identical durable advisory review requests.",
                business_owner_id=OWNER_ID,
                business_area="AI Governance",
                intended_users="Internal reviewers",
                decision_impact=DecisionImpact.INFORMATIONAL,
                data_classification=DataClassification.INTERNAL,
                autonomy_level=AutonomyLevel.A1_RECOMMENDATION,
                hosting_model=HostingModel.SELF_HOSTED,
                risk_score=10,
                risk_tier=RiskTier.LOW,
                policy_id="test-policy",
                policy_version="2026.08",
                required_documents=[],
            )
        )
        await session.commit()


def _finding() -> GovernanceFindingEnvelope:
    """Return one immutable advisory candidate shared by both requests."""
    source = GovernanceSourceReference(
        artifact_id="evidence:eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        version="1",
        content_digest="a" * 64,
    )
    return GovernanceFindingEnvelope(
        candidate=GovernanceFindingCandidate(
            finding_id=FINDING_ID,
            finding_type=GovernanceFindingType.RISK_CANDIDATE,
            statement="The source may require a separately governed risk decision.",
            confidence=0.75,
            sources=(source,),
            provenance=AgentRunProvenance(
                agent_run_id=RUN_ID,
                agent_name="risk_mapper",
                provider="provider-neutral",
                model="test-adapter",
                prompt_config_version="gi-3b-test-v1",
                retrieved_sources=(source,),
                created_at=datetime(2026, 8, 17, 18, 0, tzinfo=UTC),
                correlation_id=CORRELATION_ID,
            ),
        )
    )
