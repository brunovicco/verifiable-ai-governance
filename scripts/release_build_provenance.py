"""Deterministic helpers for P2.0c release build provenance."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

CANONICALIZATION = "json-sort-keys-compact-v1"
KIND = "verifiable-ai-governance/release-build-provenance"
SCHEMA_VERSION = "1.0"
ATTESTATION_PROVIDER = "github-artifact-attestations"
ATTESTATION_ACTION = "actions/attest@v4"
ATTESTATION_PREDICATE = "https://slsa.dev/provenance/v1"

RECIPE_FILES: tuple[str, ...] = (
    ".github/workflows/release-provenance.yml",
    "schemas/release-build-provenance.schema.json",
    "scripts/release_build_provenance.py",
    "scripts/generate_release_build_provenance.py",
    "scripts/verify_release_build_provenance.py",
)


class BuildProvenanceError(RuntimeError):
    """Raised when deterministic provenance evidence cannot be trusted."""


def canonical_json_bytes(value: object) -> bytes:
    """Serialize JSON using the project canonicalization contract."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 hex digest."""
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash one file as raw bytes."""
    return sha256_bytes(path.read_bytes())


def file_record(path: Path, *, relative_to: Path, role: str, media_type: str) -> dict[str, object]:
    """Describe one generated subject without embedding its contents."""
    resolved = path.resolve()
    base = relative_to.resolve()
    try:
        relative = resolved.relative_to(base)
    except ValueError as exc:
        raise BuildProvenanceError(f"Subject escapes provenance root: {path}") from exc
    return {
        "media_type": media_type,
        "path": relative.as_posix(),
        "role": role,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def safe_relative_path(value: str) -> PurePosixPath:
    """Reject absolute or traversal paths in evidence contracts."""
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or not candidate.parts:
        raise BuildProvenanceError(f"Unsafe relative path: {value}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise BuildProvenanceError(f"Unsafe relative path: {value}")
    return candidate


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildProvenanceError(f"Cannot read JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise BuildProvenanceError(f"Expected JSON object: {path}")
    return value


def self_digest(document: Mapping[str, object], field: str) -> str:
    """Compute a canonical digest after omitting one self-digest field."""
    payload = dict(document)
    payload.pop(field, None)
    return sha256_bytes(canonical_json_bytes(payload))


def verify_self_digest(document: Mapping[str, object], field: str) -> str:
    """Verify a canonical self-digest and return it."""
    observed = document.get(field)
    if not isinstance(observed, str) or len(observed) != 64:
        raise BuildProvenanceError(f"Missing or malformed {field}")
    expected = self_digest(document, field)
    if observed != expected:
        raise BuildProvenanceError(f"Invalid {field}: expected {expected}, observed {observed}")
    return observed


def release_manifest_digest(manifest: Mapping[str, object]) -> str:
    """Verify and return the P2.0a manifest digest."""
    kind = manifest.get("kind")
    if kind != "verifiable-ai-governance/release-evidence-manifest":
        raise BuildProvenanceError("Unexpected P2.0a manifest kind")
    return verify_self_digest(manifest, "manifest_digest")


def security_bundle_digest(bundle: Mapping[str, object], manifest_digest: str) -> str:
    """Verify and return the P2.0b bundle digest and upstream binding."""
    kind = bundle.get("kind")
    if kind != "verifiable-ai-governance/release-security-evidence":
        raise BuildProvenanceError("Unexpected P2.0b security bundle kind")
    observed_manifest = bundle.get("release_manifest_digest")
    if observed_manifest != manifest_digest:
        raise BuildProvenanceError(
            "P2.0b security evidence is not bound to the supplied P2.0a manifest"
        )
    return verify_self_digest(bundle, "bundle_digest")


def _run_git_text(repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    completed = subprocess.run(
        command,
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise BuildProvenanceError(
            f"Git command failed in {repo}: {' '.join(command)}: {completed.stderr.strip()}"
        )
    return completed


def _run_git_bytes(repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    command = ["git", *args]
    completed = subprocess.run(
        command,
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise BuildProvenanceError(
            f"Git command failed in {repo}: {' '.join(command)}: {stderr.strip()}"
        )
    return completed


def require_commit(repo: Path, commit: str) -> None:
    """Require one exact commit to be available locally."""
    _run_git_text(repo, ["cat-file", "-e", f"{commit}^{{commit}}"])


def normalized_remote(repo: Path) -> str:
    """Return owner/name for common GitHub origin URL forms."""
    completed = _run_git_text(repo, ["config", "--get", "remote.origin.url"])
    raw = completed.stdout.strip()
    prefixes = (
        "https://github.com/",
        "http://github.com/",
        "ssh://git@github.com/",
        "git@github.com:",
    )
    for prefix in prefixes:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    if raw.endswith(".git"):
        raw = raw[:-4]
    if raw.count("/") != 1:
        raise BuildProvenanceError(f"Unsupported GitHub origin URL: {raw}")
    return raw


def verify_repo_identity(repo: Path, expected: str) -> None:
    """Fail closed if a local checkout is not the declared repository."""
    observed = normalized_remote(repo)
    if observed != expected:
        raise BuildProvenanceError(
            f"Repository identity mismatch for {repo}: expected {expected}, observed {observed}"
        )


def deterministic_git_archive(repo: Path, commit: str, prefix: str) -> bytes:
    """Return a reproducible gzip-compressed Git archive for one exact commit."""
    require_commit(repo, commit)
    clean_prefix = prefix.strip("/") + "/"
    completed = _run_git_bytes(
        repo,
        ["archive", "--format=tar", f"--prefix={clean_prefix}", commit],
    )
    tar_bytes = completed.stdout
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as gz:
        gz.write(tar_bytes)
    return output.getvalue()


def _epoch_from_iso8601(value: str) -> int:
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError as exc:
        raise BuildProvenanceError(f"Invalid source_date: {value}") from exc


def deterministic_files_bundle(entries: Iterable[tuple[str, bytes]], *, source_date: str) -> bytes:
    """Build a stable tar.gz from explicit path/byte entries."""
    epoch = _epoch_from_iso8601(source_date)
    normalized: list[tuple[str, bytes]] = []
    for name, data in entries:
        path = safe_relative_path(name)
        normalized.append((path.as_posix(), data))
    normalized.sort(key=lambda item: item[0])

    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name, data in normalized:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = epoch
            archive.addfile(info, io.BytesIO(data))

    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as gz:
        gz.write(tar_buffer.getvalue())
    return output.getvalue()


def read_files_bundle(data: bytes) -> dict[str, bytes]:
    """Read a deterministic files bundle while rejecting unsafe tar members."""
    extracted: dict[str, bytes] = {}
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as gz:
            tar_bytes = gz.read()
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    raise BuildProvenanceError(f"Unexpected non-file bundle member: {member.name}")
                name = safe_relative_path(member.name).as_posix()
                if name in extracted:
                    raise BuildProvenanceError(f"Duplicate bundle member: {name}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise BuildProvenanceError(f"Cannot read bundle member: {name}")
                extracted[name] = handle.read()
    except (OSError, tarfile.TarError, EOFError) as exc:
        raise BuildProvenanceError("Cannot read deterministic files bundle") from exc
    return extracted


def write_bytes(path: Path, data: bytes) -> None:
    """Create parent directories and write exact bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def source_bindings_from_manifest(manifest: Mapping[str, object]) -> dict[str, dict[str, str]]:
    """Extract the immutable cross-repository source bindings from P2.0a."""
    components = manifest.get("components")
    if not isinstance(components, dict):
        raise BuildProvenanceError("P2.0a manifest components are missing")

    bindings: dict[str, dict[str, str]] = {}
    for name in (
        "governance",
        "policy_model_router",
        "multi_agent_credit_desk",
        "a2a_otel_kit",
    ):
        raw = components.get(name)
        if not isinstance(raw, dict):
            raise BuildProvenanceError(f"Missing P2.0a component: {name}")
        repository = raw.get("repository")
        commit = raw.get("commit")
        lockfile = raw.get("lockfile")
        if not isinstance(repository, str) or not isinstance(commit, str):
            raise BuildProvenanceError(f"Malformed P2.0a component: {name}")
        if not isinstance(lockfile, dict) or not isinstance(lockfile.get("sha256"), str):
            raise BuildProvenanceError(f"Malformed P2.0a lockfile binding: {name}")
        bindings[name] = {
            "commit": commit,
            "lockfile_sha256": str(lockfile["sha256"]),
            "repository": repository,
        }
    return bindings


def source_date_and_version(manifest: Mapping[str, object]) -> tuple[str, str]:
    """Read the frozen release source date and version."""
    release = manifest.get("release")
    if not isinstance(release, dict):
        raise BuildProvenanceError("P2.0a release metadata is missing")
    source_date = release.get("source_date")
    version = release.get("version")
    if not isinstance(source_date, str) or not isinstance(version, str):
        raise BuildProvenanceError("Malformed P2.0a release metadata")
    _epoch_from_iso8601(source_date)
    return source_date, version


def build_checksums(
    records: Sequence[Mapping[str, object]], provenance_path: Path, root: Path
) -> str:
    """Render a deterministic sha256sum-compatible subject manifest."""
    rows: list[tuple[str, str]] = []
    for record in records:
        digest = record.get("sha256")
        path = record.get("path")
        if not isinstance(digest, str) or not isinstance(path, str):
            raise BuildProvenanceError("Malformed subject record")
        safe_relative_path(path)
        rows.append((path, digest))

    provenance_relative = provenance_path.resolve().relative_to(root.resolve()).as_posix()
    rows.append((provenance_relative, sha256_file(provenance_path)))
    rows.sort(key=lambda item: item[0])
    return "".join(f"{digest}  {path}\n" for path, digest in rows)


def parse_checksums(value: str) -> list[tuple[str, str]]:
    """Parse the constrained checksum format emitted by build_checksums."""
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in value.splitlines():
        if not line:
            continue
        if "  " not in line:
            raise BuildProvenanceError("Malformed release subject checksum line")
        digest, path = line.split("  ", 1)
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise BuildProvenanceError(f"Malformed SHA-256 in checksum line: {line}")
        safe_relative_path(path)
        if path in seen:
            raise BuildProvenanceError(f"Duplicate subject path: {path}")
        seen.add(path)
        rows.append((path, digest))
    return rows
