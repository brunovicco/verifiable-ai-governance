"""HTTP schemas for secure uploaded evidence metadata."""

from datetime import datetime

from pydantic import BaseModel

from ai_governance_api.domain.evidence import EvidenceKind, EvidenceRecord, ScanVerdict


class EvidenceRead(BaseModel):
    """Content-minimized representation of a trusted uploaded artifact."""

    id: str
    initiative_id: str
    kind: EvidenceKind
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    scan_status: ScanVerdict
    scanner: str
    scanned_at: datetime
    supplied_by: str
    version: int
    created_at: datetime

    @classmethod
    def from_domain(cls, record: EvidenceRecord) -> "EvidenceRead":
        """Map trusted domain metadata without exposing internal storage coordinates."""
        return cls(
            id=record.id,
            initiative_id=record.initiative_id,
            kind=record.kind,
            original_filename=record.original_filename,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            scan_status=record.scan_status,
            scanner=record.scanner,
            scanned_at=record.scanned_at,
            supplied_by=record.supplied_by,
            version=record.version,
            created_at=record.created_at,
        )
