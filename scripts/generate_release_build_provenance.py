"""Generate deterministic P2.0c build provenance subjects and metadata."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from scripts.release_build_provenance import (
    ATTESTATION_ACTION,
    ATTESTATION_PREDICATE,
    ATTESTATION_PROVIDER,
    CANONICALIZATION,
    KIND,
    RECIPE_FILES,
    SCHEMA_VERSION,
    BuildProvenanceError,
    build_checksums,
    deterministic_files_bundle,
    deterministic_git_archive,
    file_record,
    read_json,
    release_manifest_digest,
    security_bundle_digest,
    self_digest,
    sha256_bytes,
    source_bindings_from_manifest,
    source_date_and_version,
    verify_repo_identity,
    write_bytes,
)

COMPONENT_ORDER = (
    "governance",
    "policy_model_router",
    "multi_agent_credit_desk",
    "a2a_otel_kit",
)


def _git_status_clean(repo: Path) -> None:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    dirty = [
        line
        for line in completed.stdout.splitlines()
        if line and not line.startswith("?? .release-sources/")
    ]
    if dirty:
        raise BuildProvenanceError("Governance worktree must be clean before evidence generation")


def _collect_evidence_entries(repo_root: Path) -> list[tuple[str, bytes]]:
    entries: list[tuple[str, bytes]] = []
    manifest_path = repo_root / "artifacts/release/release-manifest.json"
    entries.append(("artifacts/release/release-manifest.json", manifest_path.read_bytes()))

    security_root = repo_root / "artifacts/release/security"
    if not security_root.is_dir():
        raise BuildProvenanceError("P2.0b security evidence directory is missing")
    for path in sorted(security_root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(repo_root).as_posix()
            entries.append((relative, path.read_bytes()))
    return entries


def _collect_recipe_entries(
    repo_root: Path,
) -> tuple[list[tuple[str, bytes]], list[dict[str, object]]]:
    entries: list[tuple[str, bytes]] = []
    records: list[dict[str, object]] = []
    for relative in RECIPE_FILES:
        path = repo_root / relative
        if not path.is_file():
            raise BuildProvenanceError(f"Build recipe file is missing: {relative}")
        data = path.read_bytes()
        entries.append((relative, data))
        records.append(
            {
                "path": relative,
                "sha256": sha256_bytes(data),
                "size_bytes": len(data),
            }
        )
    return entries, records


def generate(
    *,
    repo_root: Path,
    release_manifest_path: Path,
    security_bundle_path: Path,
    governance_source_repo: Path,
    policy_model_router_repo: Path,
    credit_desk_repo: Path,
    a2a_otel_kit_repo: Path,
    output_dir: Path,
    expected_release_version: str | None,
) -> dict[str, Any]:
    """Generate all deterministic P2.0c subjects and return the provenance object."""
    _git_status_clean(repo_root)

    manifest = read_json(release_manifest_path)
    manifest_digest = release_manifest_digest(manifest)
    source_date, release_version = source_date_and_version(manifest)
    if expected_release_version is not None and release_version != expected_release_version:
        raise BuildProvenanceError(
            "Release version mismatch: "
            f"expected {expected_release_version}, observed {release_version}"
        )

    security = read_json(security_bundle_path)
    security_digest = security_bundle_digest(security, manifest_digest)
    if security.get("verdict") != "pass":
        raise BuildProvenanceError("P2.0b security evidence verdict must be pass")
    policy_digest = security.get("policy_digest")
    if not isinstance(policy_digest, str):
        raise BuildProvenanceError("P2.0b security policy digest is missing")

    bindings = source_bindings_from_manifest(manifest)
    repos = {
        "governance": governance_source_repo,
        "policy_model_router": policy_model_router_repo,
        "multi_agent_credit_desk": credit_desk_repo,
        "a2a_otel_kit": a2a_otel_kit_repo,
    }
    for name in COMPONENT_ORDER:
        verify_repo_identity(repos[name], bindings[name]["repository"])

    if output_dir.exists():
        raise BuildProvenanceError(f"Output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)

    subjects: list[dict[str, object]] = []
    try:
        sources_dir = output_dir / "sources"
        for name in COMPONENT_ORDER:
            binding = bindings[name]
            commit = binding["commit"]
            archive_name = f"{name}-{commit[:12]}.tar.gz"
            archive_path = sources_dir / archive_name
            archive = deterministic_git_archive(
                repos[name],
                commit,
                f"{name}-{commit[:12]}",
            )
            write_bytes(archive_path, archive)
            subjects.append(
                file_record(
                    archive_path,
                    relative_to=repo_root,
                    role=f"source_archive:{name}",
                    media_type="application/gzip",
                )
            )

        evidence_path = output_dir / f"release-evidence-{release_version}.tar.gz"
        write_bytes(
            evidence_path,
            deterministic_files_bundle(
                _collect_evidence_entries(repo_root),
                source_date=source_date,
            ),
        )
        subjects.append(
            file_record(
                evidence_path,
                relative_to=repo_root,
                role="release_evidence_bundle",
                media_type="application/gzip",
            )
        )

        recipe_entries, recipe_files = _collect_recipe_entries(repo_root)
        recipe_path = output_dir / f"build-recipe-{release_version}.tar.gz"
        write_bytes(
            recipe_path,
            deterministic_files_bundle(recipe_entries, source_date=source_date),
        )
        recipe_record = file_record(
            recipe_path,
            relative_to=repo_root,
            role="build_recipe_bundle",
            media_type="application/gzip",
        )
        subjects.append(recipe_record)

        provenance: dict[str, Any] = {
            "attestation": {
                "action": ATTESTATION_ACTION,
                "predicate_type": ATTESTATION_PREDICATE,
                "provider": ATTESTATION_PROVIDER,
                "signing_identity": "github-actions-oidc-sigstore",
                "subject_mode": "checksums",
                "workflow_path": ".github/workflows/release-provenance.yml",
            },
            "build_recipe": {
                "bundle": recipe_record,
                "files": recipe_files,
            },
            "canonicalization": CANONICALIZATION,
            "kind": KIND,
            "provenance_digest": "",
            "release_version": release_version,
            "schema_version": SCHEMA_VERSION,
            "source_bindings": bindings,
            "source_date": source_date,
            "subjects": sorted(subjects, key=lambda item: str(item["path"])),
            "upstream_roots": {
                "release_manifest": {
                    "digest": manifest_digest,
                    "path": "artifacts/release/release-manifest.json",
                },
                "security_evidence": {
                    "digest": security_digest,
                    "path": "artifacts/release/security/security-evidence-bundle.json",
                    "policy_digest": policy_digest,
                },
            },
        }
        provenance["provenance_digest"] = self_digest(provenance, "provenance_digest")

        provenance_path = output_dir / "release-build-provenance.json"
        provenance_path.write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        checksums = build_checksums(subjects, provenance_path, repo_root)
        checksums_path = output_dir / "release-subjects.sha256"
        checksums_path.write_text(checksums, encoding="utf-8")

        return provenance
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
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
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/release/provenance"),
    )
    parser.add_argument("--release-version")
    return parser


def main() -> int:
    """CLI entry point."""
    args = _parser().parse_args()
    repo_root = Path.cwd().resolve()
    try:
        provenance = generate(
            repo_root=repo_root,
            release_manifest_path=args.release_manifest.resolve(),
            security_bundle_path=args.security_bundle.resolve(),
            governance_source_repo=args.governance_source_repo.resolve(),
            policy_model_router_repo=args.policy_model_router_repo.resolve(),
            credit_desk_repo=args.credit_desk_repo.resolve(),
            a2a_otel_kit_repo=args.a2a_otel_kit_repo.resolve(),
            output_dir=args.output_dir.resolve(),
            expected_release_version=args.release_version,
        )
    except (BuildProvenanceError, OSError, subprocess.SubprocessError) as exc:
        print(f"[p2.0c] FAILED: {exc}")
        return 1

    print("[p2.0c] GENERATED")
    print(f"[p2.0c] provenance: {args.output_dir / 'release-build-provenance.json'}")
    print(f"[p2.0c] digest: {provenance['provenance_digest']}")
    print(f"[p2.0c] subjects: {len(provenance['subjects']) + 1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
