"""Core contracts for the coordinated v0.2.0-rc2 release evidence refresh."""

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "1.0"
CANONICALIZATION = "json-sort-keys-compact-v1"
RELEASE_VERSION = "0.2.0-rc2"
CLEAN_INSTALL_KIND = "verifiable-ai-governance/release-clean-install-evidence"
INDEX_KIND = "verifiable-ai-governance/release-candidate-evidence-index"
CLEAN_INSTALL_SCRIPT = "scripts/test_fresh_install_migrations.sh"
CLEAN_INSTALL_LOG = "artifacts/release/clean-install/clean-install-e2e.log"
CLEAN_INSTALL_EVIDENCE = "artifacts/release/clean-install/clean-install-evidence.json"
RELEASE_INDEX = "artifacts/release/release-candidate-evidence-index.json"
RELEASE_SUBJECTS = "artifacts/release/release-candidate-subjects.sha256"
RELEASE_MANIFEST = "artifacts/release/release-manifest.json"
SECURITY_BUNDLE = "artifacts/release/security/security-evidence-bundle.json"
PROVENANCE = "artifacts/release/provenance/release-build-provenance.json"
PROVENANCE_SUBJECTS = "artifacts/release/provenance/release-subjects.sha256"
BENCHMARK_BUNDLE = "artifacts/release/benchmark/runtime-benchmark-bundle.json"
BENCHMARK_RAW = "artifacts/release/benchmark/runtime-benchmark-raw.json"
ATTESTATION_WORKFLOW = ".github/workflows/release-provenance.yml"
FROZEN_COMPONENT_COMMITS = {
    "policy_model_router": "0344f7410fa68fbd8a61fb5d949f5d4dcf0c9166",
    "multi_agent_credit_desk": "b326971bbe7910bd94bd45c0cafbaa11a03f8610",
    "a2a_otel_kit": "a096766fd075868704276777d847c740a17ba821",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_CLEAN_INSTALL_FIELDS = {
    "schema_version",
    "kind",
    "canonicalization",
    "release_version",
    "generated_at",
    "source",
    "test_script",
    "expected_alembic_head",
    "checks",
    "environment",
    "log",
    "verdict",
    "evidence_digest",
}


class ReleaseCandidateEvidenceError(RuntimeError):
    """Raised when coordinated release-candidate evidence is incomplete or inconsistent."""


def canonical_json_bytes(value: object) -> bytes:
    """Serialize JSON using the repository canonicalization contract."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return lowercase SHA-256 for bytes."""
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash one evidence file as raw bytes."""
    return sha256_bytes(path.read_bytes())


def self_digest(document: Mapping[str, object], field: str) -> str:
    """Hash one canonical document while omitting its self-digest field."""
    payload = dict(document)
    payload.pop(field, None)
    return sha256_bytes(canonical_json_bytes(payload))


def verify_self_digest(document: Mapping[str, object], field: str) -> str:
    """Verify and return a lowercase SHA-256 self-digest."""
    observed = document.get(field)
    if not isinstance(observed, str) or not _SHA256_RE.fullmatch(observed):
        raise ReleaseCandidateEvidenceError(f"{field} must be a lowercase SHA-256 digest")
    if self_digest(document, field) != observed:
        raise ReleaseCandidateEvidenceError(f"{field} self-digest mismatch")
    return observed


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk or fail closed."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseCandidateEvidenceError(f"Could not read JSON evidence: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseCandidateEvidenceError(f"JSON evidence root must be an object: {path}")
    return value


def write_json(path: Path, document: Mapping[str, object]) -> None:
    """Write stable pretty JSON without changing canonical digest semantics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def safe_relative_path(value: str) -> PurePosixPath:
    """Reject absolute paths and traversal in evidence references."""
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or not candidate.parts:
        raise ReleaseCandidateEvidenceError(f"Unsafe relative evidence path: {value}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ReleaseCandidateEvidenceError(f"Unsafe relative evidence path: {value}")
    return candidate


def require_clean_worktree(repo: Path) -> None:
    """Require a clean Governance checkout before producing new release evidence."""
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    if completed.stdout.strip():
        raise ReleaseCandidateEvidenceError(
            "Governance worktree must be clean before release evidence generation"
        )


def git_head(repo: Path) -> str:
    """Resolve the current repository HEAD as a full commit SHA."""
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = completed.stdout.strip()
    if not _COMMIT_RE.fullmatch(commit):
        raise ReleaseCandidateEvidenceError(f"Could not resolve a full Git commit for {repo}")
    return commit


def git_blob(repo: Path, commit: str, relative_path: str) -> bytes:
    """Read exact bytes from one tracked path at one immutable Git commit."""
    if not _COMMIT_RE.fullmatch(commit):
        raise ReleaseCandidateEvidenceError(f"Invalid Git commit: {commit}")
    safe_relative_path(relative_path)
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ReleaseCandidateEvidenceError(
            f"Required release-source path is unavailable: {commit}:{relative_path}"
        )
    return completed.stdout


def verify_rc2_component_bindings(manifest: Mapping[str, object]) -> None:
    """Require rc2 to preserve the non-Governance source commits frozen by rc1."""
    components = manifest.get("components")
    if not isinstance(components, dict):
        raise ReleaseCandidateEvidenceError("Release manifest components are missing")
    for component, expected_commit in FROZEN_COMPONENT_COMMITS.items():
        record = components.get(component)
        if not isinstance(record, dict) or record.get("commit") != expected_commit:
            raise ReleaseCandidateEvidenceError(
                f"rc2 component binding changed for {component}; expected {expected_commit}"
            )


def manifest_release_info(manifest: Mapping[str, object]) -> tuple[str, str, str]:
    """Return release version, Governance source commit, and manifest digest."""
    verify_rc2_component_bindings(manifest)
    release = manifest.get("release")
    components = manifest.get("components")
    digest = manifest.get("manifest_digest")
    if not isinstance(release, dict) or not isinstance(components, dict):
        raise ReleaseCandidateEvidenceError("Release manifest roots are missing")
    version = release.get("version")
    governance = components.get("governance")
    if not isinstance(governance, dict):
        raise ReleaseCandidateEvidenceError("Governance release component is missing")
    commit = governance.get("commit")
    if version != RELEASE_VERSION:
        raise ReleaseCandidateEvidenceError(
            f"Expected release {RELEASE_VERSION}, observed {version!r}"
        )
    if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
        raise ReleaseCandidateEvidenceError("Governance release commit is invalid")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise ReleaseCandidateEvidenceError("Release manifest digest is invalid")
    return version, commit, digest


def clean_install_checks(log_text: str, *, expected_head: str = "0019") -> dict[str, bool]:
    """Derive bounded pass/fail checks from the isolated fresh-install execution log."""
    head_marker = f"{expected_head} (head)"
    return {
        "empty_database_precondition": (
            "Fresh-install precondition failed" not in log_text
            and "--- first alembic upgrade head ---" in log_text
        ),
        "first_upgrade_reached_head": log_text.count(head_marker) >= 1,
        "second_upgrade_reached_head": log_text.count(head_marker) >= 2,
        "api_readiness_ok": (
            '"status": "ok"' in log_text
            and '"database": "ok"' in log_text
            and '"schema": "ok"' in log_text
            and '"runtime_control": "ok"' in log_text
        ),
        "script_reported_pass": "P2.0e.1 fresh-install E2E: PASS" in log_text,
    }


def build_clean_install_evidence(
    *,
    manifest: Mapping[str, object],
    governance_repo: Path,
    log_path: Path,
    generated_at: str,
    environment: Mapping[str, object],
) -> dict[str, object]:
    """Build a content-addressed receipt for one exact-source clean-install run."""
    version, source_commit, manifest_digest = manifest_release_info(manifest)
    try:
        log_bytes = log_path.read_bytes()
        log_text = log_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleaseCandidateEvidenceError(
            f"Could not read clean-install log: {log_path}"
        ) from exc
    checks = clean_install_checks(log_text)
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise ReleaseCandidateEvidenceError(f"Clean-install evidence failed checks: {failed}")
    script_bytes = git_blob(governance_repo, source_commit, CLEAN_INSTALL_SCRIPT)
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLEAN_INSTALL_KIND,
        "canonicalization": CANONICALIZATION,
        "release_version": version,
        "generated_at": generated_at,
        "source": {
            "governance_commit": source_commit,
            "release_manifest_digest": manifest_digest,
        },
        "test_script": {
            "path": CLEAN_INSTALL_SCRIPT,
            "sha256": sha256_bytes(script_bytes),
        },
        "expected_alembic_head": "0019",
        "checks": checks,
        "environment": dict(environment),
        "log": {
            "path": CLEAN_INSTALL_LOG,
            "sha256": sha256_bytes(log_bytes),
            "size_bytes": len(log_bytes),
        },
        "verdict": "pass",
    }
    document["evidence_digest"] = self_digest(document, "evidence_digest")
    return document


def verify_clean_install_evidence(
    *,
    evidence_path: Path,
    log_path: Path,
    release_manifest_path: Path,
    governance_repo: Path,
) -> dict[str, Any]:
    """Verify clean-install evidence without rerunning Docker or migrations."""
    evidence = read_json(evidence_path)
    if set(evidence) != _CLEAN_INSTALL_FIELDS:
        raise ReleaseCandidateEvidenceError(
            "Clean-install evidence fields are incomplete or unsupported"
        )
    if evidence.get("schema_version") != SCHEMA_VERSION:
        raise ReleaseCandidateEvidenceError("Unsupported clean-install evidence schema version")
    if evidence.get("kind") != CLEAN_INSTALL_KIND:
        raise ReleaseCandidateEvidenceError("Unexpected clean-install evidence kind")
    if evidence.get("canonicalization") != CANONICALIZATION:
        raise ReleaseCandidateEvidenceError("Unexpected clean-install canonicalization")
    verify_self_digest(evidence, "evidence_digest")
    if evidence.get("verdict") != "pass":
        raise ReleaseCandidateEvidenceError("Clean-install evidence verdict must be pass")
    if evidence.get("expected_alembic_head") != "0019":
        raise ReleaseCandidateEvidenceError("Clean-install Alembic head must be 0019")
    if not isinstance(evidence.get("generated_at"), str):
        raise ReleaseCandidateEvidenceError("Clean-install generated_at is missing")

    manifest = read_json(release_manifest_path)
    version, source_commit, manifest_digest = manifest_release_info(manifest)
    if evidence.get("release_version") != version:
        raise ReleaseCandidateEvidenceError("Clean-install release version does not match manifest")
    source = evidence.get("source")
    if not isinstance(source, dict):
        raise ReleaseCandidateEvidenceError("Clean-install source binding is missing")
    if source.get("governance_commit") != source_commit:
        raise ReleaseCandidateEvidenceError("Clean-install source commit does not match manifest")
    if source.get("release_manifest_digest") != manifest_digest:
        raise ReleaseCandidateEvidenceError("Clean-install manifest digest binding is invalid")

    script = evidence.get("test_script")
    if not isinstance(script, dict) or script.get("path") != CLEAN_INSTALL_SCRIPT:
        raise ReleaseCandidateEvidenceError("Clean-install test script binding is invalid")
    expected_script_digest = sha256_bytes(
        git_blob(governance_repo, source_commit, CLEAN_INSTALL_SCRIPT)
    )
    if script.get("sha256") != expected_script_digest:
        raise ReleaseCandidateEvidenceError("Clean-install test script digest is invalid")

    log = evidence.get("log")
    if not isinstance(log, dict) or log.get("path") != CLEAN_INSTALL_LOG:
        raise ReleaseCandidateEvidenceError("Clean-install log binding is invalid")
    try:
        log_bytes = log_path.read_bytes()
        log_text = log_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleaseCandidateEvidenceError("Clean-install log is unreadable") from exc
    if log.get("sha256") != sha256_bytes(log_bytes) or log.get("size_bytes") != len(log_bytes):
        raise ReleaseCandidateEvidenceError("Clean-install log digest or size mismatch")
    checks = clean_install_checks(
        log_text,
        expected_head=str(evidence.get("expected_alembic_head")),
    )
    if evidence.get("checks") != checks or not all(checks.values()):
        raise ReleaseCandidateEvidenceError("Clean-install derived checks are inconsistent")
    return evidence


def _root_record(path: str, digest: object, *, verdict: object | None = None) -> dict[str, object]:
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise ReleaseCandidateEvidenceError(f"Invalid evidence digest for {path}")
    record: dict[str, object] = {"path": path, "digest": digest}
    if verdict is not None:
        if verdict != "pass":
            raise ReleaseCandidateEvidenceError(f"Evidence verdict is not pass: {path}")
        record["verdict"] = verdict
    return record


def build_release_candidate_index(
    *,
    manifest: Mapping[str, object],
    security: Mapping[str, object],
    provenance: Mapping[str, object],
    benchmark: Mapping[str, object],
    clean_install: Mapping[str, object],
    canonical_demo: Mapping[str, str],
) -> dict[str, object]:
    """Bind all rc2 release-evidence roots into one deterministic final index."""
    version, source_commit, manifest_digest = manifest_release_info(manifest)
    if security.get("release_version") != version:
        raise ReleaseCandidateEvidenceError("Security release version does not match manifest")
    if security.get("release_manifest_digest") != manifest_digest:
        raise ReleaseCandidateEvidenceError("Security evidence does not bind the release manifest")
    if provenance.get("release_version") != version:
        raise ReleaseCandidateEvidenceError("Provenance release version does not match manifest")
    if benchmark.get("release_version") != version:
        raise ReleaseCandidateEvidenceError("Benchmark release version does not match manifest")
    if clean_install.get("release_version") != version:
        raise ReleaseCandidateEvidenceError("Clean-install release version does not match manifest")
    source = clean_install.get("source")
    if not isinstance(source, dict) or source.get("governance_commit") != source_commit:
        raise ReleaseCandidateEvidenceError("Clean-install evidence is not bound to release source")
    expected_identity_fields = {
        "scenario_id",
        "identity_scheme",
        "initiative_id",
        "ai_system_id",
        "approved_model_id",
        "out_of_scope_model_id",
        "agent_id",
    }
    if set(canonical_demo) != expected_identity_fields:
        raise ReleaseCandidateEvidenceError("Canonical demo release identity fields are invalid")
    if canonical_demo.get("identity_scheme") != "uuidv5":
        raise ReleaseCandidateEvidenceError("Canonical demo release identity scheme must be uuidv5")

    roots = {
        "release_manifest": _root_record(RELEASE_MANIFEST, manifest_digest),
        "security_evidence": _root_record(
            SECURITY_BUNDLE,
            security.get("bundle_digest"),
            verdict=security.get("verdict"),
        ),
        "build_provenance": _root_record(PROVENANCE, provenance.get("provenance_digest")),
        "runtime_benchmark": _root_record(
            BENCHMARK_BUNDLE,
            benchmark.get("bundle_digest"),
            verdict=benchmark.get("verdict"),
        ),
        "clean_install": _root_record(
            CLEAN_INSTALL_EVIDENCE,
            clean_install.get("evidence_digest"),
            verdict=clean_install.get("verdict"),
        ),
    }
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": INDEX_KIND,
        "canonicalization": CANONICALIZATION,
        "release_version": version,
        "source_commit": source_commit,
        "roots": roots,
        "canonical_demo": dict(canonical_demo),
        "attestation": {
            "provider": "github-artifact-attestations",
            "action": "actions/attest@v4",
            "workflow_path": ATTESTATION_WORKFLOW,
            "provenance_subject_checksums": PROVENANCE_SUBJECTS,
            "release_candidate_subject_checksums": RELEASE_SUBJECTS,
        },
        "verdict": "pass",
    }
    document["index_digest"] = self_digest(document, "index_digest")
    return document


def verify_release_candidate_index(
    *,
    index: Mapping[str, object],
    manifest: Mapping[str, object],
    security: Mapping[str, object],
    provenance: Mapping[str, object],
    benchmark: Mapping[str, object],
    clean_install: Mapping[str, object],
    canonical_demo: Mapping[str, str],
) -> str:
    """Rebuild the deterministic final index and reject any root drift."""
    if index.get("schema_version") != SCHEMA_VERSION:
        raise ReleaseCandidateEvidenceError("Unsupported release-candidate index schema version")
    if index.get("kind") != INDEX_KIND:
        raise ReleaseCandidateEvidenceError("Unexpected release-candidate index kind")
    if index.get("canonicalization") != CANONICALIZATION:
        raise ReleaseCandidateEvidenceError("Unexpected release-candidate canonicalization")
    observed_digest = verify_self_digest(index, "index_digest")
    expected = build_release_candidate_index(
        manifest=manifest,
        security=security,
        provenance=provenance,
        benchmark=benchmark,
        clean_install=clean_install,
        canonical_demo=canonical_demo,
    )
    if canonical_json_bytes(index) != canonical_json_bytes(expected):
        raise ReleaseCandidateEvidenceError("Release-candidate evidence index does not re-derive")
    return observed_digest


def build_release_candidate_subjects(index_path: Path, repo_root: Path) -> str:
    """Return the single final release-candidate subject checksum row."""
    try:
        relative = index_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ReleaseCandidateEvidenceError("Release index is outside repository root") from exc
    if relative != RELEASE_INDEX:
        raise ReleaseCandidateEvidenceError(f"Unexpected release index path: {relative}")
    return f"{sha256_file(index_path)}  {relative}\n"


def verify_release_candidate_subjects(
    *,
    checksums_path: Path,
    index_path: Path,
    repo_root: Path,
) -> None:
    """Verify the checksum file used by GitHub Artifact Attestation."""
    try:
        observed = checksums_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReleaseCandidateEvidenceError(
            "Release-candidate subject checksums are missing"
        ) from exc
    expected = build_release_candidate_subjects(index_path, repo_root)
    if observed != expected:
        raise ReleaseCandidateEvidenceError("Release-candidate subject checksums are inconsistent")
