"""Immutable backup manifests and restore-assurance results."""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

BACKUP_FORMAT_VERSION = 1
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class InvalidBackupManifest(ValueError):
    """Raised when backup metadata violates the portable archive contract."""


@dataclass(frozen=True)
class FileArtifact:
    """Integrity metadata for one file inside a backup archive."""

    relative_path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        """Reject unsafe paths and malformed integrity metadata."""
        path = PurePosixPath(self.relative_path)
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise InvalidBackupManifest("Backup artifact path must stay inside the archive")
        if not _SHA256_PATTERN.fullmatch(self.sha256):
            raise InvalidBackupManifest("Backup artifact SHA-256 must be lowercase hexadecimal")
        if self.size_bytes < 0:
            raise InvalidBackupManifest("Backup artifact size cannot be negative")


@dataclass(frozen=True)
class DatabaseArtifact:
    """PostgreSQL dump metadata captured with the source schema state."""

    file: FileArtifact
    alembic_revision: str
    table_count: int
    evidence_object_count: int

    def __post_init__(self) -> None:
        """Validate the minimum state required for meaningful restore assurance."""
        if not self.alembic_revision.strip():
            raise InvalidBackupManifest("Database artifact requires an Alembic revision")
        if self.table_count < 1:
            raise InvalidBackupManifest("Database artifact must contain at least one table")
        if self.evidence_object_count < 0:
            raise InvalidBackupManifest("Evidence object count cannot be negative")


@dataclass(frozen=True)
class EvidenceArtifact:
    """One object-storage artifact mapped to its original immutable key."""

    key: str
    file: FileArtifact

    def __post_init__(self) -> None:
        """Reject empty or ambiguous object keys."""
        if not self.key or self.key.strip() != self.key:
            raise InvalidBackupManifest("Evidence object key cannot be empty or padded")
        if "\x00" in self.key or len(self.key.encode("utf-8")) > 1024:
            raise InvalidBackupManifest("Evidence object key exceeds the S3 safety contract")


@dataclass(frozen=True)
class BackupManifest:
    """Portable manifest linking database and evidence artifacts by checksum."""

    format_version: int
    created_at: datetime
    source_database: str
    source_bucket: str
    database: DatabaseArtifact
    evidence: tuple[EvidenceArtifact, ...]

    def __post_init__(self) -> None:
        """Validate version, provenance, timestamps, and artifact uniqueness."""
        if self.format_version != BACKUP_FORMAT_VERSION:
            raise InvalidBackupManifest(f"Unsupported backup format version: {self.format_version}")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise InvalidBackupManifest("Backup timestamp must include a timezone")
        if not self.source_database.strip() or not self.source_bucket.strip():
            raise InvalidBackupManifest("Backup provenance requires database and bucket names")

        paths = [self.database.file.relative_path]
        paths.extend(item.file.relative_path for item in self.evidence)
        if len(paths) != len(set(paths)):
            raise InvalidBackupManifest("Backup artifact paths must be unique")

        keys = [item.key for item in self.evidence]
        if len(keys) != len(set(keys)):
            raise InvalidBackupManifest("Evidence object keys must be unique")


@dataclass(frozen=True)
class DatabaseState:
    """Minimal database state used to compare a restored target with its source."""

    alembic_revision: str
    table_count: int
    evidence_object_count: int


@dataclass(frozen=True)
class RestoreResult:
    """Evidence that an archive was restored into isolated destinations."""

    database_name: str
    bucket_name: str
    database: DatabaseState
    evidence_count: int
