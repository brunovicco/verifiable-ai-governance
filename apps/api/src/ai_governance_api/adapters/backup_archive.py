"""Private local archive adapter for portable governance backups."""

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from ai_governance_api.application.backups import (
    BackupConflictError,
    BackupIntegrityError,
)
from ai_governance_api.domain.backups import (
    BackupManifest,
    DatabaseArtifact,
    EvidenceArtifact,
    FileArtifact,
    InvalidBackupManifest,
)

_MANIFEST_NAME = "manifest.json"
_MANIFEST_DIGEST_NAME = "manifest.sha256"
_DATABASE_DUMP_NAME = "postgres.dump"
_MAX_MANIFEST_BYTES = 10 * 1024 * 1024


class LocalBackupArchive:
    """Store a backup package privately and publish it with an atomic rename."""

    def __init__(self, root: Path) -> None:
        """Initialize an archive rooted at an explicit non-symlink path."""
        self._root = root.expanduser().absolute()
        self._working_root: Path | None = None

    def prepare(self) -> None:
        """Create a mode-0700 temporary directory beside the final destination."""
        if self._root.exists() or self._root.is_symlink():
            raise BackupConflictError(f"Backup destination already exists: {self._root}")
        self._root.parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.mkdtemp(prefix=f".{self._root.name}.", dir=self._root.parent)
        self._working_root = Path(temporary)
        self._working_root.chmod(0o700)

    def database_destination(self) -> Path:
        """Return the private dump destination within the working archive."""
        return self._active_root() / _DATABASE_DUMP_NAME

    def evidence_destination(self, index: int, key: str) -> Path:
        """Return a path derived from index and a one-way object-key digest."""
        key_digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        destination = self._active_root() / "evidence" / f"{index:06d}-{key_digest}.bin"
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        return destination

    def file_artifact(self, path: Path) -> FileArtifact:
        """Calculate integrity metadata for a regular non-symlink file."""
        root = self._active_root()
        resolved_root = root.resolve(strict=True)
        candidate = self._safe_resolve(root, path)
        if not candidate.is_file() or candidate.is_symlink():
            raise BackupIntegrityError("Backup artifact must be a regular file")
        candidate.chmod(0o600)
        return FileArtifact(
            relative_path=candidate.relative_to(resolved_root).as_posix(),
            sha256=self._sha256(candidate),
            size_bytes=candidate.stat().st_size,
        )

    def finalize(self, manifest: BackupManifest) -> None:
        """Write a canonical manifest and atomically rename the complete archive."""
        working_root = self._require_working_root()
        manifest_path = working_root / _MANIFEST_NAME
        manifest_bytes = self._serialize(manifest)
        manifest_path.write_bytes(manifest_bytes)
        manifest_path.chmod(0o600)

        digest_path = working_root / _MANIFEST_DIGEST_NAME
        digest_path.write_text(f"{hashlib.sha256(manifest_bytes).hexdigest()}\n", encoding="ascii")
        digest_path.chmod(0o600)

        if self._root.exists() or self._root.is_symlink():
            raise BackupConflictError(f"Backup destination appeared during creation: {self._root}")
        os.replace(working_root, self._root)
        self._working_root = None

    def discard(self) -> None:
        """Remove only the private unpublished directory created by this instance."""
        if self._working_root is None:
            return
        working_root = self._working_root
        self._working_root = None
        if working_root.exists() and working_root.parent == self._root.parent:
            shutil.rmtree(working_root)

    def load(self) -> BackupManifest:
        """Load a bounded canonical JSON manifest from a published archive."""
        root = self._published_root()
        manifest_path = root / _MANIFEST_NAME
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise BackupIntegrityError("Backup manifest is missing or is not a regular file")
        if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise BackupIntegrityError("Backup manifest exceeds the safety limit")
        try:
            payload = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
            return self._deserialize(payload)
        except (KeyError, TypeError, ValueError, InvalidBackupManifest) as exc:
            raise BackupIntegrityError("Backup manifest is invalid") from exc

    def verify_files(self, manifest: BackupManifest) -> None:
        """Verify manifest checksum, exact file inventory, modes, sizes, and hashes."""
        root = self._published_root()
        manifest_path = root / _MANIFEST_NAME
        digest_path = root / _MANIFEST_DIGEST_NAME
        if digest_path.is_symlink() or not digest_path.is_file():
            raise BackupIntegrityError("Backup manifest checksum is missing")
        expected_manifest_digest = digest_path.read_text(encoding="ascii").strip()
        if expected_manifest_digest != self._sha256(manifest_path):
            raise BackupIntegrityError("Backup manifest checksum does not match")

        expected_paths = {
            _MANIFEST_NAME,
            _MANIFEST_DIGEST_NAME,
            manifest.database.file.relative_path,
            *(item.file.relative_path for item in manifest.evidence),
        }
        actual_paths = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        if actual_paths != expected_paths:
            raise BackupIntegrityError("Backup archive contains missing or unexpected files")

        artifacts = [manifest.database.file]
        artifacts.extend(item.file for item in manifest.evidence)
        for artifact in artifacts:
            path = self.resolve(artifact)
            if path.is_symlink() or not path.is_file():
                raise BackupIntegrityError("Backup artifact is not a regular file")
            if path.stat().st_size != artifact.size_bytes:
                raise BackupIntegrityError(
                    f"Backup artifact size mismatch: {artifact.relative_path}"
                )
            if self._sha256(path) != artifact.sha256:
                raise BackupIntegrityError(
                    f"Backup artifact checksum mismatch: {artifact.relative_path}"
                )

    def resolve(self, artifact: FileArtifact) -> Path:
        """Resolve a manifest artifact while rejecting traversal and symlinks."""
        root = self._published_root()
        return self._safe_resolve(root, root / artifact.relative_path)

    def _active_root(self) -> Path:
        """Return the working root during creation or the published root otherwise."""
        if self._working_root is not None:
            return self._working_root
        return self._published_root()

    def _published_root(self) -> Path:
        """Return a valid published archive directory."""
        if self._root.is_symlink() or not self._root.is_dir():
            raise BackupIntegrityError(f"Backup archive does not exist: {self._root}")
        return self._root

    def _require_working_root(self) -> Path:
        """Return the unpublished root or reject an invalid lifecycle call."""
        if self._working_root is None:
            raise BackupConflictError("Backup archive was not prepared")
        return self._working_root

    @staticmethod
    def _safe_resolve(root: Path, candidate: Path) -> Path:
        """Resolve a path and prove it remains below the expected archive root."""
        lexical_root = root.absolute()
        lexical_candidate = candidate.absolute()
        try:
            relative = lexical_candidate.relative_to(lexical_root)
        except ValueError as exc:
            raise BackupIntegrityError("Backup artifact escapes the archive root") from exc

        current = lexical_root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise BackupIntegrityError("Backup archive cannot contain symlinks")

        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
        if not resolved_candidate.is_relative_to(resolved_root):
            raise BackupIntegrityError("Backup artifact escapes the archive root")
        return resolved_candidate

    @staticmethod
    def _sha256(path: Path) -> str:
        """Stream a file into a SHA-256 digest without loading it into memory."""
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _serialize(manifest: BackupManifest) -> bytes:
        """Serialize the stable manifest contract as canonical UTF-8 JSON."""
        payload = {
            "format_version": manifest.format_version,
            "created_at": manifest.created_at.isoformat(),
            "source_database": manifest.source_database,
            "source_bucket": manifest.source_bucket,
            "database": {
                "file": LocalBackupArchive._serialize_file(manifest.database.file),
                "alembic_revision": manifest.database.alembic_revision,
                "table_count": manifest.database.table_count,
                "evidence_object_count": manifest.database.evidence_object_count,
            },
            "evidence": [
                {"key": item.key, "file": LocalBackupArchive._serialize_file(item.file)}
                for item in manifest.evidence
            ],
        }
        return (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )

    @staticmethod
    def _serialize_file(artifact: FileArtifact) -> dict[str, str | int]:
        """Serialize one file integrity record."""
        return {
            "relative_path": artifact.relative_path,
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
        }

    @staticmethod
    def _deserialize(payload: dict[str, Any]) -> BackupManifest:
        """Deserialize JSON into the validated immutable domain contract."""
        database_payload = LocalBackupArchive._require_mapping(payload, "database")
        evidence_payload = LocalBackupArchive._require_mapping_list(payload, "evidence")
        return BackupManifest(
            format_version=LocalBackupArchive._require_int(payload, "format_version"),
            created_at=datetime.fromisoformat(
                LocalBackupArchive._require_string(payload, "created_at")
            ),
            source_database=LocalBackupArchive._require_string(payload, "source_database"),
            source_bucket=LocalBackupArchive._require_string(payload, "source_bucket"),
            database=DatabaseArtifact(
                file=LocalBackupArchive._deserialize_file(
                    LocalBackupArchive._require_mapping(database_payload, "file")
                ),
                alembic_revision=LocalBackupArchive._require_string(
                    database_payload, "alembic_revision"
                ),
                table_count=LocalBackupArchive._require_int(database_payload, "table_count"),
                evidence_object_count=LocalBackupArchive._require_int(
                    database_payload, "evidence_object_count"
                ),
            ),
            evidence=tuple(
                EvidenceArtifact(
                    key=LocalBackupArchive._require_string(item, "key"),
                    file=LocalBackupArchive._deserialize_file(
                        LocalBackupArchive._require_mapping(item, "file")
                    ),
                )
                for item in evidence_payload
            ),
        )

    @staticmethod
    def _deserialize_file(payload: dict[str, Any]) -> FileArtifact:
        """Deserialize and validate one artifact record."""
        return FileArtifact(
            relative_path=LocalBackupArchive._require_string(payload, "relative_path"),
            sha256=LocalBackupArchive._require_string(payload, "sha256"),
            size_bytes=LocalBackupArchive._require_int(payload, "size_bytes"),
        )

    @staticmethod
    def _require_string(payload: dict[str, Any], key: str) -> str:
        """Read one exact JSON string without coercing malformed values."""
        value = payload[key]
        if not isinstance(value, str):
            raise TypeError(f"Manifest field {key} must be a string")
        return value

    @staticmethod
    def _require_int(payload: dict[str, Any], key: str) -> int:
        """Read one exact JSON integer while rejecting booleans and strings."""
        value = payload[key]
        if type(value) is not int:
            raise TypeError(f"Manifest field {key} must be an integer")
        return value

    @staticmethod
    def _require_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
        """Read one JSON object without coercing arbitrary values."""
        value = payload[key]
        if not isinstance(value, dict):
            raise TypeError(f"Manifest field {key} must be an object")
        return cast(dict[str, Any], value)

    @staticmethod
    def _require_mapping_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
        """Read one JSON array containing only objects."""
        value = payload[key]
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise TypeError(f"Manifest field {key} must be an array of objects")
        return cast(list[dict[str, Any]], value)
