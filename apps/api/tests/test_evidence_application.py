"""Unit tests for the fail-closed evidence upload pipeline."""

import hashlib
from datetime import UTC, datetime
from io import BytesIO

import pytest
from ai_governance_api.application.evidence import (
    EvidenceDependencyError,
    UploadEvidence,
)
from ai_governance_api.domain.evidence import (
    EvidenceActor,
    EvidenceKind,
    EvidenceRecord,
    InitiativeEvidenceContext,
    MalwareScanResult,
    ScanVerdict,
    StoredObject,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

FIXED_TIME = datetime(2026, 7, 31, 20, 0, tzinfo=UTC)


class BytesSource:
    """Bounded in-memory upload source."""

    def __init__(self, content: bytes, filename: str, content_type: str) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = BytesIO(content)

    async def read(self, size: int) -> bytes:
        return self._content.read(size)


class FakeEvidenceStore:
    """Capture evidence records for use-case assertions."""

    def __init__(self, *, fail_save: bool = False) -> None:
        self.initiative = InitiativeEvidenceContext("initiative-1", "owner-1")
        self.records: list[EvidenceRecord] = []
        self.fail_save = fail_save

    async def get_initiative(self, initiative_id: str) -> InitiativeEvidenceContext | None:
        return self.initiative if initiative_id == self.initiative.id else None

    async def list_for_initiative(self, initiative_id: str) -> list[EvidenceRecord]:
        return [record for record in self.records if record.initiative_id == initiative_id]

    async def save(self, record: EvidenceRecord) -> EvidenceRecord:
        if self.fail_save:
            raise RuntimeError("database failure")
        self.records.append(record)
        return record


class FakeScanner:
    """Return a configured scanner verdict or dependency failure."""

    def __init__(self, verdict: ScanVerdict = ScanVerdict.CLEAN, *, fail: bool = False) -> None:
        self.verdict = verdict
        self.fail = fail
        self.scanned = b""

    async def scan(self, content: BytesIO) -> MalwareScanResult:
        if self.fail:
            raise EvidenceDependencyError("scanner unavailable")
        self.scanned = content.read()
        return MalwareScanResult(verdict=self.verdict, scanner="test-scanner")


class FakeObjectStorage:
    """Capture immutable object operations."""

    def __init__(self) -> None:
        self.uploaded: dict[str, bytes] = {}
        self.deleted: list[StoredObject] = []

    async def put(
        self,
        *,
        key: str,
        content: BytesIO,
        content_type: str,
        size_bytes: int,
        sha256: str,
    ) -> StoredObject:
        del content_type, size_bytes, sha256
        self.uploaded[key] = content.read()
        return StoredObject("evidence", key, f"s3://evidence/{key}")

    async def delete(self, stored: StoredObject) -> None:
        self.deleted.append(stored)
        self.uploaded.pop(stored.key, None)


class FakeAudit:
    """Capture evidence audit records."""

    def __init__(self) -> None:
        self.records: list[EvidenceRecord] = []

    async def append(self, *, actor_id: str, record: EvidenceRecord) -> None:
        assert actor_id == record.supplied_by
        self.records.append(record)


class FakeTransaction:
    """Capture transaction outcomes."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def build_use_case(
    *,
    store: FakeEvidenceStore | None = None,
    scanner: FakeScanner | None = None,
    storage: FakeObjectStorage | None = None,
    transaction: FakeTransaction | None = None,
    max_bytes: int = 1024,
) -> tuple[UploadEvidence, FakeEvidenceStore, FakeScanner, FakeObjectStorage, FakeTransaction]:
    actual_store = store or FakeEvidenceStore()
    actual_scanner = scanner or FakeScanner()
    actual_storage = storage or FakeObjectStorage()
    actual_transaction = transaction or FakeTransaction()
    use_case = UploadEvidence(
        actual_store,
        actual_scanner,
        actual_storage,
        FakeAudit(),
        actual_transaction,
        max_bytes=max_bytes,
        allowed_content_types=frozenset({"application/json", "application/pdf"}),
        clock=lambda: FIXED_TIME,
        id_factory=lambda: "evidence-1",
    )
    return use_case, actual_store, actual_scanner, actual_storage, actual_transaction


async def test_clean_upload_hashes_scans_stores_and_commits() -> None:
    content = b'{"control": "GOV-EVD-001"}'
    use_case, store, scanner, storage, transaction = build_use_case()

    result = await use_case.execute(
        initiative_id="initiative-1",
        kind=EvidenceKind.SECURITY_TEST,
        source=BytesSource(content, "result.json", "application/json"),
        actor=EvidenceActor("owner-1"),
    )

    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.scan_status is ScanVerdict.CLEAN
    assert scanner.scanned == content
    assert storage.uploaded[result.storage.key] == content
    assert store.records == [result]
    assert transaction.committed


async def test_infected_or_unavailable_scan_fails_before_storage() -> None:
    infected_scanner = FakeScanner(ScanVerdict.INFECTED)
    use_case, _, _, storage, _ = build_use_case(scanner=infected_scanner)

    with pytest.raises(ApplicationError) as infected:
        await use_case.execute(
            initiative_id="initiative-1",
            kind=EvidenceKind.OTHER,
            source=BytesSource(b"%PDF-test", "test.pdf", "application/pdf"),
            actor=EvidenceActor("owner-1"),
        )
    assert infected.value.kind is ErrorKind.UNPROCESSABLE
    assert storage.uploaded == {}

    use_case, _, _, storage, _ = build_use_case(scanner=FakeScanner(fail=True))
    with pytest.raises(ApplicationError) as unavailable:
        await use_case.execute(
            initiative_id="initiative-1",
            kind=EvidenceKind.OTHER,
            source=BytesSource(b"%PDF-test", "test.pdf", "application/pdf"),
            actor=EvidenceActor("owner-1"),
        )
    assert unavailable.value.kind is ErrorKind.DEPENDENCY_UNAVAILABLE
    assert storage.uploaded == {}


async def test_size_type_and_owner_policies_are_enforced() -> None:
    use_case, _, scanner, storage, _ = build_use_case(max_bytes=4)
    with pytest.raises(ApplicationError) as too_large:
        await use_case.execute(
            initiative_id="initiative-1",
            kind=EvidenceKind.OTHER,
            source=BytesSource(b"12345", "test.pdf", "application/pdf"),
            actor=EvidenceActor("owner-1"),
        )
    assert too_large.value.kind is ErrorKind.PAYLOAD_TOO_LARGE

    with pytest.raises(ApplicationError) as forbidden:
        await use_case.execute(
            initiative_id="initiative-1",
            kind=EvidenceKind.OTHER,
            source=BytesSource(b"{}", "test.json", "application/json"),
            actor=EvidenceActor("another-user"),
        )
    assert forbidden.value.kind is ErrorKind.FORBIDDEN
    assert scanner.scanned == b""
    assert storage.uploaded == {}


async def test_database_failure_rolls_back_and_deletes_object() -> None:
    store = FakeEvidenceStore(fail_save=True)
    storage = FakeObjectStorage()
    transaction = FakeTransaction()
    use_case, _, _, _, _ = build_use_case(
        store=store,
        storage=storage,
        transaction=transaction,
    )

    with pytest.raises(RuntimeError, match="database failure"):
        await use_case.execute(
            initiative_id="initiative-1",
            kind=EvidenceKind.ASSESSMENT,
            source=BytesSource(b"{}", "assessment.json", "application/json"),
            actor=EvidenceActor("owner-1"),
        )

    assert transaction.rolled_back
    assert storage.uploaded == {}
    assert len(storage.deleted) == 1
