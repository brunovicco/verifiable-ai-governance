"""Generate the P2.0a reproducible release evidence manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.release_evidence_manifest import (
    ReleaseManifestError,
    build_release_manifest,
    write_manifest,
)


def parse_args() -> argparse.Namespace:
    """Parse deterministic release-manifest generation arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--governance-repo", type=Path, default=Path.cwd())
    parser.add_argument("--policy-model-router-repo", type=Path, required=True)
    parser.add_argument("--credit-desk-repo", type=Path, required=True)
    parser.add_argument("--a2a-otel-kit-repo", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/release/release-manifest.json"),
    )
    return parser.parse_args()


def main() -> int:
    """Generate one manifest from clean exact Git inputs."""
    args = parse_args()
    repos = {
        "governance": args.governance_repo.resolve(),
        "policy_model_router": args.policy_model_router_repo.resolve(),
        "multi_agent_credit_desk": args.credit_desk_repo.resolve(),
        "a2a_otel_kit": args.a2a_otel_kit_repo.resolve(),
    }
    try:
        manifest = build_release_manifest(
            release_version=args.release_version,
            repos=repos,
            require_clean=True,
        )
        write_manifest(args.output, manifest)
    except ReleaseManifestError as exc:
        print(f"[p2.0a] FAILED: {exc}")
        return 1
    print("[p2.0a] GENERATED")
    print(f"[p2.0a] manifest: {args.output}")
    print(f"[p2.0a] digest: {manifest['manifest_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
