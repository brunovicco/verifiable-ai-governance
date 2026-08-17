"""Tests for initiative-scoped advisory finding review authorization."""

import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from ai_governance_api import dependencies
from ai_governance_api.adapters import SqlAlchemyInitiativeFindingReviewAuthorizer
from ai_governance_api.application.governance_intelligence_review import (
    GovernanceFindingReviewAccess,
    GovernanceFindingReviewDependencyError,
    GovernanceFindingReviewDisposition,
    GovernanceFindingReviewError,
    GovernanceFindingReviewFailure,
)
from ai_governance_api.database import SessionFactory
from ai_governance_api.models import AuditEvent, Initiative
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
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

INITIATIVE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
MISSING_INITIATIVE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
FINDING_ID = UUID("33333333-3333-4333-8333-333333333333")
RUN_ID = UUID("44444444-4444-4444-8444-444444444444")
REVIEW_REQUEST_ID = UUID("77777777-7777-4777-8777-777777777777")
OWNER_ID = "initiative-owner"
ADMIN_ID = "governance-admin"
CORRELATION_ID = "corr:gi-3a-review"
NOW = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
STATEMENT = "The source may warrant a separately governed risk decision."


async def _persist_initiative() -> None:
    """Persist one governed initiative with a stable owner identity."""
    async with SessionFactory() as session:
        session.add(
            Initiative(
                id=INITIATIVE_ID,
                name="GI-3A authorization fixture",
                description="Tests the advisory review authorization boundary.",
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
    """Return one valid advisory envelope bound to the test correlation."""
    source = GovernanceSourceReference(
        artifact_id="evidence:55555555-5555-4555-8555-555555555555",
        version="1",
        content_digest="a" * 64,
    )
    return GovernanceFindingEnvelope(
        candidate=GovernanceFindingCandidate(
            finding_id=FINDING_ID,
            finding_type=GovernanceFindingType.RISK_CANDIDATE,
            statement=STATEMENT,
            confidence=0.75,
            sources=(source,),
            provenance=AgentRunProvenance(
                agent_run_id=RUN_ID,
                agent_name="risk_mapper",
                provider="provider-neutral",
                model="test-adapter",
                prompt_config_version="gi-3a-test-v1",
                retrieved_sources=(source,),
                created_at=NOW,
                correlation_id=CORRELATION_ID,
            ),
        )
    )


@pytest.mark.parametrize("finding_type", list(GovernanceFindingType))
@pytest.mark.parametrize(
    ("actor_id", "is_admin"),
    [(OWNER_ID, False), (ADMIN_ID, True)],
)
async def test_existing_initiative_owner_or_admin_can_review_every_advisory_type(
    actor_id: str,
    is_admin: bool,
    finding_type: GovernanceFindingType,
) -> None:
    """Finding taxonomy must not expand or narrow the owner/admin policy."""
    await _persist_initiative()
    authorizer = SqlAlchemyInitiativeFindingReviewAuthorizer(SessionFactory)

    assert await authorizer.can_review(
        actor_id=actor_id,
        subject_id=INITIATIVE_ID,
        finding_type=finding_type,
        is_admin=is_admin,
    )


@pytest.mark.parametrize("finding_type", list(GovernanceFindingType))
async def test_unrelated_actor_is_denied_for_every_advisory_type(
    finding_type: GovernanceFindingType,
) -> None:
    """A finding type is context, never an authorization role."""
    await _persist_initiative()
    authorizer = SqlAlchemyInitiativeFindingReviewAuthorizer(SessionFactory)

    assert not await authorizer.can_review(
        actor_id="unrelated-reviewer",
        subject_id=INITIATIVE_ID,
        finding_type=finding_type,
        is_admin=False,
    )


@pytest.mark.parametrize(
    "subject_id",
    [
        MISSING_INITIATIVE_ID,
        f"initiative:{INITIATIVE_ID}",
        INITIATIVE_ID.upper(),
        "00000000-0000-0000-0000-000000000000",
        "not-an-initiative-id",
    ],
)
async def test_absent_or_noncanonical_subject_is_denied(subject_id: str) -> None:
    """Missing subjects and aliases produce the same closed authorization decision."""
    await _persist_initiative()
    authorizer = SqlAlchemyInitiativeFindingReviewAuthorizer(SessionFactory)

    assert not await authorizer.can_review(
        actor_id=ADMIN_ID,
        subject_id=subject_id,
        finding_type=GovernanceFindingType.EVIDENCE_GAP,
        is_admin=True,
    )


class _RecordingSession:
    """Minimal async-session seam recording acquisition and release."""

    def __init__(self, *, owner_id: str | None = OWNER_ID, fail: bool = False) -> None:
        self.owner_id = owner_id
        self.fail = fail
        self.entered = False
        self.exited = False
        self.scalar_calls = 0

    async def __aenter__(self) -> "_RecordingSession":
        self.entered = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        self.exited = True

    async def scalar(self, statement: object) -> str | None:
        self.scalar_calls += 1
        if self.fail:
            raise SQLAlchemyError("database coordinates must not escape")
        assert "initiatives.business_owner_id" in str(statement)
        assert "initiatives.name" not in str(statement)
        assert "initiatives.description" not in str(statement)
        return self.owner_id


class _RecordingSessionFactory:
    """Return the same recording session for one authorization request."""

    def __init__(self, session: _RecordingSession) -> None:
        self.session = session
        self.calls = 0

    def __call__(self) -> _RecordingSession:
        self.calls += 1
        return self.session


def _recording_authorizer(
    session: _RecordingSession,
) -> tuple[SqlAlchemyInitiativeFindingReviewAuthorizer, _RecordingSessionFactory]:
    """Build the concrete adapter over a minimal lifecycle seam."""
    factory = _RecordingSessionFactory(session)
    return (
        SqlAlchemyInitiativeFindingReviewAuthorizer(
            cast(async_sessionmaker[AsyncSession], factory)
        ),
        factory,
    )


async def test_authorization_uses_one_short_lived_minimal_read_session() -> None:
    """The ownership read closes before the separate review audit transaction begins."""
    session = _RecordingSession()
    authorizer, factory = _recording_authorizer(session)

    assert await authorizer.can_review(
        actor_id=OWNER_ID,
        subject_id=INITIATIVE_ID,
        finding_type=GovernanceFindingType.CONTROL_CANDIDATE,
        is_admin=False,
    )
    assert factory.calls == 1
    assert session.scalar_calls == 1
    assert session.entered
    assert session.exited


async def test_database_failure_is_content_free_and_releases_the_session() -> None:
    """Infrastructure details are bounded by the review dependency contract."""
    session = _RecordingSession(fail=True)
    authorizer, _ = _recording_authorizer(session)

    with pytest.raises(GovernanceFindingReviewDependencyError) as captured:
        await authorizer.can_review(
            actor_id=OWNER_ID,
            subject_id=INITIATIVE_ID,
            finding_type=GovernanceFindingType.INTAKE_SUGGESTION,
            is_admin=False,
        )

    assert "database coordinates" not in str(captured.value)
    assert session.exited


@pytest.mark.parametrize(
    ("actor_id", "is_admin"),
    [(OWNER_ID, False), (ADMIN_ID, True)],
)
async def test_initiative_composition_records_only_an_authorized_minimized_receipt(
    actor_id: str,
    is_admin: bool,
) -> None:
    """The concrete policy composes with the GI-3 audit without delivery exposure."""
    await _persist_initiative()
    service = dependencies.build_initiative_governance_finding_review()

    receipt = await service.execute(
        request_id=REVIEW_REQUEST_ID,
        finding=_finding(),
        disposition=GovernanceFindingReviewDisposition.ACCEPTED_FOR_CONSIDERATION,
        access=GovernanceFindingReviewAccess(
            actor_id=actor_id,
            subject_id=INITIATIVE_ID,
            correlation_id=CORRELATION_ID,
            is_admin=is_admin,
        ),
    )
    async with SessionFactory() as session:
        event = await session.scalar(
            select(AuditEvent).where(AuditEvent.entity_id == str(receipt.review_id))
        )

    assert event is not None
    assert event.action == "governance_intelligence.finding_reviewed"
    assert event.payload["subject_id"] == INITIATIVE_ID
    assert event.payload["administrator_access"] is is_admin
    serialized = json.dumps(event.payload, sort_keys=True)
    assert STATEMENT not in serialized
    assert "confidence" not in serialized
    assert "sources" not in serialized


async def test_concrete_authorization_denial_writes_no_review_receipt() -> None:
    """An unrelated actor cannot create audit evidence implying a completed review."""
    await _persist_initiative()
    service = dependencies.build_initiative_governance_finding_review()

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await service.execute(
            request_id=REVIEW_REQUEST_ID,
            finding=_finding(),
            disposition=GovernanceFindingReviewDisposition.REJECTED,
            access=GovernanceFindingReviewAccess(
                actor_id="unrelated-reviewer",
                subject_id=INITIATIVE_ID,
                correlation_id=CORRELATION_ID,
            ),
        )

    assert captured.value.reason is GovernanceFindingReviewFailure.FORBIDDEN
    async with SessionFactory() as session:
        events = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "governance_intelligence.finding_reviewed"
                )
            )
        ).all()
    assert events == []
