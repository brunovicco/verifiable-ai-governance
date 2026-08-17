"""Persistence and integrity proofs for GI-2 finding release evidence."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest
from ai_governance_api.adapters.governance_intelligence_persistence import (
    SqlAlchemyGovernanceFindingReleaseVerifier,
    SqlAlchemyGovernanceIntelligenceUnitOfWork,
)
from ai_governance_api.application.governance_intelligence import (
    GovernanceIntelligenceFindingRelease,
)
from ai_governance_api.application.governance_intelligence_integrity import (
    governance_finding_envelope_digest,
)
from ai_governance_api.application.governance_intelligence_review import (
    GovernanceFindingReviewDependencyError,
)
from ai_governance_api.database import SessionFactory
from ai_governance_api.models import GovernanceIntelligenceFindingReleaseEntry
from governance_schemas import (
    AgentRunProvenance,
    GovernanceFindingCandidate,
    GovernanceFindingEnvelope,
    GovernanceFindingType,
    GovernanceSourceReference,
)
from sqlalchemy import select

RELEASE_ID = UUID("11111111-1111-4111-8111-111111111111")
FINDING_ID = UUID("22222222-2222-4222-8222-222222222222")
RUN_ID = UUID("33333333-3333-4333-8333-333333333333")
OTHER_RUN_ID = UUID("44444444-4444-4444-8444-444444444444")
SUBJECT_ID = "55555555-5555-4555-8555-555555555555"
CORRELATION_ID = "corr:gi-3c-release-verification"
RELEASED_AT = datetime(2026, 8, 17, 18, 30, tzinfo=UTC)
SOURCE_CONTENT = b'{"control":"GOV-001","passed":true}'


def _envelope(*, statement: str = "The evidence may support reviewer consideration.") -> (
    GovernanceFindingEnvelope
):
    source = GovernanceSourceReference(
        artifact_id="evidence:66666666-6666-4666-8666-666666666666",
        version="1",
        content_digest=hashlib.sha256(SOURCE_CONTENT).hexdigest(),
    )
    return GovernanceFindingEnvelope(
        candidate=GovernanceFindingCandidate(
            finding_id=FINDING_ID,
            finding_type=GovernanceFindingType.EVIDENCE_INTERPRETATION,
            statement=statement,
            confidence=0.76,
            sources=(source,),
            provenance=AgentRunProvenance(
                agent_run_id=RUN_ID,
                agent_name="evidence_interpreter",
                provider="provider-neutral",
                model="deterministic-test-adapter",
                prompt_config_version="gi-3c-test-v1",
                retrieved_sources=(source,),
                created_at=RELEASED_AT,
                correlation_id=CORRELATION_ID,
            ),
        )
    )


async def _persist_release(
    envelope: GovernanceFindingEnvelope,
) -> GovernanceIntelligenceFindingRelease:
    release = GovernanceIntelligenceFindingRelease.create(
        release_id=RELEASE_ID,
        envelope=envelope,
        subject_id=SUBJECT_ID,
        correlation_id=CORRELATION_ID,
        released_at=RELEASED_AT,
    )
    unit = SqlAlchemyGovernanceIntelligenceUnitOfWork(SessionFactory)
    await unit.save_releases((release,))
    await unit.commit()
    return release


async def test_release_verifier_requires_the_exact_complete_envelope_binding() -> None:
    envelope = _envelope()
    release = await _persist_release(envelope)
    verifier = SqlAlchemyGovernanceFindingReleaseVerifier(SessionFactory)

    assert await verifier.was_released(
        finding_schema_version=envelope.schema_version,
        finding_id=FINDING_ID,
        finding_type=GovernanceFindingType.EVIDENCE_INTERPRETATION,
        agent_run_id=RUN_ID,
        candidate_digest=release.candidate_digest,
        subject_id=SUBJECT_ID,
        correlation_id=CORRELATION_ID,
    )
    forged = _envelope(statement="A fabricated but schema-valid interpretation.")
    assert not await verifier.was_released(
        finding_schema_version=forged.schema_version,
        finding_id=FINDING_ID,
        finding_type=GovernanceFindingType.EVIDENCE_INTERPRETATION,
        agent_run_id=RUN_ID,
        candidate_digest=governance_finding_envelope_digest(forged),
        subject_id=SUBJECT_ID,
        correlation_id=CORRELATION_ID,
    )
    assert not await verifier.was_released(
        finding_schema_version=envelope.schema_version,
        finding_id=FINDING_ID,
        finding_type=GovernanceFindingType.EVIDENCE_INTERPRETATION,
        agent_run_id=OTHER_RUN_ID,
        candidate_digest=release.candidate_digest,
        subject_id=SUBJECT_ID,
        correlation_id=CORRELATION_ID,
    )
    assert not await verifier.was_released(
        finding_schema_version=envelope.schema_version,
        finding_id=FINDING_ID,
        finding_type=GovernanceFindingType.EVIDENCE_INTERPRETATION,
        agent_run_id=RUN_ID,
        candidate_digest=release.candidate_digest,
        subject_id="77777777-7777-4777-8777-777777777777",
        correlation_id=CORRELATION_ID,
    )
    assert not await verifier.was_released(
        finding_schema_version=envelope.schema_version,
        finding_id=FINDING_ID,
        finding_type=GovernanceFindingType.EVIDENCE_INTERPRETATION,
        agent_run_id=RUN_ID,
        candidate_digest=release.candidate_digest,
        subject_id=SUBJECT_ID,
        correlation_id="corr:different",
    )


async def test_release_verifier_returns_false_when_evidence_is_absent() -> None:
    envelope = _envelope()

    assert not await SqlAlchemyGovernanceFindingReleaseVerifier(
        SessionFactory
    ).was_released(
        finding_schema_version=envelope.schema_version,
        finding_id=FINDING_ID,
        finding_type=GovernanceFindingType.EVIDENCE_INTERPRETATION,
        agent_run_id=RUN_ID,
        candidate_digest=governance_finding_envelope_digest(envelope),
        subject_id=SUBJECT_ID,
        correlation_id=CORRELATION_ID,
    )


async def test_release_verifier_fails_closed_on_corrupt_persisted_evidence() -> None:
    envelope = _envelope()
    await _persist_release(envelope)
    async with SessionFactory() as session:
        stored = await session.scalar(
            select(GovernanceIntelligenceFindingReleaseEntry).where(
                GovernanceIntelligenceFindingReleaseEntry.finding_id == str(FINDING_ID)
            )
        )
        assert stored is not None
        stored.release_digest = "f" * 64
        await session.commit()

    with pytest.raises(GovernanceFindingReviewDependencyError):
        await SqlAlchemyGovernanceFindingReleaseVerifier(SessionFactory).was_released(
            finding_schema_version=envelope.schema_version,
            finding_id=FINDING_ID,
            finding_type=GovernanceFindingType.EVIDENCE_INTERPRETATION,
            agent_run_id=RUN_ID,
            candidate_digest=governance_finding_envelope_digest(envelope),
            subject_id=SUBJECT_ID,
            correlation_id=CORRELATION_ID,
        )
