"""Docker/PostgreSQL and S3-compatible adapters for operational backups."""

import hashlib
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import IO, Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from ai_governance_api.application.backups import (
    BackupConflictError,
    BackupDependencyError,
    BackupIntegrityError,
)
from ai_governance_api.domain.backups import DatabaseState, EvidenceArtifact

_DATABASE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_BUCKET_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


class DockerComposePostgres:
    """Use PostgreSQL client tools inside the Compose service container."""

    def __init__(
        self,
        source_database: str,
        database_user: str,
        compose_command: tuple[str, ...] = ("docker", "compose"),
        service_name: str = "postgres",
        command_timeout_seconds: int = 1800,
    ) -> None:
        """Initialize explicit command, service, user, and source settings."""
        if not source_database or not database_user:
            raise ValueError("PostgreSQL database and user are required")
        if not 1 <= command_timeout_seconds <= 86400:
            raise ValueError("PostgreSQL backup timeout must be between 1 and 86400 seconds")
        self._source_database = source_database
        self._database_user = database_user
        self._base_command = (*compose_command, "exec", "-T", service_name)
        self._command_timeout_seconds = command_timeout_seconds

    @property
    def source_database(self) -> str:
        """Return the configured source database name."""
        return self._source_database

    def create_dump(self, destination: Path) -> DatabaseState:
        """Create a consistent custom-format logical backup using pg_dump."""
        state = self._inspect_database(self._source_database)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with destination.open("wb") as output:
            self._run(
                (
                    *self._base_command,
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--username",
                    self._database_user,
                    "--dbname",
                    self._source_database,
                ),
                stdout=output,
            )
        destination.chmod(0o600)
        self.verify_dump(destination)
        return state

    def verify_dump(self, source: Path) -> None:
        """Parse the custom-format catalog with the matching pg_restore client."""
        with source.open("rb") as dump:
            self._run(
                (*self._base_command, "pg_restore", "--list"),
                stdin=dump,
                stdout=subprocess.DEVNULL,
            )

    def restore_to_new_database(self, source: Path, target_database: str) -> DatabaseState:
        """Create and restore a database only after proving the target is absent."""
        self._validate_database_name(target_database)
        if self._database_exists(target_database):
            raise BackupConflictError(f"Restore database already exists: {target_database}")

        self._run(
            (
                *self._base_command,
                "createdb",
                "--username",
                self._database_user,
                "--template",
                "template0",
                "--encoding",
                "UTF8",
                target_database,
            )
        )
        try:
            with source.open("rb") as dump:
                self._run(
                    (
                        *self._base_command,
                        "pg_restore",
                        "--exit-on-error",
                        "--no-owner",
                        "--no-privileges",
                        "--username",
                        self._database_user,
                        "--dbname",
                        target_database,
                    ),
                    stdin=dump,
                )
            return self._inspect_database(target_database)
        except Exception:
            self.drop_database(target_database)
            raise

    def drop_database(self, target_database: str) -> None:
        """Drop an explicitly named isolated target with active sessions terminated."""
        self._validate_database_name(target_database)
        if target_database == self._source_database:
            raise BackupConflictError("Refusing to drop the configured source database")
        self._run(
            (
                *self._base_command,
                "dropdb",
                "--if-exists",
                "--force",
                "--username",
                self._database_user,
                target_database,
            )
        )

    def _database_exists(self, database_name: str) -> bool:
        """Query database existence with a strictly validated identifier."""
        self._validate_database_name(database_name)
        value = self._query(
            "postgres",
            f"SELECT 1 FROM pg_database WHERE datname = '{database_name}'",
        )
        return value == "1"

    def _inspect_database(self, database_name: str) -> DatabaseState:
        """Read migration provenance and the public table count."""
        revision = self._query(database_name, "SELECT version_num FROM alembic_version")
        table_count_text = self._query(
            database_name,
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'",
        )
        evidence_object_count_text = self._query(
            database_name,
            "SELECT count(*) FROM evidence WHERE storage_key IS NOT NULL",
        )
        try:
            return DatabaseState(
                alembic_revision=revision,
                table_count=int(table_count_text),
                evidence_object_count=int(evidence_object_count_text),
            )
        except ValueError as exc:
            raise BackupIntegrityError("PostgreSQL returned invalid database state") from exc

    def _query(self, database_name: str, query: str) -> str:
        """Execute a scalar read-only query and return normalized output."""
        result = self._run(
            (
                *self._base_command,
                "psql",
                "--no-psqlrc",
                "--tuples-only",
                "--no-align",
                "--username",
                self._database_user,
                "--dbname",
                database_name,
                "--command",
                query,
            ),
            capture_output=True,
        )
        return result.stdout.strip()

    @staticmethod
    def _validate_database_name(database_name: str) -> None:
        """Allow only unquoted identifiers safe for isolated restore targets."""
        if not _DATABASE_NAME_PATTERN.fullmatch(database_name):
            raise BackupConflictError("Restore database must match ^[a-z][a-z0-9_]{0,62}$")

    def _run(
        self,
        command: Sequence[str],
        *,
        stdin: IO[bytes] | None = None,
        stdout: IO[bytes] | int | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """Run one bounded argument-vector command and sanitize dependency errors."""
        try:
            return subprocess.run(
                command,
                check=True,
                stdin=stdin,
                stdout=stdout,
                capture_output=capture_output,
                text=capture_output,
                timeout=self._command_timeout_seconds,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise BackupDependencyError(
                f"PostgreSQL backup command failed: {Path(command[0]).name} {command[-1]}"
            ) from exc


class S3EvidenceBackup:
    """Stream private evidence objects through an S3-compatible API."""

    def __init__(
        self,
        endpoint_url: str,
        region: str,
        source_bucket: str,
        access_key: str = "",
        secret_key: str = "",
        session_token: str = "",
        client: Any | None = None,
        connect_timeout_seconds: int = 3,
        read_timeout_seconds: int = 30,
        max_attempts: int = 3,
        server_side_encryption: str = "",
    ) -> None:
        """Create an explicit bounded-timeout client without logging credentials."""
        if not source_bucket:
            raise ValueError("Evidence source bucket is required")
        if bool(access_key) != bool(secret_key):
            raise ValueError("S3 access key and secret key must be provided together")
        if not 1 <= connect_timeout_seconds <= 60 or not 1 <= read_timeout_seconds <= 3600:
            raise ValueError("S3 backup timeouts are outside the safety bounds")
        if not 1 <= max_attempts <= 10:
            raise ValueError("S3 backup max attempts must be between 1 and 10")
        self._source_bucket = source_bucket
        self._region = region
        self._server_side_encryption = server_side_encryption
        client_options: dict[str, Any] = {
            "region_name": region,
            "config": Config(
                connect_timeout=connect_timeout_seconds,
                read_timeout=read_timeout_seconds,
                retries={"max_attempts": max_attempts, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
        }
        if endpoint_url:
            client_options["endpoint_url"] = endpoint_url
        if access_key and secret_key:
            client_options["aws_access_key_id"] = access_key
            client_options["aws_secret_access_key"] = secret_key
        if session_token:
            client_options["aws_session_token"] = session_token
        self._client: Any = client or boto3.client("s3", **client_options)

    @property
    def source_bucket(self) -> str:
        """Return the configured private evidence bucket."""
        return self._source_bucket

    def list_keys(self) -> tuple[str, ...]:
        """List all object keys in deterministic lexical order."""
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            keys = [
                str(item["Key"])
                for page in paginator.paginate(Bucket=self._source_bucket)
                for item in page.get("Contents", [])
            ]
            return tuple(sorted(keys))
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"NoSuchBucket", "404", "NotFound"}:
                return ()
            raise BackupDependencyError("Unable to list private evidence objects") from exc
        except BotoCoreError as exc:
            raise BackupDependencyError("Unable to list private evidence objects") from exc

    def download(self, key: str, destination: Path) -> None:
        """Download an object as a private file without buffering full content."""
        try:
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            response = self._client.get_object(Bucket=self._source_bucket, Key=key)
            body = response["Body"]
            try:
                with destination.open("wb") as output:
                    for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)
            finally:
                body.close()
            destination.chmod(0o600)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise BackupDependencyError("Unable to export a private evidence object") from exc

    def restore_to_new_bucket(
        self,
        artifacts: tuple[tuple[EvidenceArtifact, Path], ...],
        target_bucket: str,
    ) -> int:
        """Create an absent bucket, upload every object, and verify full digests."""
        self._validate_target_bucket(target_bucket)
        if self._bucket_exists(target_bucket):
            raise BackupConflictError(f"Restore bucket already exists: {target_bucket}")
        try:
            create_arguments: dict[str, Any] = {"Bucket": target_bucket}
            if self._region != "us-east-1":
                create_arguments["CreateBucketConfiguration"] = {"LocationConstraint": self._region}
            self._client.create_bucket(**create_arguments)
            for artifact, source in artifacts:
                put_arguments: dict[str, Any] = {
                    "Bucket": target_bucket,
                    "Key": artifact.key,
                }
                if self._server_side_encryption:
                    put_arguments["ServerSideEncryption"] = self._server_side_encryption
                with source.open("rb") as content:
                    self._client.put_object(Body=content, **put_arguments)
                if self._remote_sha256(target_bucket, artifact.key) != artifact.file.sha256:
                    raise BackupIntegrityError("Restored evidence checksum does not match manifest")
            return len(artifacts)
        except (BotoCoreError, ClientError, OSError) as exc:
            if self._bucket_exists(target_bucket):
                self.delete_bucket(target_bucket)
            raise BackupDependencyError("Unable to restore private evidence objects") from exc
        except Exception:
            if self._bucket_exists(target_bucket):
                self.delete_bucket(target_bucket)
            raise

    def delete_bucket(self, target_bucket: str) -> None:
        """Delete all objects and the explicitly named non-source bucket."""
        self._validate_target_bucket(target_bucket)
        if target_bucket == self._source_bucket:
            raise BackupConflictError("Refusing to delete the configured source bucket")
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=target_bucket):
                objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if objects:
                    self._client.delete_objects(
                        Bucket=target_bucket,
                        Delete={"Objects": objects, "Quiet": True},
                    )
            self._client.delete_bucket(Bucket=target_bucket)
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code not in {"NoSuchBucket", "404"}:
                raise BackupDependencyError("Unable to clean isolated evidence bucket") from exc
        except BotoCoreError as exc:
            raise BackupDependencyError("Unable to clean isolated evidence bucket") from exc

    def _bucket_exists(self, bucket: str) -> bool:
        """Return bucket existence without treating absence as dependency failure."""
        try:
            self._client.head_bucket(Bucket=bucket)
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"NoSuchBucket", "404", "NotFound"}:
                return False
            raise BackupDependencyError("Unable to verify evidence bucket existence") from exc
        except BotoCoreError as exc:
            raise BackupDependencyError("Unable to verify evidence bucket existence") from exc

    def _remote_sha256(self, bucket: str, key: str) -> str:
        """Stream a restored object to verify content independently of ETags."""
        digest = hashlib.sha256()
        response = self._client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                if chunk:
                    digest.update(chunk)
        finally:
            body.close()
        return digest.hexdigest()

    def _validate_target_bucket(self, target_bucket: str) -> None:
        """Reject ambiguous, invalid, or source-equivalent restore targets."""
        if not _BUCKET_NAME_PATTERN.fullmatch(target_bucket) or ".." in target_bucket:
            raise BackupConflictError("Restore bucket name is not S3-compatible")
        if target_bucket == self._source_bucket:
            raise BackupConflictError("Restore bucket must differ from the configured source")
