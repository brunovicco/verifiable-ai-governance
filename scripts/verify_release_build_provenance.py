"""Verify committed P2.0c provenance subjects without network access."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from scripts.generate_release_build_provenance import COMPONENT_ORDER
from scripts.release_build_provenance import (
    ATTESTATION_ACTION,
    ATTESTATION_PREDICATE,
    ATTESTATION_PROVIDER,
    BuildProvenanceError,
    build_checksums,
    deterministic_files_bundle,
    deterministic_git_archive,
    parse_checksums,
    read_files_bundle,
    read_json,
    release_manifest_digest,
    safe_relative_path,
    security_bundle_digest,
    sha256_bytes,
    sha256_file,
    source_bindings_from_manifest,
    source_date_and_version,
    verify_repo_identity,
    verify_self_digest,
)


def _evidence_entries(repo_root: Path) -> list[tuple[str, bytes]]:
    entries: list[tuple[str, bytes]] = [
        (
            "artifacts/release/release-manifest.json",
            (repo_root / "artifacts/release/release-manifest.json").read_bytes(),
        )
    ]
    security_root = repo_root / "artifacts/release/security"
    for path in sorted(security_root.rglob("*")):
        if path.is_file():
            entries.append((path.relative_to(repo_root).as_posix(), path.read_bytes()))
    return entries


def _verify_subject_files(
    repo_root: Path, provenance: dict[str, object], output_dir: Path
) -> list[dict[str, object]]:
    raw_subjects = provenance.get("subjects")
    if not isinstance(raw_subjects, list):
        raise BuildProvenanceError("Provenance subjects are missing")

    subjects: list[dict[str, object]] = []
    for raw in raw_subjects:
        if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
            raise BuildProvenanceError("Malformed provenance subject")
        record: dict[str, object] = {
            key: value for key, value in raw.items() if isinstance(key, str)
        }
        path_value = record.get("path")
        digest = record.get("sha256")
        size = record.get("size_bytes")
        if (
            not isinstance(path_value, str)
            or not isinstance(digest, str)
            or not isinstance(size, int)
        ):
            raise BuildProvenanceError("Malformed provenance subject fields")
        safe_relative_path(path_value)
        path = repo_root / path_value
        try:
            path.resolve().relative_to(output_dir.resolve())
        except ValueError as exc:
            raise BuildProvenanceError(f"Subject is outside provenance root: {path_value}") from exc
        if not path.is_file():
            raise BuildProvenanceError(f"Missing provenance subject: {path_value}")
        if sha256_file(path) != digest or path.stat().st_size != size:
            raise BuildProvenanceError(f"Subject digest/size mismatch: {path_value}")
        subjects.append(record)
    return subjects


def verify(
    *,
    repo_root: Path,
    provenance_path: Path,
    release_manifest_path: Path,
    security_bundle_path: Path,
    governance_source_repo: Path,
    policy_model_router_repo: Path,
    credit_desk_repo: Path,
    a2a_otel_kit_repo: Path,
) -> dict[str, object]:
    """Verify upstream roots, generated artifacts, source archives, and checksums."""
    manifest = read_json(release_manifest_path)
    manifest_digest = release_manifest_digest(manifest)
    source_date, release_version = source_date_and_version(manifest)
    security = read_json(security_bundle_path)
    security_digest = security_bundle_digest(security, manifest_digest)
    if security.get("verdict") != "pass":
        raise BuildProvenanceError("P2.0b security evidence verdict is not pass")

    provenance = read_json(provenance_path)
    if provenance.get("kind") != "verifiable-ai-governance/release-build-provenance":
        raise BuildProvenanceError("Unexpected P2.0c provenance kind")
    verify_self_digest(provenance, "provenance_digest")
    if provenance.get("release_version") != release_version:
        raise BuildProvenanceError("P2.0c release version does not match P2.0a")
    if provenance.get("source_date") != source_date:
        raise BuildProvenanceError("P2.0c source date does not match P2.0a")

    upstream = provenance.get("upstream_roots")
    if not isinstance(upstream, dict):
        raise BuildProvenanceError("P2.0c upstream roots are missing")
    release_root = upstream.get("release_manifest")
    security_root = upstream.get("security_evidence")
    if not isinstance(release_root, dict) or release_root.get("digest") != manifest_digest:
        raise BuildProvenanceError("P2.0c P2.0a root binding is invalid")
    if not isinstance(security_root, dict) or security_root.get("digest") != security_digest:
        raise BuildProvenanceError("P2.0c P2.0b root binding is invalid")
    if security_root.get("policy_digest") != security.get("policy_digest"):
        raise BuildProvenanceError("P2.0c security policy binding is invalid")

    bindings = source_bindings_from_manifest(manifest)
    if provenance.get("source_bindings") != bindings:
        raise BuildProvenanceError("P2.0c source bindings differ from P2.0a")

    attestation = provenance.get("attestation")
    expected_attestation = {
        "action": ATTESTATION_ACTION,
        "predicate_type": ATTESTATION_PREDICATE,
        "provider": ATTESTATION_PROVIDER,
        "signing_identity": "github-actions-oidc-sigstore",
        "subject_mode": "checksums",
        "workflow_path": ".github/workflows/release-provenance.yml",
    }
    if attestation != expected_attestation:
        raise BuildProvenanceError("Unexpected attestation policy")

    output_dir = provenance_path.parent
    subjects = _verify_subject_files(repo_root, provenance, output_dir)

    repos = {
        "governance": governance_source_repo,
        "policy_model_router": policy_model_router_repo,
        "multi_agent_credit_desk": credit_desk_repo,
        "a2a_otel_kit": a2a_otel_kit_repo,
    }
    subject_by_role = {str(item.get("role")): item for item in subjects}
    for name in COMPONENT_ORDER:
        verify_repo_identity(repos[name], bindings[name]["repository"])
        role = f"source_archive:{name}"
        record = subject_by_role.get(role)
        if record is None:
            raise BuildProvenanceError(f"Missing source archive subject: {name}")
        expected_archive = deterministic_git_archive(
            repos[name],
            bindings[name]["commit"],
            f"{name}-{bindings[name]['commit'][:12]}",
        )
        if sha256_bytes(expected_archive) != record.get("sha256"):
            raise BuildProvenanceError(f"Source archive is not reproducible: {name}")

    evidence_record = subject_by_role.get("release_evidence_bundle")
    if evidence_record is None:
        raise BuildProvenanceError("Missing release evidence bundle subject")
    expected_evidence = deterministic_files_bundle(
        _evidence_entries(repo_root), source_date=source_date
    )
    if sha256_bytes(expected_evidence) != evidence_record.get("sha256"):
        raise BuildProvenanceError("Release evidence bundle is not reproducible")

    recipe_record = subject_by_role.get("build_recipe_bundle")
    if recipe_record is None:
        raise BuildProvenanceError("Missing build recipe bundle subject")
    recipe = provenance.get("build_recipe")
    if not isinstance(recipe, dict) or recipe.get("bundle") != recipe_record:
        raise BuildProvenanceError("Build recipe bundle binding is invalid")
    recipe_files = recipe.get("files")
    if not isinstance(recipe_files, list):
        raise BuildProvenanceError("Build recipe file inventory is missing")
    recipe_path_value = recipe_record.get("path")
    if not isinstance(recipe_path_value, str):
        raise BuildProvenanceError("Build recipe bundle path is invalid")
    embedded = read_files_bundle((repo_root / recipe_path_value).read_bytes())
    expected_recipe_paths: set[str] = set()
    for raw in recipe_files:
        if not isinstance(raw, dict):
            raise BuildProvenanceError("Malformed build recipe file record")
        path_value = raw.get("path")
        digest = raw.get("sha256")
        size = raw.get("size_bytes")
        if (
            not isinstance(path_value, str)
            or not isinstance(digest, str)
            or not isinstance(size, int)
        ):
            raise BuildProvenanceError("Malformed build recipe file fields")
        data = embedded.get(path_value)
        if data is None or sha256_bytes(data) != digest or len(data) != size:
            raise BuildProvenanceError(f"Build recipe member mismatch: {path_value}")
        expected_recipe_paths.add(path_value)
    if set(embedded) != expected_recipe_paths:
        raise BuildProvenanceError("Build recipe bundle contains unexpected members")

    checksums_path = output_dir / "release-subjects.sha256"
    if not checksums_path.is_file():
        raise BuildProvenanceError("release-subjects.sha256 is missing")
    observed_rows = parse_checksums(checksums_path.read_text(encoding="utf-8"))
    expected_text = build_checksums(subjects, provenance_path, repo_root)
    expected_rows = parse_checksums(expected_text)
    if observed_rows != expected_rows:
        raise BuildProvenanceError("release-subjects.sha256 is inconsistent")

    return provenance


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provenance",
        type=Path,
        default=Path("artifacts/release/provenance/release-build-provenance.json"),
    )
    parser.add_argument(
        "--release-manifest",
        type=Path,
        default=Path("artifacts/release/release-manifest.json"),
    )
    parser.add_argument(
        "--security-bundle",
        type=Path,
        default=Path("artifacts/release/security/security-evidence-bundle.json"),
    )
    parser.add_argument("--governance-source-repo", type=Path, default=Path("."))
    parser.add_argument("--policy-model-router-repo", type=Path, required=True)
    parser.add_argument("--credit-desk-repo", type=Path, required=True)
    parser.add_argument("--a2a-otel-kit-repo", type=Path, required=True)
    return parser


def main() -> int:
    """CLI entry point."""
    args = _parser().parse_args()
    repo_root = Path.cwd().resolve()
    try:
        provenance = verify(
            repo_root=repo_root,
            provenance_path=args.provenance.resolve(),
            release_manifest_path=args.release_manifest.resolve(),
            security_bundle_path=args.security_bundle.resolve(),
            governance_source_repo=args.governance_source_repo.resolve(),
            policy_model_router_repo=args.policy_model_router_repo.resolve(),
            credit_desk_repo=args.credit_desk_repo.resolve(),
            a2a_otel_kit_repo=args.a2a_otel_kit_repo.resolve(),
        )
    except (BuildProvenanceError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"[p2.0c] FAILED: {exc}")
        return 1

    print("[p2.0c] VERIFIED")
    print(f"[p2.0c] digest: {provenance['provenance_digest']}")
    print("[p2.0c] upstream roots, source archives, recipe, subjects and checksums verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
