"""Governance knowledge adapter for verified private evidence uploads."""

import hmac
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from governance_schemas import GovernanceSourceReference
from sqlalchemy.exc import SQLAlchemyError

from ai_governance_api.application.evidence import EvidenceDependencyError
from ai_governance_api.application.governance_knowledge import (
    GovernanceKnowledgeAccess,
    GovernanceKnowledgeContent,
    GovernanceKnowledgeDependencyError,
    ResolvedGovernanceKnowledgeSource,
)
from ai_governance_api.domain.evidence import (
    EvidenceRecord,
    InitiativeEvidenceContext,
    ScanVerdict,
    StoredObject,
)

_EVIDENCE_ARTIFACT_PREFIX = "evidence:"


class _VerifiedEvidenceStore(Protocol):
    """Metadata reads required by the verified-evidence knowledge adapter."""

    async def get_initiative(self, initiative_id: str) -> InitiativeEvidenceContext | None:
        """Return the exact initiative ownership context."""
        ...

    async def get_uploaded(
        self,
        evidence_id: str,
        initiative_id: str,
    ) -> EvidenceRecord | None:
        """Return eligible uploaded evidence inside the exact initiative boundary."""
        ...


class _EvidenceObjectContent(Protocol):
    """Private storage stream hidden behind evidence dependency errors."""

    async def read(self, size: int) -> bytes:
        """Read at most ``size`` bytes."""
        ...

    async def close(self) -> None:
        """Release the private storage stream."""
        ...


class _EvidenceObjectReader(Protocol):
    """Open an exact internal storage object without exposing coordinates."""

    async def open(self, stored: StoredObject) -> _EvidenceObjectContent:
        """Open the private object identified by trusted evidence metadata."""
        ...


@dataclass(frozen=True, slots=True)
class _AuthorizationKey:
    """Bind cached authorization to the complete access and reference context."""

    actor_id: str
    subject_id: str
    correlation_id: str
    is_admin: bool
    artifact_id: str
    version: str
    content_digest: str


class _KnowledgeContent:
    """Map evidence storage failures into the governance knowledge boundary."""

    def __init__(self, content: _EvidenceObjectContent) -> None:
        self._content = content

    async def read(self, size: int) -> bytes:
        """Read private evidence through the generic knowledge stream contract."""
        try:
            return await self._content.read(size)
        except EvidenceDependencyError as exc:
            raise GovernanceKnowledgeDependencyError(
                "Verified evidence content is unavailable"
            ) from exc

    async def close(self) -> None:
        """Close private evidence through the generic knowledge stream contract."""
        try:
            await self._content.close()
        except EvidenceDependencyError as exc:
            raise GovernanceKnowledgeDependencyError(
                "Verified evidence content could not be closed"
            ) from exc


class VerifiedEvidenceKnowledgeAdapter:
    """Authorize and resolve clean private uploads as governed knowledge sources."""

    def __init__(
        self,
        store: _VerifiedEvidenceStore,
        object_reader: _EvidenceObjectReader,
    ) -> None:
        """Initialize request-scoped authorization state and infrastructure ports."""
        self._store = store
        self._object_reader = object_reader
        self._authorized: dict[_AuthorizationKey, EvidenceRecord] = {}

    async def can_read(
        self,
        *,
        reference: GovernanceSourceReference,
        access: GovernanceKnowledgeAccess,
    ) -> bool:
        """Authorize an exact immutable upload for its initiative owner or an administrator."""
        evidence_id = _evidence_id(reference)
        if evidence_id is None or reference.node_id is not None or reference.section is not None:
            return False

        try:
            initiative = await self._store.get_initiative(access.subject_id)
        except (SQLAlchemyError, ValueError) as exc:
            raise GovernanceKnowledgeDependencyError(
                "Verified evidence authorization is unavailable"
            ) from exc
        if initiative is None or (
            initiative.business_owner_id != access.actor_id and not access.is_admin
        ):
            return False
        try:
            record = await self._store.get_uploaded(evidence_id, access.subject_id)
        except (SQLAlchemyError, ValueError) as exc:
            raise GovernanceKnowledgeDependencyError(
                "Verified evidence metadata is unavailable"
            ) from exc
        if (
            record is None
            or record.initiative_id != access.subject_id
            or record.scan_status is not ScanVerdict.CLEAN
            or record.version <= 0
            or str(record.version) != reference.version
            or not hmac.compare_digest(record.sha256, reference.content_digest)
            or record.storage.key != f"evidence/{record.initiative_id}/{record.id}"
        ):
            return False

        self._authorized[_authorization_key(reference, access)] = record
        return True

    async def resolve(
        self,
        *,
        reference: GovernanceSourceReference,
        access: GovernanceKnowledgeAccess,
    ) -> ResolvedGovernanceKnowledgeSource | None:
        """Resolve only a source authorized by this request-scoped adapter instance."""
        record = self._authorized.get(_authorization_key(reference, access))
        if record is None:
            return None
        try:
            content = await self._object_reader.open(record.storage)
        except EvidenceDependencyError as exc:
            raise GovernanceKnowledgeDependencyError(
                "Verified evidence storage is unavailable"
            ) from exc
        knowledge_content: GovernanceKnowledgeContent = _KnowledgeContent(content)
        return ResolvedGovernanceKnowledgeSource(
            artifact_id=reference.artifact_id,
            version=reference.version,
            content_type=record.content_type,
            content=knowledge_content,
        )


def governance_reference_for_evidence(record: EvidenceRecord) -> GovernanceSourceReference:
    """Create the canonical knowledge reference for one clean uploaded evidence record."""
    evidence_id = _canonical_uuid(record.id)
    canonical_storage_key = f"evidence/{record.initiative_id}/{record.id}"
    if (
        evidence_id is None
        or record.scan_status is not ScanVerdict.CLEAN
        or record.version <= 0
        or record.storage.key != canonical_storage_key
    ):
        raise ValueError("Evidence record is not eligible for governance knowledge")
    return GovernanceSourceReference(
        artifact_id=f"{_EVIDENCE_ARTIFACT_PREFIX}{evidence_id}",
        version=str(record.version),
        content_digest=record.sha256,
    )


def _evidence_id(reference: GovernanceSourceReference) -> str | None:
    """Parse the canonical evidence artifact identifier without accepting aliases."""
    if not reference.artifact_id.startswith(_EVIDENCE_ARTIFACT_PREFIX):
        return None
    return _canonical_uuid(reference.artifact_id.removeprefix(_EVIDENCE_ARTIFACT_PREFIX))


def _canonical_uuid(value: str) -> str | None:
    """Return a canonical non-nil UUID or no identity."""
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    canonical = str(parsed)
    return canonical if parsed.int != 0 and canonical == value else None


def _authorization_key(
    reference: GovernanceSourceReference,
    access: GovernanceKnowledgeAccess,
) -> _AuthorizationKey:
    """Create an exact cache key without storing source bytes or storage coordinates."""
    return _AuthorizationKey(
        actor_id=access.actor_id,
        subject_id=access.subject_id,
        correlation_id=access.correlation_id,
        is_admin=access.is_admin,
        artifact_id=reference.artifact_id,
        version=reference.version,
        content_digest=reference.content_digest,
    )
