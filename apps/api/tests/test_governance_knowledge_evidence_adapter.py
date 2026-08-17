"""Tests for the verified private-evidence Governance Knowledge adapter."""

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import pytest
from ai_governance_api.adapters.evidence_persistence import SqlAlchemyEvidenceStore
from ai_governance_api.adapters.governance_knowledge_evidence import (
    VerifiedEvidenceKnowledgeAdapter,
    governance_reference_for_evidence,
)
from ai_governance_api.adapters.object_storage import S3ObjectStorage
from ai_governance_api.application.evidence import EvidenceDependencyError
from ai_governance_api.application.governance_knowledge import (
    GovernanceKnowledgeAccess,
    GovernanceKnowledgeFailure,
    GovernanceKnowledgeResolutionError,
    ResolveGovernanceKnowledgeSources,
)
from ai_governance_api.database import SessionFactory
from ai_governance_api.domain.evidence import (
    EvidenceKind,
    EvidenceRecord,
    InitiativeEvidenceContext,
    ScanVerdict,
    StoredObject,
)
from ai_governance_api.models import Evidence
from governance_schemas import GovernanceSourceReference
from sqlalchemy.exc import SQLAlchemyError

EVIDENCE_ID = "11111111-1111-4111-8111-111111111111"
INITIATIVE_ID = "22222222-2222-4222-8222-222222222222"
CONTENT = b'{"control": "GOV-EVD-001", "passed": true}'
NOW = datetime(2026, 8, 17, 4, 0, tzinfo=UTC)


def evidence_record(
    *,
    evidence_id: str = EVIDENCE_ID,
    scan_status: ScanVerdict = ScanVerdict.CLEAN,
    version: int = 1,
    storage: StoredObject | None = None,
) -> EvidenceRecord:
    """Return one clean, immutable private upload with canonical storage metadata."""
    return EvidenceRecord(
        id=evidence_id,
        initiative_id=INITIATIVE_ID,
        kind=EvidenceKind.SECURITY_TEST,
        original_filename="control-result.json",
        content_type="application/json",
        size_bytes=len(CONTENT),
        sha256=hashlib.sha256(CONTENT).hexdigest(),
        scan_status=scan_status,
        scanner="test-scanner",
        scanned_at=NOW,
        storage=storage
        or StoredObject(
            bucket="governance-evidence",
            key=f"evidence/{INITIATIVE_ID}/{evidence_id}",
            uri=f"s3://governance-evidence/evidence/{INITIATIVE_ID}/{evidence_id}",
        ),
        supplied_by="owner-1",
        version=version,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeEvidenceStore:
    """Return configured initiative and upload metadata without infrastructure."""

    def __init__(
        self,
        record: EvidenceRecord | None,
        *,
        owner_id: str = "owner-1",
        fail_initiative: bool = False,
        fail_evidence: bool = False,
    ) -> None:
        self.record = record
        self.initiative = InitiativeEvidenceContext(INITIATIVE_ID, owner_id)
        self.fail_initiative = fail_initiative
        self.fail_evidence = fail_evidence
        self.initiative_calls: list[str] = []
        self.evidence_calls: list[tuple[str, str]] = []

    async def get_initiative(self, initiative_id: str) -> InitiativeEvidenceContext | None:
        self.initiative_calls.append(initiative_id)
        if self.fail_initiative:
            raise SQLAlchemyError("initiative lookup failed")
        return self.initiative if initiative_id == self.initiative.id else None

    async def get_uploaded(
        self,
        evidence_id: str,
        initiative_id: str,
    ) -> EvidenceRecord | None:
        self.evidence_calls.append((evidence_id, initiative_id))
        if self.fail_evidence:
            raise SQLAlchemyError("evidence lookup failed")
        return (
            self.record
            if self.record is not None
            and evidence_id == self.record.id
            and initiative_id == self.record.initiative_id
            else None
        )


class MemoryEvidenceContent:
    """Expose private evidence bytes and deterministic dependency failures."""

    def __init__(
        self,
        content: bytes,
        *,
        fail_read: bool = False,
        fail_close: bool = False,
    ) -> None:
        self._content = BytesIO(content)
        self.fail_read = fail_read
        self.fail_close = fail_close
        self.closed = False

    async def read(self, size: int) -> bytes:
        if self.fail_read:
            raise EvidenceDependencyError("private read failed")
        return self._content.read(size)

    async def close(self) -> None:
        self.closed = True
        if self.fail_close:
            raise EvidenceDependencyError("private close failed")


class FakeObjectReader:
    """Open one configured private object without exposing it to the caller."""

    def __init__(
        self,
        content: MemoryEvidenceContent,
        *,
        fail_open: bool = False,
    ) -> None:
        self.content = content
        self.fail_open = fail_open
        self.opened: list[StoredObject] = []

    async def open(self, stored: StoredObject) -> MemoryEvidenceContent:
        self.opened.append(stored)
        if self.fail_open:
            raise EvidenceDependencyError("private object unavailable")
        return self.content


def access(
    *,
    actor_id: str = "owner-1",
    subject_id: str = INITIATIVE_ID,
    correlation_id: str = "corr:gi-1a-test",
    is_admin: bool = False,
) -> GovernanceKnowledgeAccess:
    """Return one authenticated source-access context."""
    return GovernanceKnowledgeAccess(
        actor_id=actor_id,
        subject_id=subject_id,
        correlation_id=correlation_id,
        is_admin=is_admin,
    )


def build_gate(
    record: EvidenceRecord | None,
    object_reader: FakeObjectReader,
    *,
    owner_id: str = "owner-1",
    fail_initiative: bool = False,
    fail_evidence: bool = False,
) -> tuple[ResolveGovernanceKnowledgeSources, VerifiedEvidenceKnowledgeAdapter, FakeEvidenceStore]:
    """Compose the real adapter on both sides of the deterministic GI-1 gate."""
    store = FakeEvidenceStore(
        record,
        owner_id=owner_id,
        fail_initiative=fail_initiative,
        fail_evidence=fail_evidence,
    )
    adapter = VerifiedEvidenceKnowledgeAdapter(store, object_reader)
    gate = ResolveGovernanceKnowledgeSources(
        adapter,
        adapter,
        max_sources=2,
        max_source_bytes=1024,
        max_total_bytes=2048,
    )
    return gate, adapter, store


async def test_owner_resolves_exact_verified_upload_through_the_full_gate() -> None:
    record = evidence_record()
    reference = governance_reference_for_evidence(record)
    content = MemoryEvidenceContent(CONTENT)
    reader = FakeObjectReader(content)
    gate, _, store = build_gate(record, reader)

    result = await gate.execute(references=(reference,), access=access())

    assert result[0].reference == reference
    assert result[0].content == CONTENT
    assert result[0].content_type == "application/json"
    assert store.initiative_calls == [INITIATIVE_ID]
    assert store.evidence_calls == [(EVIDENCE_ID, INITIATIVE_ID)]
    assert reader.opened == [record.storage]
    assert content.closed
    assert record.storage.key not in repr(result[0])


async def test_authenticated_administrator_can_resolve_another_owners_source() -> None:
    record = evidence_record()
    reference = governance_reference_for_evidence(record)
    gate, _, _ = build_gate(record, FakeObjectReader(MemoryEvidenceContent(CONTENT)))

    result = await gate.execute(
        references=(reference,),
        access=access(actor_id="governance-admin", is_admin=True),
    )

    assert result[0].content == CONTENT


@pytest.mark.parametrize(
    "source_access",
    [
        access(actor_id="another-user"),
        access(subject_id="33333333-3333-4333-8333-333333333333"),
    ],
)
async def test_non_owner_or_wrong_subject_is_denied_before_object_storage(
    source_access: GovernanceKnowledgeAccess,
) -> None:
    record = evidence_record()
    reference = governance_reference_for_evidence(record)
    reader = FakeObjectReader(MemoryEvidenceContent(CONTENT))
    gate, _, store = build_gate(record, reader)

    with pytest.raises(GovernanceKnowledgeResolutionError) as captured:
        await gate.execute(references=(reference,), access=source_access)

    assert captured.value.reason is GovernanceKnowledgeFailure.SOURCE_UNAVAILABLE
    assert reader.opened == []
    if source_access.actor_id != "owner-1":
        assert store.evidence_calls == []


@pytest.mark.parametrize(
    "reference_update",
    [
        {"artifact_id": f"document:{EVIDENCE_ID}"},
        {"artifact_id": "evidence:AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"},
        {"version": "2"},
        {"content_digest": "f" * 64},
        {"node_id": "page:1"},
        {"section": "1"},
    ],
)
async def test_noncanonical_or_mismatched_reference_is_not_resolved(
    reference_update: dict[str, object],
) -> None:
    record = evidence_record()
    reference = governance_reference_for_evidence(record).model_copy(update=reference_update)
    reader = FakeObjectReader(MemoryEvidenceContent(CONTENT))
    gate, _, _ = build_gate(record, reader)

    with pytest.raises(GovernanceKnowledgeResolutionError) as captured:
        await gate.execute(references=(reference,), access=access())

    assert captured.value.reason is GovernanceKnowledgeFailure.SOURCE_UNAVAILABLE
    assert reader.opened == []


@pytest.mark.parametrize(
    "record",
    [
        evidence_record(scan_status=ScanVerdict.INFECTED),
        evidence_record(version=0),
        evidence_record(
            storage=StoredObject(
                "governance-evidence",
                "evidence/another-initiative/another-object",
                "s3://governance-evidence/evidence/another-initiative/another-object",
            )
        ),
    ],
)
async def test_ineligible_or_noncanonical_evidence_metadata_fails_closed(
    record: EvidenceRecord,
) -> None:
    valid_record = evidence_record()
    reference = governance_reference_for_evidence(valid_record)
    reader = FakeObjectReader(MemoryEvidenceContent(CONTENT))
    gate, _, _ = build_gate(record, reader)

    with pytest.raises(GovernanceKnowledgeResolutionError) as captured:
        await gate.execute(references=(reference,), access=access())

    assert captured.value.reason is GovernanceKnowledgeFailure.SOURCE_UNAVAILABLE
    assert reader.opened == []


async def test_resolver_requires_prior_authorization_on_the_same_adapter_context() -> None:
    record = evidence_record()
    reference = governance_reference_for_evidence(record)
    reader = FakeObjectReader(MemoryEvidenceContent(CONTENT))
    _, adapter, _ = build_gate(record, reader)

    unresolved = await adapter.resolve(reference=reference, access=access())
    assert unresolved is None
    assert reader.opened == []

    assert await adapter.can_read(reference=reference, access=access())
    changed_context = access(correlation_id="corr:another-run")
    assert await adapter.resolve(reference=reference, access=changed_context) is None
    assert reader.opened == []


async def test_corrupted_private_bytes_fail_the_application_digest_gate() -> None:
    record = evidence_record()
    reference = governance_reference_for_evidence(record)
    content = MemoryEvidenceContent(b'{"tampered": true}')
    gate, _, _ = build_gate(record, FakeObjectReader(content))

    with pytest.raises(GovernanceKnowledgeResolutionError) as captured:
        await gate.execute(references=(reference,), access=access())

    assert captured.value.reason is GovernanceKnowledgeFailure.INTEGRITY_MISMATCH
    assert content.closed


@pytest.mark.parametrize("stage", ["open", "read", "close"])
async def test_storage_failures_map_to_content_free_dependency_errors(stage: str) -> None:
    record = evidence_record()
    reference = governance_reference_for_evidence(record)
    content = MemoryEvidenceContent(
        CONTENT,
        fail_read=stage == "read",
        fail_close=stage == "close",
    )
    gate, _, _ = build_gate(
        record,
        FakeObjectReader(content, fail_open=stage == "open"),
    )

    with pytest.raises(GovernanceKnowledgeResolutionError) as captured:
        await gate.execute(references=(reference,), access=access())

    assert captured.value.reason is GovernanceKnowledgeFailure.DEPENDENCY_UNAVAILABLE
    assert EVIDENCE_ID not in str(captured.value)
    assert record.storage.key not in str(captured.value)


@pytest.mark.parametrize("stage", ["initiative", "evidence"])
async def test_metadata_dependency_failures_are_content_free(stage: str) -> None:
    record = evidence_record()
    reference = governance_reference_for_evidence(record)
    gate, _, _ = build_gate(
        record,
        FakeObjectReader(MemoryEvidenceContent(CONTENT)),
        fail_initiative=stage == "initiative",
        fail_evidence=stage == "evidence",
    )

    with pytest.raises(GovernanceKnowledgeResolutionError) as captured:
        await gate.execute(references=(reference,), access=access())

    assert captured.value.reason is GovernanceKnowledgeFailure.DEPENDENCY_UNAVAILABLE
    assert EVIDENCE_ID not in str(captured.value)


def test_reference_factory_emits_only_canonical_content_free_identity() -> None:
    record = evidence_record()

    reference = governance_reference_for_evidence(record)

    assert reference == GovernanceSourceReference(
        artifact_id=f"evidence:{EVIDENCE_ID}",
        version="1",
        content_digest=record.sha256,
    )
    assert record.original_filename not in repr(reference)
    assert record.storage.key not in repr(reference)


@pytest.mark.parametrize(
    "record",
    [
        evidence_record(evidence_id="not-a-uuid"),
        evidence_record(evidence_id="00000000-0000-0000-0000-000000000000"),
        evidence_record(scan_status=ScanVerdict.INFECTED),
        evidence_record(version=0),
        evidence_record(
            storage=StoredObject(
                "governance-evidence",
                "evidence/another-initiative/another-object",
                "s3://governance-evidence/evidence/another-initiative/another-object",
            )
        ),
    ],
)
def test_reference_factory_rejects_ineligible_records(record: EvidenceRecord) -> None:
    with pytest.raises(ValueError, match="not eligible"):
        governance_reference_for_evidence(record)


class FakeS3Body:
    """Synchronous streaming body used by the boto3 adapter boundary."""

    def __init__(
        self,
        content: bytes,
        *,
        fail_read: bool = False,
        fail_close: bool = False,
    ) -> None:
        self._content = BytesIO(content)
        self.fail_read = fail_read
        self.fail_close = fail_close
        self.closed = False

    def read(self, size: int) -> bytes:
        if self.fail_read:
            raise OSError("S3 read failed")
        return self._content.read(size)

    def close(self) -> None:
        self.closed = True
        if self.fail_close:
            raise OSError("S3 close failed")


class FakeS3Client:
    """Capture exact private object reads without network access."""

    def __init__(
        self,
        body: FakeS3Body | None,
        *,
        fail_get: bool = False,
    ) -> None:
        self.body = body
        self.fail_get = fail_get
        self.gets: list[tuple[str, str]] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.gets.append((Bucket, Key))
        if self.fail_get:
            raise OSError("S3 get failed")
        return {"Body": self.body}


def s3_storage(client: FakeS3Client) -> S3ObjectStorage:
    """Build the real S3 adapter around a deterministic client."""
    return S3ObjectStorage(
        bucket="governance-evidence",
        region="us-east-1",
        endpoint_url="https://storage.example.com",
        access_key="",
        secret_key="",
        auto_create_bucket=False,
        server_side_encryption="AES256",
        connect_timeout_seconds=1,
        read_timeout_seconds=2,
        client=client,
    )


async def test_s3_reader_opens_exact_bucket_and_key_and_closes_body() -> None:
    body = FakeS3Body(CONTENT)
    client = FakeS3Client(body)
    storage = s3_storage(client)
    stored = evidence_record().storage

    content = await storage.open(stored)
    assert await content.read(8) == CONTENT[:8]
    await content.close()
    await content.close()

    assert client.gets == [(stored.bucket, stored.key)]
    assert body.closed


async def test_s3_reader_rejects_bucket_substitution_before_network() -> None:
    client = FakeS3Client(FakeS3Body(CONTENT))
    storage = s3_storage(client)
    stored = replace(evidence_record().storage, bucket="attacker-bucket")

    with pytest.raises(EvidenceDependencyError, match="bucket mismatch"):
        await storage.open(stored)

    assert client.gets == []


@pytest.mark.parametrize("failure", ["get", "body", "read", "close"])
async def test_s3_reader_maps_transport_and_body_failures(failure: str) -> None:
    body = FakeS3Body(
        CONTENT,
        fail_read=failure == "read",
        fail_close=failure == "close",
    )
    client = FakeS3Client(None if failure == "body" else body, fail_get=failure == "get")
    storage = s3_storage(client)

    if failure in {"get", "body"}:
        with pytest.raises(EvidenceDependencyError):
            await storage.open(evidence_record().storage)
        return

    content = await storage.open(evidence_record().storage)
    if failure == "read":
        with pytest.raises(EvidenceDependencyError, match="read failed"):
            await content.read(8)
    else:
        with pytest.raises(EvidenceDependencyError, match="close failed"):
            await content.close()


def test_knowledge_limit_configuration_is_fail_closed() -> None:
    from ai_governance_api.config import Settings

    with pytest.raises(ValueError, match="MAX_TOTAL_BYTES"):
        Settings(
            governance_knowledge_max_source_bytes=1024,
            governance_knowledge_max_total_bytes=512,
        )


async def test_persistence_reader_returns_only_clean_trusted_private_uploads() -> None:
    clean_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    untrusted_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    infected_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    external_id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    incomplete_id = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"

    def entity(
        evidence_id: str,
        *,
        trusted_source: bool = True,
        scan_status: str = "clean",
        storage_key: str | None = None,
    ) -> Evidence:
        key = storage_key or f"evidence/{INITIATIVE_ID}/{evidence_id}"
        return Evidence(
            id=evidence_id,
            initiative_id=INITIATIVE_ID,
            approval_id=None,
            kind=EvidenceKind.SECURITY_TEST.value,
            uri=f"s3://governance-evidence/{key}",
            sha256=hashlib.sha256(CONTENT).hexdigest(),
            metadata_json={},
            supplied_by="owner-1",
            trusted_source=trusted_source,
            original_filename="control-result.json",
            content_type="application/json",
            size_bytes=len(CONTENT),
            scan_status=scan_status,
            scanner="test-scanner",
            scanned_at=NOW,
            storage_bucket="governance-evidence" if storage_key is not None else None,
            storage_key=storage_key,
            version=1,
            created_at=NOW,
            updated_at=NOW,
        )

    async with SessionFactory() as session:
        incomplete = entity(
            incomplete_id,
            storage_key=f"evidence/{INITIATIVE_ID}/{incomplete_id}",
        )
        incomplete.storage_bucket = None
        session.add_all(
            [
                entity(
                    clean_id,
                    storage_key=f"evidence/{INITIATIVE_ID}/{clean_id}",
                ),
                entity(
                    untrusted_id,
                    trusted_source=False,
                    storage_key=f"evidence/{INITIATIVE_ID}/{untrusted_id}",
                ),
                entity(
                    infected_id,
                    scan_status="infected",
                    storage_key=f"evidence/{INITIATIVE_ID}/{infected_id}",
                ),
                entity(external_id),
                incomplete,
            ]
        )
        await session.commit()
        store = SqlAlchemyEvidenceStore(session)

        clean = await store.get_uploaded(clean_id, INITIATIVE_ID)
        assert clean is not None
        assert clean.id == clean_id
        assert await store.get_uploaded(clean_id, "another-initiative") is None
        assert await store.get_uploaded(untrusted_id, INITIATIVE_ID) is None
        assert await store.get_uploaded(infected_id, INITIATIVE_ID) is None
        assert await store.get_uploaded(external_id, INITIATIVE_ID) is None
        assert await store.get_uploaded(incomplete_id, INITIATIVE_ID) is None
