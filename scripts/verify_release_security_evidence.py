"""Offline verifier for P2.0b release security evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.release_security_evidence import SecurityEvidenceError, verify_bundle


def build_parser() -> argparse.ArgumentParser:
    """Build the offline verifier CLI."""
    parser = argparse.ArgumentParser(description="Verify P2.0b release security evidence")
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("artifacts/release/security/security-evidence-bundle.json"),
    )
    parser.add_argument(
        "--release-manifest",
        type=Path,
        default=Path("artifacts/release/release-manifest.json"),
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("config/release-security-policy.json"),
    )
    return parser


def main() -> int:
    """Verify hashes, bindings, raw reports, summaries, and policy verdict."""
    args = build_parser().parse_args()
    try:
        bundle = verify_bundle(args.bundle, args.release_manifest, args.policy)
    except (SecurityEvidenceError, OSError, ValueError) as exc:
        print(f"[p2.0b] FAILED: {exc}", file=sys.stderr)
        return 2
    print("[p2.0b] VERIFIED")
    print(f"[p2.0b] bundle: {args.bundle}")
    print(f"[p2.0b] digest: {bundle['bundle_digest']}")
    print(f"[p2.0b] verdict: {bundle['verdict']}")
    print("[p2.0b] release root, artifact hashes, raw scans, summaries and policy verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
