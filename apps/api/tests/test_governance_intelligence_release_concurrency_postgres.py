"""PostgreSQL concurrency proof for globally single-use finding releases."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
from ai_governance_api.adapters.governance_intelligence_persistence import (
    SqlAlchemyGovernanceIntelligenceUnitOfWork,
)
from ai_governance_api.application.governance_intelligence import (
    GovernanceIntelligenceAnalysisType,
    GovernanceIntelligenceAuditRecord,
    GovernanceIntelligenceAuditStage,
    GovernanceIntelligenceFindingAudit,
    GovernanceIntelligenceFindingRelease,
    GovernanceIntelligenceReleaseConflict,
)
from ai_governance_api.models import (
    AuditEvent,
    Base,
    GovernanceIntelligenceFindingReleaseEntry,
)
from governance_schemas import (
    AgentRunProvenance,
    GovernanceFindingCandidate,
    GovernanceFindingEnvelope,
    GovernanceFindingType,
    GovernanceSourceReference,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

POSTGRES_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
FINDING_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
FIRST_RELEASE_ID = UUID("33333333-3333-4333-8333-333333333333")
SECOND_RELEASE_ID = UUID("44444444-4444-4444-8444-444444444444")
SUBJECT_ID = "55555555-5555-4555-8555-555555555555"
CORRELATION_ID = "corr:gi-3c-release-concurrency"
ACTOR_ID = "initiative-owner"
RELEASED_AT = datetime(2026, 8, 17, 19, 0, tzinfo=UTC)


@pytest.mark.skipif(
    POSTGRES_TEST_DATABASE_URL is None,
    reason="POSTGRES_TEST_DATABASE_URL is required for release concurrency verification",
)
async def test_concurrent_release_rebinding_preserves_one_atomic_winner() -> None:
    """Require one release/completion pair and reject the competing finding binding."""
    assert POSTGRES_TEST_DATABASE_URL is not None
    postgres_engine = create_async_engine(POSTGRES_TEST_DATABASE_URL)
    session_factory = async_sessionmaker(postgres_engine, expire_on_commit=False)
    try:
        async with postgres_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        start = asyncio.Event()

        async def persist(
            release_id: UUID,
            statement: str,
        ) -> GovernanceIntelligenceFindingRelease:
            envelope = _finding(statement)
            release = GovernanceIntelligenceFindingRelease.create(
                release_id=release_id,
                envelope=envelope,
                subject_id=SUBJECT_ID,
                correlation_id=CORRELATION_ID,
                released_at=RELEASED_AT,
            )
            record = _completion_record(release, envelope)
            unit = SqlAlchemyGovernanceIntelligenceUnitOfWork(session_factory)
            await start.wait()
            try:
                await unit.save_releases((release,))
                await unit.append(actor_id=ACTOR_ID, record=record)
                await unit.commit()
            except GovernanceIntelligenceReleaseConflict:
                await unit.rollback()
                raise
            return release

        first_task = asyncio.create_task(
            persist(FIRST_RELEASE_ID, "First advisory interpretation.")
        )
        second_task = asyncio.create_task(
            persist(SECOND_RELEASE_ID, "Competing advisory interpretation.")
        )
        start.set()
        results = await asyncio.gather(first_task, second_task, return_exceptions=True)

        releases = [
            result
            for result in results
            if isinstance(result, GovernanceIntelligenceFindingRelease)
        ]
        conflicts = [
            result
            for result in results
            if isinstance(result, GovernanceIntelligenceReleaseConflict)
        ]
        assert len(releases) == 1
        assert len(conflicts) == 1
        async with session_factory() as session:
            release_count = await session.scalar(
                select(func.count()).select_from(GovernanceIntelligenceFindingReleaseEntry)
            )
            audit_count = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "governance_intelligence.analysis_completed")
            )
            stored = await session.scalar(select(GovernanceIntelligenceFindingReleaseEntry))
        assert release_count == 1
        assert audit_count == 1
        assert stored is not None
        assert stored.release_id == str(releases[0].release_id)
        assert stored.release_digest == releases[0].release_digest
    finally:
        async with postgres_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await postgres_engine.dispose()


def _finding(statement: str) -> GovernanceFindingEnvelope:
    """Return one schema-valid envelope that competes for the same finding identity."""
    source = GovernanceSourceReference(
        artifact_id="evidence:66666666-6666-4666-8666-666666666666",
        version="1",
        content_digest="a" * 64,
    )
    return GovernanceFindingEnvelope(
        candidate=GovernanceFindingCandidate(
            finding_id=FINDING_ID,
            finding_type=GovernanceFindingType.RISK_CANDIDATE,
            statement=statement,
            confidence=0.75,
            sources=(source,),
            provenance=AgentRunProvenance(
                agent_run_id=RUN_ID,
                agent_name="risk_mapper",
                provider="provider-neutral",
                model="test-adapter",
                prompt_config_version="gi-3c-test-v1",
                retrieved_sources=(source,),
                created_at=RELEASED_AT,
                correlation_id=CORRELATION_ID,
            ),
        )
    )


def _completion_record(
    release: GovernanceIntelligenceFindingRelease,
    envelope: GovernanceFindingEnvelope,
) -> GovernanceIntelligenceAuditRecord:
    """Bind a minimized completion event to the candidate release transaction."""
    return GovernanceIntelligenceAuditRecord(
        stage=GovernanceIntelligenceAuditStage.ANALYSIS_COMPLETED,
        sequence=3,
        analysis_type=GovernanceIntelligenceAnalysisType.RISK_IDENTIFICATION,
        subject_id=SUBJECT_ID,
        correlation_id=CORRELATION_ID,
        administrator_access=False,
        references=envelope.candidate.sources,
        findings=(
            GovernanceIntelligenceFindingAudit(
                finding_id=str(release.finding_id),
                finding_type=release.finding_type,
                agent_run_id=str(release.agent_run_id),
                release_id=str(release.release_id),
                candidate_digest=release.candidate_digest,
                release_digest=release.release_digest,
                released_at=release.released_at,
            ),
        ),
    )
