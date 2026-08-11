"""Generate the rc2 release manifest while preserving frozen sibling component commits."""

import argparse
from pathlib import Path

from scripts.release_candidate_evidence import FROZEN_COMPONENT_COMMITS, RELEASE_VERSION
from scripts.release_evidence_manifest import (
    ReleaseManifestError,
    build_release_manifest,
    write_manifest,
)


def parse_args() -> argparse.Namespace:
    """Parse exact repository paths used by the rc2 manifest generator."""
    parser = argparse.ArgumentParser(description=__doc__)
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
    """Generate one rc2 manifest with only Governance intentionally advanced."""
    args = parse_args()
    repos = {
        "governance": args.governance_repo.resolve(),
        "policy_model_router": args.policy_model_router_repo.resolve(),
        "multi_agent_credit_desk": args.credit_desk_repo.resolve(),
        "a2a_otel_kit": args.a2a_otel_kit_repo.resolve(),
    }
    refs = {
        "governance": "HEAD",
        **FROZEN_COMPONENT_COMMITS,
    }
    try:
        manifest = build_release_manifest(
            release_version=RELEASE_VERSION,
            repos=repos,
            refs=refs,
            require_clean=True,
        )
        write_manifest(args.output, manifest)
    except ReleaseManifestError as exc:
        print(f"[p2.0e.3-manifest] FAILED: {exc}")
        return 1
    print("[p2.0e.3-manifest] GENERATED")
    print(f"[p2.0e.3-manifest] release: {RELEASE_VERSION}")
    print(f"[p2.0e.3-manifest] governance: {manifest['components']['governance']['commit']}")
    print(f"[p2.0e.3-manifest] digest: {manifest['manifest_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
