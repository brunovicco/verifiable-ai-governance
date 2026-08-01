"""Secure evidence upload use cases and consumer-owned ports."""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from tempfile import SpooledTemporaryFile
from typing import Protocol
from uuid import uuid4

from ai_governance_api.domain.evidence import (
    EvidenceActor,
    EvidenceDomainError,
    EvidenceKind,
    EvidenceRecord,
    InitiativeEvidenceContext,
    MalwareScanResult,
    ScanVerdict,
    StoredObject,
    normalize_filename,
    validate_content,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


class EvidenceDependencyError(RuntimeError):
    """Raised when a mandatory scanner or storage dependency is unavailable."""


class EvidenceSource(Protocol):
    """Asynchronous upload stream consumed without depending on FastAPI."""

    filename: str
    content_type: str

    async def read(self, size: int) -> bytes:
        """Read at most ``size`` bytes from the untrusted upload."""
        ...


class BinaryContent(Protocol):
    """Minimal seekable binary stream shared with scanner and storage ports."""

    def read(self, size: int = -1) -> bytes:
        """Read binary content from the current position."""
        ...

    def seek(self, offset: int, whence: int = 0) -> int:
        """Move the stream cursor and return its resulting position."""
        ...


class BinaryStaging(BinaryContent, Protocol):
    """Writable binary stream used while applying the upload size bound."""

    def write(self, data: bytes) -> int:
        """Write staged bytes and return their count."""
        ...


class EvidenceStore(Protocol):
    """Persistence operations required by evidence use cases."""

    async def get_initiative(self, initiative_id: str) -> InitiativeEvidenceContext | None:
        """Return minimal initiative ownership context when it exists."""
        ...

    async def list_for_initiative(self, initiative_id: str) -> list[EvidenceRecord]:
        """List scanned uploaded evidence in stable creation order."""
        ...

    async def save(self, record: EvidenceRecord) -> EvidenceRecord:
        """Persist evidence metadata without committing the transaction."""
        ...


class MalwareScannerPort(Protocol):
    """Mandatory malware scanning operation."""

    async def scan(self, content: BinaryContent) -> MalwareScanResult:
        """Scan content and return a trusted clean or infected verdict."""
        ...


class ObjectStoragePort(Protocol):
    """Object-storage operations used by secure evidence upload."""

    async def put(
        self,
        *,
        key: str,
        content: BinaryContent,
        content_type: str,
        size_bytes: int,
        sha256: str,
    ) -> StoredObject:
        """Store immutable evidence content under an application-generated key."""
        ...

    async def delete(self, stored: StoredObject) -> None:
        """Remove an object during compensating rollback."""
        ...


class EvidenceAuditPort(Protocol):
    """Content-minimized audit operation for uploaded evidence."""

    async def append(self, *, actor_id: str, record: EvidenceRecord) -> None:
        """Append evidence metadata without filenames or file content."""
        ...


class EvidenceTransactionPort(Protocol):
    """Transaction boundary for metadata and audit persistence."""

    async def commit(self) -> None:
        """Commit evidence metadata and audit atomically."""
        ...

    async def rollback(self) -> None:
        """Discard pending database changes after a failed upload."""
        ...


class UploadEvidence:
    """Validate, scan, store, and audit one immutable evidence artifact."""

    _chunk_size = 64 * 1024

    def __init__(
        self,
        store: EvidenceStore,
        scanner: MalwareScannerPort,
        object_storage: ObjectStoragePort,
        audit: EvidenceAuditPort,
        transaction: EvidenceTransactionPort,
        *,
        max_bytes: int,
        allowed_content_types: frozenset[str],
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize the use case with explicit policy and replaceable adapters."""
        self._store = store
        self._scanner = scanner
        self._object_storage = object_storage
        self._audit = audit
        self._transaction = transaction
        self._max_bytes = max_bytes
        self._allowed_content_types = allowed_content_types
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def execute(
        self,
        *,
        initiative_id: str,
        kind: EvidenceKind,
        source: EvidenceSource,
        actor: EvidenceActor,
    ) -> EvidenceRecord:
        """Run the fail-closed upload pipeline and return trusted metadata."""
        initiative = await _require_initiative(self._store, initiative_id)
        _require_owner(initiative, actor)
        filename = _normalize_filename(source.filename)
        content_type = source.content_type.lower().split(";", maxsplit=1)[0].strip()
        if content_type not in self._allowed_content_types:
            raise ApplicationError(
                ErrorKind.UNSUPPORTED_MEDIA_TYPE,
                "Evidence media type is not allowed",
            )

        with SpooledTemporaryFile(max_size=min(self._max_bytes, 1024 * 1024), mode="w+b") as staged:
            size_bytes, sha256 = await self._stage(source, staged)
            content = staged.read()
            try:
                validate_content(filename=filename, content_type=content_type, content=content)
            except EvidenceDomainError as exc:
                raise ApplicationError(ErrorKind.UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
            staged.seek(0)
            scan = await self._scan(staged)
            if scan.verdict is ScanVerdict.INFECTED:
                raise ApplicationError(ErrorKind.UNPROCESSABLE, "Evidence failed malware scanning")
            staged.seek(0)
            return await self._store_clean_evidence(
                initiative_id=initiative_id,
                kind=kind,
                actor=actor,
                filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                sha256=sha256,
                scan=scan,
                staged=staged,
            )

    async def _stage(self, source: EvidenceSource, staged: BinaryStaging) -> tuple[int, str]:
        """Copy a bounded stream into temporary storage while computing SHA-256."""
        digest = hashlib.sha256()
        size_bytes = 0
        while chunk := await source.read(self._chunk_size):
            size_bytes += len(chunk)
            if size_bytes > self._max_bytes:
                raise ApplicationError(
                    ErrorKind.PAYLOAD_TOO_LARGE,
                    f"Evidence exceeds the {self._max_bytes}-byte upload limit",
                )
            staged.write(chunk)
            digest.update(chunk)
        staged.seek(0)
        return size_bytes, digest.hexdigest()

    async def _scan(self, staged: BinaryContent) -> MalwareScanResult:
        """Invoke the mandatory scanner and hide dependency implementation details."""
        try:
            return await self._scanner.scan(staged)
        except EvidenceDependencyError as exc:
            raise ApplicationError(
                ErrorKind.DEPENDENCY_UNAVAILABLE,
                "Evidence scanning is temporarily unavailable",
            ) from exc

    async def _store_clean_evidence(
        self,
        *,
        initiative_id: str,
        kind: EvidenceKind,
        actor: EvidenceActor,
        filename: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        scan: MalwareScanResult,
        staged: BinaryContent,
    ) -> EvidenceRecord:
        """Store clean bytes before atomically persisting their metadata and audit."""
        evidence_id = self._id_factory()
        key = f"evidence/{initiative_id}/{evidence_id}"
        try:
            stored = await self._object_storage.put(
                key=key,
                content=staged,
                content_type=content_type,
                size_bytes=size_bytes,
                sha256=sha256,
            )
        except EvidenceDependencyError as exc:
            raise ApplicationError(
                ErrorKind.DEPENDENCY_UNAVAILABLE,
                "Evidence storage is temporarily unavailable",
            ) from exc

        now = self._clock()
        record = EvidenceRecord(
            id=evidence_id,
            initiative_id=initiative_id,
            kind=kind,
            original_filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            scan_status=ScanVerdict.CLEAN,
            scanner=scan.scanner,
            scanned_at=now,
            storage=stored,
            supplied_by=actor.user_id,
            version=1,
            created_at=now,
            updated_at=now,
        )
        try:
            saved = await self._store.save(record)
            await self._audit.append(actor_id=actor.user_id, record=saved)
            await self._transaction.commit()
        except Exception:
            try:
                await self._transaction.rollback()
            finally:
                await self._delete_after_failure(stored)
            raise
        return saved

    async def _delete_after_failure(self, stored: StoredObject) -> None:
        """Compensate object creation and fail closed if cleanup cannot be confirmed."""
        try:
            await self._object_storage.delete(stored)
        except EvidenceDependencyError as exc:
            raise ApplicationError(
                ErrorKind.DEPENDENCY_UNAVAILABLE,
                "Evidence upload could not be finalized safely",
            ) from exc


class ListEvidence:
    """List trusted uploaded evidence metadata for an initiative."""

    def __init__(self, store: EvidenceStore) -> None:
        """Initialize the query with its consumer-owned store."""
        self._store = store

    async def execute(
        self,
        initiative_id: str,
        actor: EvidenceActor,
    ) -> list[EvidenceRecord]:
        """Return uploaded evidence after enforcing initiative ownership."""
        initiative = await _require_initiative(self._store, initiative_id)
        _require_owner(initiative, actor)
        return await self._store.list_for_initiative(initiative_id)


async def _require_initiative(
    store: EvidenceStore,
    initiative_id: str,
) -> InitiativeEvidenceContext:
    """Return initiative context or raise a stable not-found error."""
    initiative = await store.get_initiative(initiative_id)
    if initiative is None:
        raise ApplicationError(ErrorKind.NOT_FOUND, "Initiative not found")
    return initiative


def _require_owner(initiative: InitiativeEvidenceContext, actor: EvidenceActor) -> None:
    """Restrict uploads to the initiative owner or a governance administrator."""
    if initiative.business_owner_id != actor.user_id and not actor.is_admin:
        raise ApplicationError(
            ErrorKind.FORBIDDEN,
            "Only the initiative owner or an administrator can upload evidence",
        )


def _normalize_filename(value: str) -> str:
    """Translate typed filename validation into an application error."""
    try:
        return normalize_filename(value)
    except EvidenceDomainError as exc:
        raise ApplicationError(ErrorKind.UNPROCESSABLE, str(exc)) from exc
