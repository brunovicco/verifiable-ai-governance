"""Generate the deterministic P2.0e.3 rc2 evidence index after all child evidence commits."""

import argparse
import subprocess
from pathlib import Path

from scripts.canonical_demo_contract import canonical_demo_release_record
from scripts.release_build_provenance import BuildProvenanceError
from scripts.release_candidate_evidence import (
    BENCHMARK_BUNDLE,
    CLEAN_INSTALL_EVIDENCE,
    CLEAN_INSTALL_LOG,
    PROVENANCE,
    RELEASE_INDEX,
    RELEASE_MANIFEST,
    RELEASE_SUBJECTS,
    SECURITY_BUNDLE,
    ReleaseCandidateEvidenceError,
    build_release_candidate_index,
    build_release_candidate_subjects,
    require_clean_worktree,
    verify_clean_install_evidence,
    write_json,
)
from scripts.release_evidence_manifest import (
    ReleaseManifestError,
    load_manifest,
    verify_release_manifest,
)
from scripts.release_runtime_benchmark import (
    RuntimeBenchmarkError,
)
from scripts.release_runtime_benchmark import (
    verify_bundle as verify_runtime_benchmark,
)
from scripts.release_security_evidence import (
    SecurityEvidenceError,
)
from scripts.release_security_evidence import (
    verify_bundle as verify_security_bundle,
)
from scripts.verify_release_build_provenance import verify as verify_build_provenance


def parse_args() -> argparse.Namespace:
    """Parse repository paths and final evidence output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--governance-repo", type=Path, default=Path("."))
    parser.add_argument("--policy-model-router-repo", type=Path, required=True)
    parser.add_argument("--credit-desk-repo", type=Path, required=True)
    parser.add_argument("--a2a-otel-kit-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(RELEASE_INDEX))
    parser.add_argument("--subjects", type=Path, default=Path(RELEASE_SUBJECTS))
    return parser.parse_args()


def main() -> int:
    """Deep-verify child evidence and generate the final rc2 evidence root."""
    args = parse_args()
    repo = args.governance_repo.resolve()
    repos = {
        "governance": repo,
        "policy_model_router": args.policy_model_router_repo.resolve(),
        "multi_agent_credit_desk": args.credit_desk_repo.resolve(),
        "a2a_otel_kit": args.a2a_otel_kit_repo.resolve(),
    }
    try:
        require_clean_worktree(repo)
        if args.output.exists() or args.subjects.exists():
            raise ReleaseCandidateEvidenceError(
                "Release-candidate index already exists; preserve it or remove it explicitly"
            )
        manifest_path = repo / RELEASE_MANIFEST
        security_path = repo / SECURITY_BUNDLE
        provenance_path = repo / PROVENANCE
        benchmark_path = repo / BENCHMARK_BUNDLE
        clean_path = repo / CLEAN_INSTALL_EVIDENCE
        clean_log = repo / CLEAN_INSTALL_LOG

        manifest = load_manifest(manifest_path)
        verify_release_manifest(manifest, repos=repos)
        security = verify_security_bundle(
            security_path,
            manifest_path,
            repo / "config/release-security-policy.json",
        )
        provenance = verify_build_provenance(
            repo_root=repo,
            provenance_path=provenance_path,
            release_manifest_path=manifest_path,
            security_bundle_path=security_path,
            governance_source_repo=repo,
            policy_model_router_repo=repos["policy_model_router"],
            credit_desk_repo=repos["multi_agent_credit_desk"],
            a2a_otel_kit_repo=repos["a2a_otel_kit"],
        )
        benchmark = verify_runtime_benchmark(
            bundle_path=benchmark_path,
            raw_path=repo / "artifacts/release/benchmark/runtime-benchmark-raw.json",
            policy_path=repo / "config/release-runtime-slo-policy.json",
            release_manifest_path=manifest_path,
            security_bundle_path=security_path,
            provenance_path=provenance_path,
            governance_repo=repo,
        )
        clean_install = verify_clean_install_evidence(
            evidence_path=clean_path,
            log_path=clean_log,
            release_manifest_path=manifest_path,
            governance_repo=repo,
        )
        index = build_release_candidate_index(
            manifest=manifest,
            security=security,
            provenance=provenance,
            benchmark=benchmark,
            clean_install=clean_install,
            canonical_demo=canonical_demo_release_record(),
        )
        write_json(args.output, index)
        args.subjects.parent.mkdir(parents=True, exist_ok=True)
        args.subjects.write_text(
            build_release_candidate_subjects(args.output, repo),
            encoding="utf-8",
        )
    except (
        ReleaseCandidateEvidenceError,
        ReleaseManifestError,
        BuildProvenanceError,
        SecurityEvidenceError,
        RuntimeBenchmarkError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        print(f"[p2.0e.3] FAILED: {exc}")
        return 1
    print("[p2.0e.3] GENERATED")
    print(f"[p2.0e.3] index: {args.output}")
    print(f"[p2.0e.3] digest: {index['index_digest']}")
    print(f"[p2.0e.3] attestation subjects: {args.subjects}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
