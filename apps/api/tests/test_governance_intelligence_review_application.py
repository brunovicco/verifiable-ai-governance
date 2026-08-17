"""Tests for the non-authoritative Governance Intelligence review boundary."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from ai_governance_api import dependencies
from ai_governance_api.application.governance_intelligence_review import (
    GovernanceFindingReviewAccess,
    GovernanceFindingReviewAuditRecord,
    GovernanceFindingReviewDependencyError,
    GovernanceFindingReviewDisposition,
    GovernanceFindingReviewError,
    GovernanceFindingReviewFailure,
    ReviewGovernanceFinding,
)
from ai_governance_api.database import SessionFactory
from ai_governance_api.models import AuditEvent
from governance_schemas import (
    AgentRunProvenance,
    GovernanceFindingCandidate,
    GovernanceFindingEnvelope,
    GovernanceFindingType,
    GovernanceSourceReference,
)
from sqlalchemy import select

FINDING_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
REVIEW_ID = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
ACTOR_ID = "reviewer-1"
SUBJECT_ID = "initiative:44444444-4444-4444-8444-444444444444"
CORRELATION_ID = "corr:gi-3-review"
STATEMENT = "The verified source may require a separate governed risk assessment."


def finding() -> GovernanceFindingEnvelope:
    """Return one schema-valid advisory finding envelope."""
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
            confidence=0.81,
            sources=(source,),
            provenance=AgentRunProvenance(
                agent_run_id=RUN_ID,
                agent_name="risk_mapper",
                provider="provider-neutral",
                model="deterministic-test-adapter",
                prompt_config_version="gi-3-test-v1",
                retrieved_sources=(source,),
                created_at=NOW,
                correlation_id=CORRELATION_ID,
            ),
        )
    )


def access(*, correlation_id: str = CORRELATION_ID) -> GovernanceFindingReviewAccess:
    """Return one bounded authenticated review context."""
    return GovernanceFindingReviewAccess(
        actor_id=ACTOR_ID,
        subject_id=SUBJECT_ID,
        correlation_id=correlation_id,
    )


class FakeAuthorizer:
    """Return one configured content-free review authorization decision."""

    def __init__(
        self,
        *,
        allowed: bool = True,
        fail: bool = False,
        block: bool = False,
    ) -> None:
        self.allowed = allowed
        self.fail = fail
        self.block = block
        self.started = asyncio.Event()
        self.calls: list[tuple[str, str, GovernanceFindingType, bool]] = []

    async def can_review(
        self,
        *,
        actor_id: str,
        subject_id: str,
        finding_type: GovernanceFindingType,
        is_admin: bool,
    ) -> bool:
        self.calls.append((actor_id, subject_id, finding_type, is_admin))
        self.started.set()
        if self.block:
            await asyncio.Event().wait()
        if self.fail:
            raise GovernanceFindingReviewDependencyError("authorization detail must not escape")
        return self.allowed


class FakeAudit:
    """Capture minimized review records and deterministic audit failures."""

    def __init__(self, *, fail: bool = False, block: bool = False) -> None:
        self.fail = fail
        self.block = block
        self.started = asyncio.Event()
        self.records: list[tuple[str, GovernanceFindingReviewAuditRecord]] = []

    async def append(
        self,
        *,
        actor_id: str,
        record: GovernanceFindingReviewAuditRecord,
    ) -> None:
        self.records.append((actor_id, record))
        self.started.set()
        if self.block:
            await asyncio.Event().wait()
        if self.fail:
            raise GovernanceFindingReviewDependencyError("audit detail must not escape")


class FakeTransaction:
    """Capture review receipt commits and rollback cleanup."""

    def __init__(self, *, fail_commit: bool = False) -> None:
        self.fail_commit = fail_commit
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1
        if self.fail_commit:
            raise GovernanceFindingReviewDependencyError("commit detail must not escape")

    async def rollback(self) -> None:
        self.rollbacks += 1


def use_case(
    authorizer: FakeAuthorizer,
    audit: FakeAudit,
    transaction: FakeTransaction,
) -> ReviewGovernanceFinding:
    """Compose the review boundary with deterministic seams."""
    return ReviewGovernanceFinding(
        authorizer,
        audit,
        transaction,
        clock=lambda: NOW,
        id_factory=lambda: REVIEW_ID,
    )


@pytest.mark.parametrize("disposition", list(GovernanceFindingReviewDisposition))
async def test_authorized_review_returns_only_a_non_authoritative_receipt_after_audit(
    disposition: GovernanceFindingReviewDisposition,
) -> None:
    authorizer = FakeAuthorizer()
    audit = FakeAudit()
    transaction = FakeTransaction()

    receipt = await use_case(authorizer, audit, transaction).execute(
        finding=finding(),
        disposition=disposition,
        access=access(),
    )

    assert receipt.review_id == REVIEW_ID
    assert receipt.finding_id == FINDING_ID
    assert receipt.agent_run_id == RUN_ID
    assert receipt.disposition is disposition
    assert receipt.reviewed_by == ACTOR_ID
    assert len(receipt.candidate_digest) == 64
    assert authorizer.calls == [(ACTOR_ID, SUBJECT_ID, GovernanceFindingType.RISK_CANDIDATE, False)]
    assert transaction.commits == 1
    assert transaction.rollbacks == 0
    actor_id, record = audit.records[0]
    assert actor_id == ACTOR_ID
    assert record.disposition is disposition
    assert record.candidate_digest == receipt.candidate_digest
    assert STATEMENT not in repr(record)
    assert "deterministic-test-adapter" not in repr(record)


async def test_review_digest_binds_the_complete_revalidated_envelope() -> None:
    envelope = finding()
    expected = hashlib.sha256(
        json.dumps(
            envelope.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()

    receipt = await use_case(FakeAuthorizer(), FakeAudit(), FakeTransaction()).execute(
        finding=envelope,
        disposition=GovernanceFindingReviewDisposition.DEFERRED,
        access=access(),
    )

    assert receipt.candidate_digest == expected


@pytest.mark.parametrize("invalid_case", ["correlation", "constructed", "disposition"])
async def test_invalid_review_input_fails_before_authorization_or_audit(
    invalid_case: str,
) -> None:
    envelope = finding()
    review_access = access()
    disposition = GovernanceFindingReviewDisposition.REJECTED
    if invalid_case == "correlation":
        review_access = access(correlation_id="corr:different")
    elif invalid_case == "constructed":
        envelope = envelope.model_copy(
            update={"candidate": envelope.candidate.model_copy(update={"advisory_only": False})}
        )
    else:
        disposition = cast(GovernanceFindingReviewDisposition, "approved")
    authorizer = FakeAuthorizer()
    audit = FakeAudit()
    transaction = FakeTransaction()

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await use_case(authorizer, audit, transaction).execute(
            finding=envelope,
            disposition=disposition,
            access=review_access,
        )

    assert captured.value.reason is GovernanceFindingReviewFailure.INVALID_REQUEST
    assert authorizer.calls == []
    assert audit.records == []
    assert transaction.commits == 0


async def test_authorization_denial_is_content_free_and_writes_no_receipt() -> None:
    authorizer = FakeAuthorizer(allowed=False)
    audit = FakeAudit()
    transaction = FakeTransaction()

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await use_case(authorizer, audit, transaction).execute(
            finding=finding(),
            disposition=GovernanceFindingReviewDisposition.ACCEPTED_FOR_CONSIDERATION,
            access=access(),
        )

    assert captured.value.reason is GovernanceFindingReviewFailure.FORBIDDEN
    assert STATEMENT not in str(captured.value)
    assert audit.records == []
    assert transaction.commits == 0


async def test_authorization_dependency_failure_is_bounded_without_audit() -> None:
    audit = FakeAudit()

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await use_case(
            FakeAuthorizer(fail=True),
            audit,
            FakeTransaction(),
        ).execute(
            finding=finding(),
            disposition=GovernanceFindingReviewDisposition.DEFERRED,
            access=access(),
        )

    assert captured.value.reason is GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
    assert "authorization detail" not in str(captured.value)
    assert audit.records == []


@pytest.mark.parametrize("failure", ["append", "commit"])
async def test_audit_failure_withholds_receipt_and_rolls_back(failure: str) -> None:
    audit = FakeAudit(fail=failure == "append")
    transaction = FakeTransaction(fail_commit=failure == "commit")

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await use_case(FakeAuthorizer(), audit, transaction).execute(
            finding=finding(),
            disposition=GovernanceFindingReviewDisposition.REJECTED,
            access=access(),
        )

    assert captured.value.reason is GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
    assert transaction.rollbacks == 1


async def test_cancellation_during_authorization_propagates_without_audit() -> None:
    authorizer = FakeAuthorizer(block=True)
    audit = FakeAudit()
    task = asyncio.create_task(
        use_case(authorizer, audit, FakeTransaction()).execute(
            finding=finding(),
            disposition=GovernanceFindingReviewDisposition.DEFERRED,
            access=access(),
        )
    )
    await authorizer.started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert audit.records == []


async def test_cancellation_during_audit_propagates_and_rolls_back() -> None:
    audit = FakeAudit(block=True)
    transaction = FakeTransaction()
    task = asyncio.create_task(
        use_case(FakeAuthorizer(), audit, transaction).execute(
            finding=finding(),
            disposition=GovernanceFindingReviewDisposition.DEFERRED,
            access=access(),
        )
    )
    await audit.started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert transaction.rollbacks == 1


async def test_composition_root_persists_only_the_minimized_review_receipt() -> None:
    service = dependencies.build_governance_finding_review(FakeAuthorizer())
    composition = vars(service)
    assert composition["_audit"] is composition["_transaction"]

    receipt = await service.execute(
        finding=finding(),
        disposition=GovernanceFindingReviewDisposition.ACCEPTED_FOR_CONSIDERATION,
        access=access(),
    )
    async with SessionFactory() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "governance_intelligence.finding_reviewed",
                AuditEvent.entity_id == str(receipt.review_id),
            )
        )

    assert event is not None
    assert event.entity_type == "governance_intelligence_finding_review"
    assert event.entity_version == 1
    assert event.payload["candidate_digest"] == receipt.candidate_digest
    assert event.payload["disposition"] == "accepted_for_consideration"
    serialized = json.dumps(event.payload, sort_keys=True)
    assert STATEMENT not in serialized
    assert "confidence" not in serialized
    assert "sources" not in serialized
    assert "provider-neutral" not in serialized
    assert "deterministic-test-adapter" not in serialized
    assert "prompt" not in serialized
    assert "chain_of_thought" not in serialized
    assert "storage_bucket" not in serialized
    assert "storage_key" not in serialized
