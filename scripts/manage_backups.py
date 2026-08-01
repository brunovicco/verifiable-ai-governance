"""Create, verify, restore, and test portable local backup packages."""

import argparse
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ai_governance_api.adapters.backup_archive import LocalBackupArchive
from ai_governance_api.adapters.backup_services import (
    DockerComposePostgres,
    S3EvidenceBackup,
)
from ai_governance_api.application.backups import (
    BackupOperationError,
    CreateBackup,
    RestoreBackup,
    TestRestore,
    VerifyBackup,
)
from ai_governance_api.domain.backups import BackupManifest, RestoreResult


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit backup-management command-line contract."""
    parser = argparse.ArgumentParser(
        description=(
            "Manage portable PostgreSQL and evidence backups without overwriting restore targets."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a new private backup archive")
    create.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify", help="Verify archive and pg_dump integrity")
    verify.add_argument("--backup", type=Path, required=True)

    restore = subparsers.add_parser(
        "restore",
        help="Restore only to an absent database and absent evidence bucket",
    )
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--database", required=True)
    restore.add_argument("--bucket", required=True)

    restore_test = subparsers.add_parser(
        "restore-test",
        help="Restore to generated isolated targets, verify them, and clean them",
    )
    restore_test.add_argument("--backup", type=Path, required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    """Execute one backup command and emit content-minimized JSON status."""
    options = build_parser().parse_args(arguments)
    try:
        local_environment = os.getenv("APP_ENV", "local").lower() in {"local", "test"}
        database = DockerComposePostgres(
            source_database=os.getenv("POSTGRES_DB", "ai_governance"),
            database_user=os.getenv("POSTGRES_USER", "governance"),
            command_timeout_seconds=_integer_environment(
                "BACKUP_DATABASE_COMMAND_TIMEOUT_SECONDS",
                1800,
            ),
        )
        evidence = S3EvidenceBackup(
            endpoint_url=_first_environment(
                "BACKUP_OBJECT_STORAGE_ENDPOINT_URL",
                "OBJECT_STORAGE_ENDPOINT_URL",
                default=(
                    f"http://127.0.0.1:{os.getenv('MINIO_API_PORT', '9000')}"
                    if local_environment
                    else ""
                ),
            ),
            region=os.getenv("OBJECT_STORAGE_REGION", "us-east-1"),
            source_bucket=os.getenv("OBJECT_STORAGE_BUCKET", "governance-evidence"),
            access_key=_first_environment(
                "BACKUP_OBJECT_STORAGE_ACCESS_KEY",
                "OBJECT_STORAGE_ACCESS_KEY",
                "MINIO_ROOT_USER",
                default="governance" if local_environment else "",
            ),
            secret_key=_first_environment(
                "BACKUP_OBJECT_STORAGE_SECRET_KEY",
                "OBJECT_STORAGE_SECRET_KEY",
                "MINIO_ROOT_PASSWORD",
                default="governance-local-only" if local_environment else "",
            ),
            session_token=_first_environment(
                "BACKUP_OBJECT_STORAGE_SESSION_TOKEN",
                "AWS_SESSION_TOKEN",
                default="",
            ),
            connect_timeout_seconds=_integer_environment(
                "BACKUP_S3_CONNECT_TIMEOUT_SECONDS",
                3,
            ),
            read_timeout_seconds=_integer_environment(
                "BACKUP_S3_READ_TIMEOUT_SECONDS",
                30,
            ),
            max_attempts=_integer_environment("BACKUP_S3_MAX_ATTEMPTS", 3),
            server_side_encryption=os.getenv("OBJECT_STORAGE_SERVER_SIDE_ENCRYPTION", ""),
        )
        if options.command == "create":
            archive = LocalBackupArchive(options.output)
            manifest = CreateBackup(
                archive,
                database,
                evidence,
                clock=lambda: datetime.now(UTC),
            ).execute()
            _print_manifest_status("created", options.output, manifest)
            return 0

        archive = LocalBackupArchive(options.backup)
        if options.command == "verify":
            manifest = VerifyBackup(archive, database).execute()
            _print_manifest_status("verified", options.backup, manifest)
            return 0

        restore = RestoreBackup(archive, database, evidence)
        if options.command == "restore":
            result = restore.execute(options.database, options.bucket)
            _print_restore_status("restored", result)
            return 0

        suffix = uuid.uuid4().hex[:12]
        result = TestRestore(restore, database, evidence).execute(
            f"governance_restore_{suffix}",
            f"governance-restore-{suffix}",
        )
        _print_restore_status("restore_tested_and_cleaned", result)
        return 0
    except (BackupOperationError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 2


def _integer_environment(name: str, default: int) -> int:
    """Read one bounded adapter integer while reporting invalid deployment config."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _first_environment(*names: str, default: str) -> str:
    """Return the first non-empty environment value from an explicit precedence list."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _print_manifest_status(status: str, path: Path, manifest: BackupManifest) -> None:
    """Print operational evidence without database rows, keys, or credentials."""
    print(
        json.dumps(
            {
                "status": status,
                "backup": str(path.expanduser().absolute()),
                "created_at": manifest.created_at.isoformat(),
                "alembic_revision": manifest.database.alembic_revision,
                "table_count": manifest.database.table_count,
                "evidence_count": len(manifest.evidence),
                "database_evidence_count": manifest.database.evidence_object_count,
            },
            sort_keys=True,
        )
    )


def _print_restore_status(status: str, result: RestoreResult) -> None:
    """Print isolated restore evidence without exposing restored content."""
    print(
        json.dumps(
            {
                "status": status,
                "database": result.database_name,
                "bucket": result.bucket_name,
                "alembic_revision": result.database.alembic_revision,
                "table_count": result.database.table_count,
                "evidence_count": result.evidence_count,
                "database_evidence_count": result.database.evidence_object_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
