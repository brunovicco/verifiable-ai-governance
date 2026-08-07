"""CLI for creating, checking or explicitly resetting the canonical demo."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from scripts.canonical_demo_seed import (
    RESET_CONFIRMATION,
    CanonicalDemoDriftError,
    DemoResetRefused,
    ensure_canonical_demo,
    inspect_canonical_demo,
    reset_application_data,
    write_summary,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded canonical-demo command-line interface."""
    parser = argparse.ArgumentParser(
        description=(
            "Create or validate the canonical governed credit demo. "
            "Reruns are idempotent."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the existing scenario without creating it.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Delete all application data before seeding. Intended only for a "
            "dedicated non-production demo database."
        ),
    )
    parser.add_argument(
        "--confirm-reset",
        default="",
        metavar="PHRASE",
        help=f"Required with --reset: {RESET_CONFIRMATION}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/demo/canonical-seed-manifest.json"),
        help="Path for the generated runtime manifest.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print only the JSON summary.",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    """Execute the selected idempotent seed operation."""
    if args.check and args.reset:
        raise ValueError("--check and --reset cannot be used together")

    if args.reset:
        await reset_application_data(confirmation=args.confirm_reset)

    if args.check:
        summary = await inspect_canonical_demo()
        if summary is None:
            raise CanonicalDemoDriftError(
                "Canonical demo is absent; run make seed-demo"
            )
    else:
        summary = await ensure_canonical_demo()

    write_summary(summary, args.output)
    payload = json.dumps(
        summary.to_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.json:
        print(payload)
    else:
        print(
            f"[seed-demo] scenario={summary.scenario_id} "
            f"version={summary.scenario_version} state={summary.state}"
        )
        print(
            "[seed-demo] allowed routing decision: "
            f"{summary.allowed_routing_decision_id}"
        )
        print(
            "[seed-demo] blocked routing decision: "
            f"{summary.blocked_routing_decision_id}"
        )
        print(f"[seed-demo] incident: {summary.incident_id}")
        print(f"[seed-demo] manifest: {args.output}")
    return 0


def main() -> int:
    """Parse arguments and map bounded operational failures to exit codes."""
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except (CanonicalDemoDriftError, DemoResetRefused, ValueError) as exc:
        print(f"[seed-demo] error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
