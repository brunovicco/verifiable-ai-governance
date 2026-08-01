from datetime import UTC, datetime

import pytest
from ai_governance_api.domain.backups import (
    BACKUP_FORMAT_VERSION,
    BackupManifest,
    DatabaseArtifact,
    EvidenceArtifact,
    FileArtifact,
    InvalidBackupManifest,
)


def artifact(path: str, digest: str = "a" * 64) -> FileArtifact:
    return FileArtifact(relative_path=path, sha256=digest, size_bytes=1)


def database(path: str = "postgres.dump") -> DatabaseArtifact:
    return DatabaseArtifact(
        file=artifact(path),
        alembic_revision="0004",
        table_count=12,
        evidence_object_count=0,
    )


def test_file_artifact_rejects_path_traversal() -> None:
    with pytest.raises(InvalidBackupManifest, match="inside the archive"):
        artifact("../postgres.dump")


def test_file_artifact_rejects_malformed_digest() -> None:
    with pytest.raises(InvalidBackupManifest, match="SHA-256"):
        artifact("postgres.dump", "not-a-digest")


def test_evidence_artifact_rejects_oversized_object_key() -> None:
    with pytest.raises(InvalidBackupManifest, match="S3 safety"):
        EvidenceArtifact(key="x" * 1025, file=artifact("evidence/one.bin"))


def test_manifest_rejects_duplicate_paths_and_object_keys() -> None:
    duplicated_path = EvidenceArtifact(key="evidence/one", file=artifact("postgres.dump"))
    with pytest.raises(InvalidBackupManifest, match="paths must be unique"):
        BackupManifest(
            format_version=BACKUP_FORMAT_VERSION,
            created_at=datetime.now(UTC),
            source_database="ai_governance",
            source_bucket="governance-evidence",
            database=database(),
            evidence=(duplicated_path,),
        )

    duplicated_key = (
        EvidenceArtifact(key="evidence/one", file=artifact("evidence/one.bin")),
        EvidenceArtifact(key="evidence/one", file=artifact("evidence/two.bin")),
    )
    with pytest.raises(InvalidBackupManifest, match="keys must be unique"):
        BackupManifest(
            format_version=BACKUP_FORMAT_VERSION,
            created_at=datetime.now(UTC),
            source_database="ai_governance",
            source_bucket="governance-evidence",
            database=database(),
            evidence=duplicated_key,
        )


def test_manifest_requires_timezone_and_supported_format() -> None:
    with pytest.raises(InvalidBackupManifest, match="format version"):
        BackupManifest(
            format_version=2,
            created_at=datetime.now(UTC),
            source_database="ai_governance",
            source_bucket="governance-evidence",
            database=database(),
            evidence=(),
        )

    with pytest.raises(InvalidBackupManifest, match="timezone"):
        BackupManifest(
            format_version=BACKUP_FORMAT_VERSION,
            created_at=datetime(2026, 8, 1),
            source_database="ai_governance",
            source_bucket="governance-evidence",
            database=database(),
            evidence=(),
        )
