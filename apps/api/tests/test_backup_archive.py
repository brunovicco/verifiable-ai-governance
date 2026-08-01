from datetime import UTC, datetime
from pathlib import Path

import pytest
from ai_governance_api.adapters.backup_archive import LocalBackupArchive
from ai_governance_api.application.backups import BackupConflictError, BackupIntegrityError
from ai_governance_api.domain.backups import (
    BACKUP_FORMAT_VERSION,
    BackupManifest,
    DatabaseArtifact,
    EvidenceArtifact,
)


def create_archive(path: Path) -> tuple[LocalBackupArchive, BackupManifest]:
    archive = LocalBackupArchive(path)
    archive.prepare()
    database_path = archive.database_destination()
    database_path.write_bytes(b"postgres-custom-dump")
    evidence_path = archive.evidence_destination(1, "evidence/initiative/artifact")
    evidence_path.write_bytes(b"trusted evidence")
    manifest = BackupManifest(
        format_version=BACKUP_FORMAT_VERSION,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_database="ai_governance",
        source_bucket="governance-evidence",
        database=DatabaseArtifact(
            file=archive.file_artifact(database_path),
            alembic_revision="0004",
            table_count=12,
            evidence_object_count=1,
        ),
        evidence=(
            EvidenceArtifact(
                key="evidence/initiative/artifact",
                file=archive.file_artifact(evidence_path),
            ),
        ),
    )
    archive.finalize(manifest)
    return archive, manifest


def test_local_archive_round_trips_and_verifies_private_artifacts(tmp_path: Path) -> None:
    archive, manifest = create_archive(tmp_path / "backup")

    assert archive.load() == manifest
    archive.verify_files(manifest)
    assert (tmp_path / "backup").stat().st_mode & 0o777 == 0o700
    assert archive.resolve(manifest.database.file).stat().st_mode & 0o777 == 0o600


def test_local_archive_supports_a_resolved_parent_alias(tmp_path: Path) -> None:
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    alias_parent = tmp_path / "alias"
    alias_parent.symlink_to(real_parent, target_is_directory=True)

    archive, manifest = create_archive(alias_parent / "backup")

    archive.verify_files(manifest)
    assert (real_parent / "backup" / "postgres.dump").is_file()


def test_local_archive_detects_tampered_artifact(tmp_path: Path) -> None:
    archive, manifest = create_archive(tmp_path / "backup")
    archive.resolve(manifest.database.file).write_bytes(b"tampered")

    with pytest.raises(BackupIntegrityError, match="size mismatch"):
        archive.verify_files(manifest)


def test_local_archive_rejects_symlinked_artifact(tmp_path: Path) -> None:
    archive, manifest = create_archive(tmp_path / "backup")
    database_path = tmp_path / "backup" / "postgres.dump"
    outside = tmp_path / "outside.dump"
    outside.write_bytes(database_path.read_bytes())
    database_path.unlink()
    database_path.symlink_to(outside)

    with pytest.raises(BackupIntegrityError, match="symlinks"):
        archive.verify_files(manifest)


def test_local_archive_refuses_to_overwrite_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "backup"
    destination.mkdir()

    with pytest.raises(BackupConflictError, match="already exists"):
        LocalBackupArchive(destination).prepare()


def test_local_archive_discards_only_unpublished_work(tmp_path: Path) -> None:
    destination = tmp_path / "backup"
    archive = LocalBackupArchive(destination)
    archive.prepare()
    temporary_parent_entries = tuple(tmp_path.iterdir())

    archive.discard()

    assert temporary_parent_entries
    assert tuple(tmp_path.iterdir()) == ()
    assert not destination.exists()
