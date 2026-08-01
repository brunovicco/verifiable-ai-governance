from datetime import UTC, datetime
from pathlib import Path

import pytest
from ai_governance_api.adapters.backup_archive import LocalBackupArchive
from ai_governance_api.application.backups import (
    BackupIntegrityError,
    CreateBackup,
    RestoreBackup,
    VerifyBackup,
)
from ai_governance_api.application.backups import (
    TestRestore as RestoreAssurance,
)
from ai_governance_api.domain.backups import DatabaseState, EvidenceArtifact


class FakeDatabase:
    def __init__(self, restored_state: DatabaseState | None = None) -> None:
        self.source_database = "ai_governance"
        self.source_state = DatabaseState(
            alembic_revision="0004",
            table_count=12,
            evidence_object_count=2,
        )
        self.restored_state = restored_state or self.source_state
        self.verified = False
        self.restored: list[str] = []
        self.dropped: list[str] = []

    def create_dump(self, destination: Path) -> DatabaseState:
        destination.write_bytes(b"valid-custom-dump")
        return self.source_state

    def verify_dump(self, source: Path) -> None:
        assert source.read_bytes() == b"valid-custom-dump"
        self.verified = True

    def restore_to_new_database(self, source: Path, target_database: str) -> DatabaseState:
        assert source.read_bytes() == b"valid-custom-dump"
        self.restored.append(target_database)
        return self.restored_state

    def drop_database(self, target_database: str) -> None:
        self.dropped.append(target_database)


class FakeEvidence:
    def __init__(self) -> None:
        self.source_bucket = "governance-evidence"
        self.objects = {
            "evidence/initiative/one": b"first",
            "evidence/initiative/two": b"second",
        }
        self.restored: list[str] = []
        self.deleted: list[str] = []

    def list_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self.objects))

    def download(self, key: str, destination: Path) -> None:
        destination.write_bytes(self.objects[key])

    def restore_to_new_bucket(
        self,
        artifacts: tuple[tuple[EvidenceArtifact, Path], ...],
        target_bucket: str,
    ) -> int:
        assert {item.key for item, _ in artifacts} == set(self.objects)
        self.restored.append(target_bucket)
        return len(artifacts)

    def delete_bucket(self, target_bucket: str) -> None:
        self.deleted.append(target_bucket)


def create_test_backup(
    tmp_path: Path,
    database: FakeDatabase,
    evidence: FakeEvidence,
) -> LocalBackupArchive:
    archive = LocalBackupArchive(tmp_path / "backup")
    CreateBackup(
        archive,
        database,
        evidence,
        clock=lambda: datetime(2026, 8, 1, tzinfo=UTC),
    ).execute()
    return archive


def test_create_verify_and_restore_backup(tmp_path: Path) -> None:
    database = FakeDatabase()
    evidence = FakeEvidence()
    archive = create_test_backup(tmp_path, database, evidence)

    manifest = VerifyBackup(archive, database).execute()
    result = RestoreBackup(archive, database, evidence).execute(
        "governance_restore_test",
        "governance-restore-test",
    )

    assert database.verified is True
    assert len(manifest.evidence) == 2
    assert result.database == database.source_state
    assert result.evidence_count == 2
    assert database.dropped == []
    assert evidence.deleted == []


def test_create_fails_when_database_and_object_inventory_diverge(tmp_path: Path) -> None:
    database = FakeDatabase()
    database.source_state = DatabaseState(
        alembic_revision="0004",
        table_count=12,
        evidence_object_count=1,
    )
    evidence = FakeEvidence()

    with pytest.raises(BackupIntegrityError, match="inventory differ"):
        create_test_backup(tmp_path, database, evidence)

    assert not (tmp_path / "backup").exists()


def test_restore_mismatch_fails_closed_and_removes_partial_database(tmp_path: Path) -> None:
    database = FakeDatabase(
        restored_state=DatabaseState(
            alembic_revision="0003",
            table_count=11,
            evidence_object_count=2,
        )
    )
    evidence = FakeEvidence()
    archive = create_test_backup(tmp_path, database, evidence)

    with pytest.raises(BackupIntegrityError, match="revision"):
        RestoreBackup(archive, database, evidence).execute(
            "governance_restore_mismatch",
            "governance-restore-mismatch",
        )

    assert database.dropped == ["governance_restore_mismatch"]
    assert evidence.restored == []


def test_restore_assurance_always_cleans_successful_isolated_targets(tmp_path: Path) -> None:
    database = FakeDatabase()
    evidence = FakeEvidence()
    archive = create_test_backup(tmp_path, database, evidence)
    restore = RestoreBackup(archive, database, evidence)

    result = RestoreAssurance(restore, database, evidence).execute(
        "governance_restore_assurance",
        "governance-restore-assurance",
    )

    assert result.evidence_count == 2
    assert database.dropped == ["governance_restore_assurance"]
    assert evidence.deleted == ["governance-restore-assurance"]
