"""Verify committed P2.0d runtime benchmark evidence without rerunning the benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.release_runtime_benchmark import RuntimeBenchmarkError, verify_bundle


def parse_args() -> argparse.Namespace:
    """Parse offline benchmark-verification arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("artifacts/release/benchmark/runtime-benchmark-bundle.json"),
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path("artifacts/release/benchmark/runtime-benchmark-raw.json"),
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("config/release-runtime-slo-policy.json"),
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
    parser.add_argument(
        "--provenance",
        type=Path,
        default=Path("artifacts/release/provenance/release-build-provenance.json"),
    )
    parser.add_argument("--governance-repo", type=Path, default=Path("."))
    return parser.parse_args()


def main() -> int:
    """Verify committed P2.0d evidence and report its stored verdict."""
    args = parse_args()
    try:
        bundle = verify_bundle(
            bundle_path=args.bundle,
            raw_path=args.raw,
            policy_path=args.policy,
            release_manifest_path=args.release_manifest,
            security_bundle_path=args.security_bundle,
            provenance_path=args.provenance,
            governance_repo=args.governance_repo,
        )
    except RuntimeBenchmarkError as exc:
        print(f"[p2.0d] FAILED: {exc}")
        return 1
    print("[p2.0d] VERIFIED")
    print(f"[p2.0d] verdict: {bundle['verdict']}")
    print(f"[p2.0d] digest: {bundle['bundle_digest']}")
    print("[p2.0d] roots, raw timings, summaries, SLOs and runtime equivalence verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
