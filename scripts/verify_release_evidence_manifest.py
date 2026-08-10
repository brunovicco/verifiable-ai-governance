"""Verify a P2.0a release evidence manifest against its declared Git commits."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.release_evidence_manifest import (
    ReleaseManifestError,
    load_manifest,
    verify_release_manifest,
)


def parse_args() -> argparse.Namespace:
    """Parse release-manifest verification arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("artifacts/release/release-manifest.json"),
    )
    parser.add_argument("--governance-repo", type=Path, default=Path.cwd())
    parser.add_argument("--policy-model-router-repo", type=Path, required=True)
    parser.add_argument("--credit-desk-repo", type=Path, required=True)
    parser.add_argument("--a2a-otel-kit-repo", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Re-derive and verify every trusted manifest field."""
    args = parse_args()
    repos = {
        "governance": args.governance_repo.resolve(),
        "policy_model_router": args.policy_model_router_repo.resolve(),
        "multi_agent_credit_desk": args.credit_desk_repo.resolve(),
        "a2a_otel_kit": args.a2a_otel_kit_repo.resolve(),
    }
    try:
        manifest = load_manifest(args.manifest)
        verify_release_manifest(manifest, repos=repos)
    except ReleaseManifestError as exc:
        print(f"[p2.0a] FAILED: {exc}")
        return 1
    print("[p2.0a] VERIFIED")
    print(f"[p2.0a] manifest: {args.manifest}")
    print(f"[p2.0a] digest: {manifest['manifest_digest']}")
    print(
        "[p2.0a] Git, lockfiles, migrations, provenance, evidence "
        "and compatibility bindings verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
