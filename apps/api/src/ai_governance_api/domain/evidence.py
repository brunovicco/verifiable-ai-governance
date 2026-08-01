"""Pure evidence metadata, validation rules, and malware verdicts."""

import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath


class EvidenceDomainError(ValueError):
    """Base class for rejected evidence metadata or content."""


class InvalidEvidenceName(EvidenceDomainError):
    """Raised when a supplied filename is unsafe or unusable."""


class UnsupportedEvidenceType(EvidenceDomainError):
    """Raised when evidence content does not match its declared safe type."""


class EvidenceKind(StrEnum):
    """Supported governance purposes for an uploaded evidence artifact."""

    POLICY = "policy"
    ASSESSMENT = "assessment"
    ARCHITECTURE = "architecture"
    SECURITY_TEST = "security_test"
    APPROVAL = "approval"
    OTHER = "other"


class ScanVerdict(StrEnum):
    """Trusted verdicts returned by the malware scanning boundary."""

    CLEAN = "clean"
    INFECTED = "infected"


@dataclass(frozen=True)
class EvidenceActor:
    """Authenticated actor relevant to evidence authorization."""

    user_id: str
    is_admin: bool = False


@dataclass(frozen=True)
class InitiativeEvidenceContext:
    """Minimal initiative context required by evidence use cases."""

    id: str
    business_owner_id: str


@dataclass(frozen=True)
class MalwareScanResult:
    """Content-minimized result produced by a trusted scanner."""

    verdict: ScanVerdict
    scanner: str
    signature: str | None = None


@dataclass(frozen=True)
class StoredObject:
    """Opaque location assigned by an object-storage adapter."""

    bucket: str
    key: str
    uri: str


@dataclass(frozen=True)
class EvidenceRecord:
    """Immutable metadata for a scanned evidence artifact."""

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
    storage: StoredObject
    supplied_by: str
    version: int
    created_at: datetime
    updated_at: datetime


_EXTENSIONS_BY_TYPE: dict[str, frozenset[str]] = {
    "application/pdf": frozenset({".pdf"}),
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "text/plain": frozenset({".txt"}),
    "text/csv": frozenset({".csv"}),
    "application/json": frozenset({".json"}),
}


def normalize_filename(value: str) -> str:
    """Return a display-only basename after rejecting controls and ambiguity."""
    filename = unicodedata.normalize(
        "NFC",
        PurePosixPath(value.replace("\\", "/")).name.strip(),
    )
    if not filename or filename in {".", ".."}:
        raise InvalidEvidenceName("Evidence filename is required")
    if len(filename) > 255:
        raise InvalidEvidenceName("Evidence filename exceeds 255 characters")
    if any(unicodedata.category(character).startswith("C") for character in filename):
        raise InvalidEvidenceName("Evidence filename contains control or format characters")
    return filename


def validate_content(
    *,
    filename: str,
    content_type: str,
    content: bytes,
) -> None:
    """Validate extension, signature, and bounded textual structure."""
    expected_extensions = _EXTENSIONS_BY_TYPE.get(content_type)
    if expected_extensions is None:
        raise UnsupportedEvidenceType("Evidence media type is not allowed")
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in expected_extensions:
        raise UnsupportedEvidenceType("Evidence extension does not match its media type")
    if not content:
        raise UnsupportedEvidenceType("Evidence file is empty")

    if content_type == "application/pdf" and not content.startswith(b"%PDF-"):
        raise UnsupportedEvidenceType("Evidence content is not a valid PDF signature")
    if content_type == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise UnsupportedEvidenceType("Evidence content is not a valid PNG signature")
    if content_type == "image/jpeg" and not content.startswith(b"\xff\xd8\xff"):
        raise UnsupportedEvidenceType("Evidence content is not a valid JPEG signature")
    if content_type in {"text/plain", "text/csv", "application/json"}:
        _validate_text(content_type, content)


def _validate_text(content_type: str, content: bytes) -> None:
    """Reject binary masquerading as text and validate JSON syntax when declared."""
    if b"\x00" in content:
        raise UnsupportedEvidenceType("Text evidence contains binary null bytes")
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedEvidenceType("Text evidence must use UTF-8") from exc
    if content_type == "application/json":
        try:
            json.loads(decoded)
        except (ValueError, RecursionError) as exc:
            raise UnsupportedEvidenceType("Evidence content is not valid JSON") from exc
