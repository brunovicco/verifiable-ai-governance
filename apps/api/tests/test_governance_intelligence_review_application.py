"""Tests for durable non-authoritative Governance Intelligence review receipts."""

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from ai_governance_api import dependencies
from ai_governance_api.adapters import governance_intelligence_review_persistence
from ai_governance_api.application.governance_intelligence_review import (
    GovernanceFindingReviewAccess,
    GovernanceFindingReviewAuditRecord,
    GovernanceFindingReviewDependencyError,
    GovernanceFindingReviewDisposition,
    GovernanceFindingReviewError,
    GovernanceFindingReviewFailure,
    GovernanceFindingReviewReceipt,
    GovernanceFindingReviewWriteConflict,
    ReviewGovernanceFinding,
)
from ai_governance_api.database import SessionFactory
from ai_governance_api.models import (
    AuditEvent,
    GovernanceFindingReviewReceiptEntry,
)
from governance_schemas import (
    AgentRunProvenance,
    GovernanceFindingCandidate,
    GovernanceFindingEnvelope,
    GovernanceFindingType,
    GovernanceSourceReference,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

FINDING_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
REVIEW_ID = UUID("33333333-3333-4333-8333-333333333333")
REQUEST_ID = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
ACTOR_ID = "reviewer-1"
SUBJECT_ID = "initiative:55555555-5555-4555-8555-555555555555"
CORRELATION_ID = "corr:gi-3-review"
STATEMENT = "The verified source may require a separate governed risk assessment."


def finding(*, statement: str = STATEMENT) -> GovernanceFindingEnvelope:
    """Return one schema-valid advisory finding envelope."""
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


def access(
    *,
    actor_id: str = ACTOR_ID,
    subject_id: str = SUBJECT_ID,
    correlation_id: str = CORRELATION_ID,
    is_admin: bool = False,
) -> GovernanceFindingReviewAccess:
    """Return one bounded authenticated review context."""
    return GovernanceFindingReviewAccess(
        actor_id=actor_id,
        subject_id=subject_id,
        correlation_id=correlation_id,
        is_admin=is_admin,
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


class FakeStore:
    """Capture minimized receipt persistence and deterministic failures."""

    def __init__(
        self,
        *,
        fail_load: bool = False,
        fail_save: bool = False,
        write_conflict: bool = False,
        retain_conflict_winner: bool = True,
    ) -> None:
        self.fail_load = fail_load
        self.fail_save = fail_save
        self.write_conflict = write_conflict
        self.retain_conflict_winner = retain_conflict_winner
        self.existing: GovernanceFindingReviewReceipt | None = None
        self.get_calls: list[UUID] = []
        self.saved: list[GovernanceFindingReviewReceipt] = []

    async def get_by_request_id(
        self,
        request_id: UUID,
    ) -> GovernanceFindingReviewReceipt | None:
        self.get_calls.append(request_id)
        if self.fail_load:
            raise GovernanceFindingReviewDependencyError("store detail must not escape")
        if self.existing is None or self.existing.request_id != request_id:
            return None
        return self.existing

    async def save(self, receipt: GovernanceFindingReviewReceipt) -> None:
        if self.fail_save:
            raise GovernanceFindingReviewDependencyError("store detail must not escape")
        if self.write_conflict:
            self.write_conflict = False
            if self.retain_conflict_winner:
                self.existing = receipt
            raise GovernanceFindingReviewWriteConflict("constraint detail must not escape")
        self.saved.append(receipt)
        self.existing = receipt


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
    """Capture durable receipt commits and rollback cleanup."""

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
    store: FakeStore,
    audit: FakeAudit,
    transaction: FakeTransaction,
) -> ReviewGovernanceFinding:
    """Compose the review boundary with deterministic seams."""
    return ReviewGovernanceFinding(
        authorizer,
        store,
        audit,
        transaction,
        clock=lambda: NOW,
        id_factory=lambda: REVIEW_ID,
    )


async def execute(
    *,
    authorizer: FakeAuthorizer | None = None,
    store: FakeStore | None = None,
    audit: FakeAudit | None = None,
    transaction: FakeTransaction | None = None,
    request_id: UUID = REQUEST_ID,
    envelope: GovernanceFindingEnvelope | None = None,
    disposition: GovernanceFindingReviewDisposition = (
        GovernanceFindingReviewDisposition.ACCEPTED_FOR_CONSIDERATION
    ),
    review_access: GovernanceFindingReviewAccess | None = None,
) -> GovernanceFindingReviewReceipt:
    """Execute one deterministic advisory review for concise test setup."""
    return await use_case(
        authorizer or FakeAuthorizer(),
        store or FakeStore(),
        audit or FakeAudit(),
        transaction or FakeTransaction(),
    ).execute(
        request_id=request_id,
        finding=envelope or finding(),
        disposition=disposition,
        access=review_access or access(),
    )


@pytest.mark.parametrize("disposition", list(GovernanceFindingReviewDisposition))
async def test_authorized_review_returns_a_durable_non_authoritative_receipt(
    disposition: GovernanceFindingReviewDisposition,
) -> None:
    authorizer = FakeAuthorizer()
    store = FakeStore()
    audit = FakeAudit()
    transaction = FakeTransaction()

    receipt = await execute(
        authorizer=authorizer,
        store=store,
        audit=audit,
        transaction=transaction,
        disposition=disposition,
    )

    assert receipt.request_id == REQUEST_ID
    assert receipt.review_id == REVIEW_ID
    assert receipt.schema_version == "1.0"
    assert receipt.finding_schema_version == "1.0"
    assert receipt.finding_id == FINDING_ID
    assert receipt.agent_run_id == RUN_ID
    assert receipt.disposition is disposition
    assert receipt.reviewed_by == ACTOR_ID
    assert receipt.version == 1
    assert len(receipt.candidate_digest) == 64
    assert len(receipt.receipt_digest) == 64
    assert store.saved == [receipt]
    assert transaction.commits == 1
    assert transaction.rollbacks == 0
    actor_id, record = audit.records[0]
    assert actor_id == ACTOR_ID
    assert record.request_id == REQUEST_ID
    assert record.receipt_digest == receipt.receipt_digest
    assert STATEMENT not in repr(record)
    assert "deterministic-test-adapter" not in repr(record)


async def test_candidate_digest_binds_the_complete_revalidated_envelope() -> None:
    envelope = finding()
    expected = hashlib.sha256(
        json.dumps(
            envelope.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()

    receipt = await execute(envelope=envelope)

    assert receipt.candidate_digest == expected
    assert receipt.receipt_digest != receipt.candidate_digest


@pytest.mark.parametrize(
    "invalid_case",
    ["request_id", "correlation", "constructed", "disposition"],
)
async def test_invalid_review_input_fails_before_authorization_or_persistence(
    invalid_case: str,
) -> None:
    request_id = REQUEST_ID
    envelope = finding()
    review_access = access()
    disposition = GovernanceFindingReviewDisposition.REJECTED
    if invalid_case == "request_id":
        request_id = UUID(int=0)
    elif invalid_case == "correlation":
        review_access = access(correlation_id="corr:different")
    elif invalid_case == "constructed":
        envelope = envelope.model_copy(
            update={"candidate": envelope.candidate.model_copy(update={"advisory_only": False})}
        )
    else:
        disposition = cast(GovernanceFindingReviewDisposition, "approved")
    authorizer = FakeAuthorizer()
    store = FakeStore()

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await execute(
            authorizer=authorizer,
            store=store,
            request_id=request_id,
            envelope=envelope,
            disposition=disposition,
            review_access=review_access,
        )

    assert captured.value.reason is GovernanceFindingReviewFailure.INVALID_REQUEST
    assert authorizer.calls == []
    assert store.get_calls == []


async def test_authorization_denial_is_content_free_and_writes_no_receipt() -> None:
    store = FakeStore()
    audit = FakeAudit()

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await execute(authorizer=FakeAuthorizer(allowed=False), store=store, audit=audit)

    assert captured.value.reason is GovernanceFindingReviewFailure.FORBIDDEN
    assert STATEMENT not in str(captured.value)
    assert store.get_calls == []
    assert audit.records == []


async def test_replay_requires_fresh_authorization_before_loading_receipt() -> None:
    authorizer = FakeAuthorizer()
    store = FakeStore()
    first = await execute(authorizer=authorizer, store=store)
    authorizer.allowed = False

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await execute(authorizer=authorizer, store=store)

    assert captured.value.reason is GovernanceFindingReviewFailure.FORBIDDEN
    assert store.existing == first
    assert store.get_calls == [REQUEST_ID]


async def test_exact_replay_returns_the_same_receipt_without_second_write_or_audit() -> None:
    authorizer = FakeAuthorizer()
    store = FakeStore()
    audit = FakeAudit()
    transaction = FakeTransaction()
    service = use_case(authorizer, store, audit, transaction)

    first = await service.execute(
        request_id=REQUEST_ID,
        finding=finding(),
        disposition=GovernanceFindingReviewDisposition.DEFERRED,
        access=access(),
    )
    replay = await service.execute(
        request_id=REQUEST_ID,
        finding=finding(),
        disposition=GovernanceFindingReviewDisposition.DEFERRED,
        access=access(),
    )

    assert replay == first
    assert store.saved == [first]
    assert len(audit.records) == 1
    assert transaction.commits == 2
    assert transaction.rollbacks == 0
    assert len(authorizer.calls) == 2


@pytest.mark.parametrize("rebind", ["finding", "disposition", "actor", "subject", "admin"])
async def test_request_id_rebinding_fails_with_content_free_conflict(rebind: str) -> None:
    store = FakeStore()
    first_access = access()
    first_finding = finding()
    first_disposition = GovernanceFindingReviewDisposition.DEFERRED
    await execute(
        store=store,
        envelope=first_finding,
        disposition=first_disposition,
        review_access=first_access,
    )
    rebound_finding = first_finding
    rebound_disposition = first_disposition
    rebound_access = first_access
    if rebind == "finding":
        rebound_finding = finding(statement="A different advisory statement.")
    elif rebind == "disposition":
        rebound_disposition = GovernanceFindingReviewDisposition.REJECTED
    elif rebind == "actor":
        rebound_access = access(actor_id="another-reviewer")
    elif rebind == "subject":
        rebound_access = access(subject_id="initiative:another-subject")
    else:
        rebound_access = access(is_admin=True)

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await execute(
            store=store,
            envelope=rebound_finding,
            disposition=rebound_disposition,
            review_access=rebound_access,
        )

    assert captured.value.reason is GovernanceFindingReviewFailure.CONFLICT
    assert STATEMENT not in str(captured.value)


async def test_tampered_persisted_receipt_fails_closed_as_conflict() -> None:
    store = FakeStore()
    receipt = await execute(store=store)
    store.existing = replace(receipt, receipt_digest="f" * 64)

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await execute(store=store)

    assert captured.value.reason is GovernanceFindingReviewFailure.CONFLICT


async def test_concurrent_unique_winner_is_reloaded_as_exact_replay() -> None:
    store = FakeStore(write_conflict=True)
    transaction = FakeTransaction()

    receipt = await execute(store=store, transaction=transaction)

    assert receipt.request_id == REQUEST_ID
    assert store.saved == []
    assert store.get_calls == [REQUEST_ID, REQUEST_ID]
    assert transaction.rollbacks == 1
    assert transaction.commits == 1


async def test_concurrent_conflict_without_a_committed_winner_fails_closed() -> None:
    store = FakeStore(write_conflict=True, retain_conflict_winner=False)

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await execute(store=store)

    assert captured.value.reason is GovernanceFindingReviewFailure.CONFLICT


async def test_authorization_dependency_failure_is_bounded_without_persistence() -> None:
    store = FakeStore()

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await execute(authorizer=FakeAuthorizer(fail=True), store=store)

    assert captured.value.reason is GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
    assert "authorization detail" not in str(captured.value)
    assert store.get_calls == []


@pytest.mark.parametrize("failure", ["load", "save", "audit", "commit"])
async def test_persistence_failure_withholds_receipt_and_rolls_back(failure: str) -> None:
    store = FakeStore(fail_load=failure == "load", fail_save=failure == "save")
    audit = FakeAudit(fail=failure == "audit")
    transaction = FakeTransaction(fail_commit=failure == "commit")

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await execute(store=store, audit=audit, transaction=transaction)

    assert captured.value.reason is GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
    assert transaction.rollbacks == 1


async def test_cancellation_during_authorization_propagates_without_persistence() -> None:
    authorizer = FakeAuthorizer(block=True)
    store = FakeStore()
    task = asyncio.create_task(execute(authorizer=authorizer, store=store))
    await authorizer.started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert store.get_calls == []


async def test_cancellation_during_audit_propagates_and_rolls_back() -> None:
    audit = FakeAudit(block=True)
    transaction = FakeTransaction()
    task = asyncio.create_task(execute(audit=audit, transaction=transaction))
    await audit.started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert transaction.rollbacks == 1


async def test_composition_persists_receipt_and_audit_atomically_and_replays() -> None:
    service = dependencies.build_governance_finding_review(FakeAuthorizer())
    composition = vars(service)
    assert composition["_store"] is composition["_audit"]
    assert composition["_audit"] is composition["_transaction"]

    receipt = await service.execute(
        request_id=REQUEST_ID,
        finding=finding(),
        disposition=GovernanceFindingReviewDisposition.ACCEPTED_FOR_CONSIDERATION,
        access=access(),
    )
    replay = await service.execute(
        request_id=REQUEST_ID,
        finding=finding(),
        disposition=GovernanceFindingReviewDisposition.ACCEPTED_FOR_CONSIDERATION,
        access=access(),
    )
    async with SessionFactory() as session:
        stored = await session.scalar(
            select(GovernanceFindingReviewReceiptEntry).where(
                GovernanceFindingReviewReceiptEntry.request_id == str(REQUEST_ID)
            )
        )
        events = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "governance_intelligence.finding_reviewed",
                    AuditEvent.entity_id == str(receipt.review_id),
                )
            )
        ).all()

    assert replay == receipt
    assert stored is not None
    assert stored.review_id == str(receipt.review_id)
    assert stored.receipt_digest == receipt.receipt_digest
    assert len(events) == 1
    event = events[0]
    assert event.entity_type == "governance_intelligence_finding_review"
    assert event.entity_version == 1
    assert event.payload["request_id"] == str(REQUEST_ID)
    assert event.payload["candidate_digest"] == receipt.candidate_digest
    assert event.payload["receipt_digest"] == receipt.receipt_digest
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


async def test_composition_rolls_back_receipt_when_audit_append_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove the concrete unit rolls back an already-flushed receipt with its audit."""

    async def fail_audit(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise SQLAlchemyError("simulated audit append failure")

    monkeypatch.setattr(
        governance_intelligence_review_persistence,
        "append_audit_event",
        fail_audit,
    )
    service = dependencies.build_governance_finding_review(FakeAuthorizer())

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await service.execute(
            request_id=REQUEST_ID,
            finding=finding(),
            disposition=GovernanceFindingReviewDisposition.REJECTED,
            access=access(),
        )

    assert captured.value.reason is GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
    async with SessionFactory() as session:
        receipt = await session.scalar(
            select(GovernanceFindingReviewReceiptEntry).where(
                GovernanceFindingReviewReceiptEntry.request_id == str(REQUEST_ID)
            )
        )
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "governance_intelligence.finding_reviewed"
            )
        )
    assert receipt is None
    assert event is None


async def test_composition_rejects_a_tampered_persisted_receipt() -> None:
    """Require the concrete loader and replay boundary to verify stored evidence."""
    service = dependencies.build_governance_finding_review(FakeAuthorizer())
    await service.execute(
        request_id=REQUEST_ID,
        finding=finding(),
        disposition=GovernanceFindingReviewDisposition.DEFERRED,
        access=access(),
    )
    async with SessionFactory() as session:
        stored = await session.scalar(
            select(GovernanceFindingReviewReceiptEntry).where(
                GovernanceFindingReviewReceiptEntry.request_id == str(REQUEST_ID)
            )
        )
        assert stored is not None
        stored.receipt_digest = "f" * 64
        await session.commit()

    with pytest.raises(GovernanceFindingReviewError) as captured:
        await service.execute(
            request_id=REQUEST_ID,
            finding=finding(),
            disposition=GovernanceFindingReviewDisposition.DEFERRED,
            access=access(),
        )

    assert captured.value.reason is GovernanceFindingReviewFailure.CONFLICT
