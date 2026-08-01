"""Backup, integrity verification, and isolated restore use cases."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ai_governance_api.domain.backups import (
    BACKUP_FORMAT_VERSION,
    BackupManifest,
    DatabaseArtifact,
    DatabaseState,
    EvidenceArtifact,
    FileArtifact,
    RestoreResult,
)


class BackupOperationError(RuntimeError):
    """Base error for safe operational backup failures."""


class BackupDependencyError(BackupOperationError):
    """Raised when PostgreSQL, object storage, or Docker is unavailable."""


class BackupConflictError(BackupOperationError):
    """Raised when an operation would overwrite an archive or restore target."""


class BackupIntegrityError(BackupOperationError):
    """Raised when a manifest, dump, or evidence object fails validation."""


class BackupArchivePort(Protocol):
    """File-archive operations consumed by backup use cases."""

    def prepare(self) -> None:
        """Create a private temporary archive without overwriting a target."""

    def database_destination(self) -> Path:
        """Return the destination for the PostgreSQL custom-format dump."""

    def evidence_destination(self, index: int, key: str) -> Path:
        """Return a collision-resistant destination for one evidence object."""

    def file_artifact(self, path: Path) -> FileArtifact:
        """Calculate the relative path, size, and SHA-256 for one artifact."""

    def finalize(self, manifest: BackupManifest) -> None:
        """Persist the manifest atomically and publish the completed archive."""

    def discard(self) -> None:
        """Remove only the unpublished temporary archive after a failed create."""

    def load(self) -> BackupManifest:
        """Load and validate the manifest from a published archive."""

    def verify_files(self, manifest: BackupManifest) -> None:
        """Verify manifest checksum, file set, sizes, and artifact digests."""

    def resolve(self, artifact: FileArtifact) -> Path:
        """Resolve a validated artifact path inside the published archive."""


class DatabaseBackupPort(Protocol):
    """PostgreSQL logical-backup operations consumed by application use cases."""

    @property
    def source_database(self) -> str:
        """Return the configured source database name."""

    def create_dump(self, destination: Path) -> DatabaseState:
        """Write one consistent custom-format dump and return its source state."""

    def verify_dump(self, source: Path) -> None:
        """Ask PostgreSQL tooling to parse and validate a dump catalog."""

    def restore_to_new_database(self, source: Path, target_database: str) -> DatabaseState:
        """Restore a dump only when the requested target database does not exist."""

    def drop_database(self, target_database: str) -> None:
        """Remove a known isolated restore target."""


class EvidenceBackupPort(Protocol):
    """S3-compatible evidence operations consumed by application use cases."""

    @property
    def source_bucket(self) -> str:
        """Return the configured source evidence bucket."""

    def list_keys(self) -> tuple[str, ...]:
        """List source object keys in a stable order."""

    def download(self, key: str, destination: Path) -> None:
        """Stream one private source object into the backup archive."""

    def restore_to_new_bucket(
        self,
        artifacts: tuple[tuple[EvidenceArtifact, Path], ...],
        target_bucket: str,
    ) -> int:
        """Restore all objects or clean any bucket created before raising an error."""

    def delete_bucket(self, target_bucket: str) -> None:
        """Remove a known isolated restore bucket and all its objects."""


class CreateBackup:
    """Create an atomic portable archive from both stateful backing services."""

    def __init__(
        self,
        archive: BackupArchivePort,
        database: DatabaseBackupPort,
        evidence: EvidenceBackupPort,
        clock: Callable[[], datetime],
    ) -> None:
        """Initialize the use case with consumer-owned ports and an injected clock."""
        self._archive = archive
        self._database = database
        self._evidence = evidence
        self._clock = clock

    def execute(self) -> BackupManifest:
        """Create all artifacts and publish only after the manifest is complete."""
        self._archive.prepare()
        try:
            database_path = self._archive.database_destination()
            database_state = self._database.create_dump(database_path)
            database_file = self._archive.file_artifact(database_path)

            evidence_artifacts: list[EvidenceArtifact] = []
            for index, key in enumerate(self._evidence.list_keys(), start=1):
                destination = self._archive.evidence_destination(index, key)
                self._evidence.download(key, destination)
                evidence_artifacts.append(
                    EvidenceArtifact(
                        key=key,
                        file=self._archive.file_artifact(destination),
                    )
                )
            if len(evidence_artifacts) != database_state.evidence_object_count:
                raise BackupIntegrityError(
                    "Database evidence metadata and object-storage inventory differ"
                )

            manifest = BackupManifest(
                format_version=BACKUP_FORMAT_VERSION,
                created_at=self._clock(),
                source_database=self._database.source_database,
                source_bucket=self._evidence.source_bucket,
                database=DatabaseArtifact(
                    file=database_file,
                    alembic_revision=database_state.alembic_revision,
                    table_count=database_state.table_count,
                    evidence_object_count=database_state.evidence_object_count,
                ),
                evidence=tuple(evidence_artifacts),
            )
            self._archive.finalize(manifest)
            return manifest
        except Exception:
            self._archive.discard()
            raise


class VerifyBackup:
    """Verify file integrity and PostgreSQL dump readability without restoring."""

    def __init__(self, archive: BackupArchivePort, database: DatabaseBackupPort) -> None:
        """Initialize verification with archive and PostgreSQL ports."""
        self._archive = archive
        self._database = database

    def execute(self) -> BackupManifest:
        """Return the manifest only after every local and dump check succeeds."""
        manifest = self._archive.load()
        self._archive.verify_files(manifest)
        self._database.verify_dump(self._archive.resolve(manifest.database.file))
        return manifest


class RestoreBackup:
    """Restore a verified archive without overwriting existing destinations."""

    def __init__(
        self,
        archive: BackupArchivePort,
        database: DatabaseBackupPort,
        evidence: EvidenceBackupPort,
    ) -> None:
        """Initialize the restore use case with its external gateways."""
        self._archive = archive
        self._database = database
        self._evidence = evidence

    def execute(self, target_database: str, target_bucket: str) -> RestoreResult:
        """Restore and verify PostgreSQL and evidence into new named targets."""
        manifest = VerifyBackup(self._archive, self._database).execute()
        database_created = False
        bucket_created = False
        try:
            database_state = self._database.restore_to_new_database(
                self._archive.resolve(manifest.database.file),
                target_database,
            )
            database_created = True
            self._assert_database_matches(manifest, database_state)

            artifacts = tuple(
                (item, self._archive.resolve(item.file)) for item in manifest.evidence
            )
            restored_count = self._evidence.restore_to_new_bucket(artifacts, target_bucket)
            bucket_created = True
            if restored_count != len(manifest.evidence):
                raise BackupIntegrityError("Restored evidence object count does not match manifest")

            return RestoreResult(
                database_name=target_database,
                bucket_name=target_bucket,
                database=database_state,
                evidence_count=restored_count,
            )
        except Exception:
            if bucket_created:
                self._evidence.delete_bucket(target_bucket)
            if database_created:
                self._database.drop_database(target_database)
            raise

    @staticmethod
    def _assert_database_matches(
        manifest: BackupManifest,
        restored: DatabaseState,
    ) -> None:
        """Compare schema provenance and the minimum public table count."""
        expected = manifest.database
        if restored.alembic_revision != expected.alembic_revision:
            raise BackupIntegrityError("Restored Alembic revision does not match manifest")
        if restored.table_count != expected.table_count:
            raise BackupIntegrityError("Restored table count does not match manifest")
        if restored.evidence_object_count != expected.evidence_object_count:
            raise BackupIntegrityError("Restored evidence metadata count does not match manifest")


class TestRestore:
    """Prove restorability in isolated targets and always clean them afterward."""

    def __init__(
        self,
        restore: RestoreBackup,
        database: DatabaseBackupPort,
        evidence: EvidenceBackupPort,
    ) -> None:
        """Initialize the assurance workflow with explicit cleanup gateways."""
        self._restore = restore
        self._database = database
        self._evidence = evidence

    def execute(self, target_database: str, target_bucket: str) -> RestoreResult:
        """Restore, retain the result in memory, and remove isolated targets."""
        result = self._restore.execute(target_database, target_bucket)
        cleanup_errors: list[Exception] = []
        try:
            self._evidence.delete_bucket(target_bucket)
        except Exception as exc:  # pragma: no cover - reported as an operational failure
            cleanup_errors.append(exc)
        try:
            self._database.drop_database(target_database)
        except Exception as exc:  # pragma: no cover - reported as an operational failure
            cleanup_errors.append(exc)
        if cleanup_errors:
            raise BackupDependencyError("Restore test passed but isolated-target cleanup failed")
        return result
