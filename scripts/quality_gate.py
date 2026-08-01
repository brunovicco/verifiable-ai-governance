"""Run the repository-owned, fail-reporting quality gate."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class Check:
    """Describe one deterministic quality command."""

    name: str
    command: tuple[str, ...]


CHECKS = (
    Check("lock", ("uv", "lock", "--check")),
    Check("ruff", (sys.executable, "-m", "ruff", "check", ".")),
    Check(
        "mypy",
        (
            sys.executable,
            "-m",
            "mypy",
            "apps/api/src",
            "packages/governance-schemas/src",
            "packages/policy-engine/src",
        ),
    ),
    Check("pytest", (sys.executable, "-m", "pytest", "-q")),
    Check("web-test", ("npm", "run", "test:web")),
    Check("web-lint", ("npm", "run", "lint:web")),
    Check("web-build", ("npm", "run", "build:web")),
)


def parse_args() -> argparse.Namespace:
    """Parse optional check selection and discovery arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list available checks and exit")
    parser.add_argument(
        "--check",
        action="append",
        choices=[check.name for check in CHECKS],
        help="run only a named check; may be repeated",
    )
    return parser.parse_args()


def run_check(check: Check) -> bool:
    """Run one check and return whether it succeeded."""
    command = " ".join(check.command)
    print(f"\n[{check.name}] {command}", flush=True)
    result = subprocess.run(check.command, cwd=ROOT, check=False)
    outcome = "PASS" if result.returncode == 0 else f"FAIL ({result.returncode})"
    print(f"[{check.name}] {outcome}", flush=True)
    return result.returncode == 0


def main() -> int:
    """Run selected checks, reporting every failure before returning."""
    args = parse_args()
    if args.list:
        for check in CHECKS:
            print(check.name)
        return 0

    selected_names = set(args.check or [])
    selected = [check for check in CHECKS if not selected_names or check.name in selected_names]
    failed = [check.name for check in selected if not run_check(check)]
    if failed:
        print(f"\nQuality gate failed: {', '.join(failed)}", flush=True)
        return 1
    print("\nQuality gate passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
