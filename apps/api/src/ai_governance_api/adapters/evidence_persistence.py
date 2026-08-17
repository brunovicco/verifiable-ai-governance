"""SQLAlchemy adapters for secure uploaded evidence."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.audit import append_audit_event
from ai_governance_api.domain.evidence import (
    EvidenceKind,
    EvidenceRecord,
    InitiativeEvidenceContext,
    ScanVerdict,
    StoredObject,
)
from ai_governance_api.models import Evidence, Initiative


class SqlAlchemyEvidenceStore:
    """Persist scanned evidence metadata in a request-scoped session."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the store with its database session."""
        self._session = session

    async def get_initiative(self, initiative_id: str) -> InitiativeEvidenceContext | None:
        """Return the ownership fields needed by evidence authorization."""
        initiative = await self._session.get(Initiative, initiative_id)
        if initiative is None:
            return None
        return InitiativeEvidenceContext(
            id=initiative.id,
            business_owner_id=initiative.business_owner_id,
        )

    async def list_for_initiative(self, initiative_id: str) -> list[EvidenceRecord]:
        """List uploaded artifacts without mixing legacy URI-only evidence."""
        entities = await self._session.scalars(
            select(Evidence)
            .where(
                Evidence.initiative_id == initiative_id,
                Evidence.storage_key.is_not(None),
            )
            .order_by(Evidence.created_at, Evidence.id)
        )
        return [_to_domain(entity) for entity in entities]

    async def get_uploaded(
        self,
        evidence_id: str,
        initiative_id: str,
    ) -> EvidenceRecord | None:
        """Return one eligible upload by exact evidence and initiative identity."""
        entity = await self._session.scalar(
            select(Evidence).where(
                Evidence.id == evidence_id,
                Evidence.initiative_id == initiative_id,
                Evidence.trusted_source.is_(True),
                Evidence.scan_status == ScanVerdict.CLEAN.value,
                Evidence.storage_bucket.is_not(None),
                Evidence.storage_key.is_not(None),
            )
        )
        return _to_domain(entity) if entity is not None else None

    async def save(self, record: EvidenceRecord) -> EvidenceRecord:
        """Insert immutable metadata without committing the transaction."""
        entity = Evidence(
            id=record.id,
            initiative_id=record.initiative_id,
            approval_id=None,
            kind=record.kind.value,
            uri=record.storage.uri,
            sha256=record.sha256,
            metadata_json={},
            supplied_by=record.supplied_by,
            trusted_source=True,
            original_filename=record.original_filename,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            scan_status=record.scan_status.value,
            scanner=record.scanner,
            scanned_at=record.scanned_at,
            storage_bucket=record.storage.bucket,
            storage_key=record.storage.key,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        self._session.add(entity)
        await self._session.flush()
        return _to_domain(entity)


class SqlAlchemyEvidenceAudit:
    """Append content-minimized evidence events to the shared audit chain."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with the same transaction as evidence metadata."""
        self._session = session

    async def append(self, *, actor_id: str, record: EvidenceRecord) -> None:
        """Record integrity and scan facts without content or original filename."""
        await append_audit_event(
            self._session,
            actor_id=actor_id,
            action="evidence.uploaded",
            entity_type="evidence",
            entity_id=record.id,
            entity_version=record.version,
            payload={
                "initiative_id": record.initiative_id,
                "kind": record.kind.value,
                "content_type": record.content_type,
                "size_bytes": record.size_bytes,
                "sha256": record.sha256,
                "scan_status": record.scan_status.value,
                "scanner": record.scanner,
            },
        )


def _to_domain(entity: Evidence) -> EvidenceRecord:
    """Map a complete uploaded evidence row into its domain record."""
    if (
        entity.original_filename is None
        or entity.content_type is None
        or entity.size_bytes is None
        or entity.scanner is None
        or entity.scanned_at is None
        or entity.storage_bucket is None
        or entity.storage_key is None
    ):
        raise ValueError("Uploaded evidence metadata is incomplete")
    return EvidenceRecord(
        id=entity.id,
        initiative_id=entity.initiative_id,
        kind=EvidenceKind(entity.kind),
        original_filename=entity.original_filename,
        content_type=entity.content_type,
        size_bytes=entity.size_bytes,
        sha256=entity.sha256,
        scan_status=ScanVerdict(entity.scan_status),
        scanner=entity.scanner,
        scanned_at=_as_utc(entity.scanned_at),
        storage=StoredObject(
            bucket=entity.storage_bucket,
            key=entity.storage_key,
            uri=entity.uri,
        ),
        supplied_by=entity.supplied_by,
        version=entity.version,
        created_at=_as_utc(entity.created_at),
        updated_at=_as_utc(entity.updated_at),
    )


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive and PostgreSQL-aware timestamps to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
