"""Reject public-repository paths that belong to local tooling or generated state."""

import argparse
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_DIRECTORY_NAMES = frozenset(
    {
        ".agents",
        ".claude",
        ".codex",
        ".idea",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "backups",
        "htmlcov",
        "node_modules",
    }
)
FORBIDDEN_FILENAMES = frozenset(
    {
        ".DS_Store",
        ".harness.json",
        "AGENTS.md",
        "CLAUDE.local.md",
        "CLAUDE.md",
    }
)
REQUIRED_GITIGNORE_ENTRIES = (
    ".agents/",
    ".codex/",
    ".claude/",
    ".harness.json",
    "AGENTS.md",
    "CLAUDE.md",
    "CLAUDE.local.md",
    ".idea/",
    ".vscode/*.local.json",
)
REQUIRED_DOCKERIGNORE_ENTRIES = (
    ".agents",
    ".codex",
    ".claude",
    ".harness.json",
    "AGENTS.md",
    "CLAUDE.md",
    "CLAUDE.local.md",
    ".idea",
    ".vscode",
)


def tracked_path_violation(path: str) -> str | None:
    """Return the hygiene violation for one tracked path, if any."""
    pure_path = PurePosixPath(path)
    if any(part in FORBIDDEN_DIRECTORY_NAMES for part in pure_path.parts[:-1]):
        return "local/generated directory is tracked"
    if pure_path.name in FORBIDDEN_FILENAMES:
        return "local tooling/state file is tracked"
    if ".vscode" in pure_path.parts[:-1] and pure_path.name.endswith(".local.json"):
        return "local editor state file is tracked"
    if pure_path.name.startswith(".env") and pure_path.name != ".env.example":
        return "local environment file is tracked"
    if pure_path.suffix in {".pyc", ".pyo"}:
        return "compiled Python artifact is tracked"
    return None


def validate_tracked_paths(paths: Iterable[str]) -> list[str]:
    """Return deterministic violations for tracked repository paths."""
    violations: list[str] = []
    for path in sorted(paths):
        reason = tracked_path_violation(path)
        if reason is not None:
            violations.append(f"{path}: {reason}")
    return violations


def _git_tracked_paths(root: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=False,
    )
    return tuple(value.decode("utf-8") for value in result.stdout.split(b"\0") if value)


def validate_ignore_entries(path: Path, required: Iterable[str]) -> list[str]:
    """Return missing exact ignore entries for one ignore file."""
    if not path.is_file():
        return [f"{path.name}: required ignore file is missing"]
    entries = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return [
        f"{path.name}: missing ignore entry {entry!r}" for entry in required if entry not in entries
    ]


def validate_repository(root: Path) -> list[str]:
    """Validate tracked paths and the repository-owned ignore policy."""
    violations = validate_tracked_paths(_git_tracked_paths(root))
    violations.extend(validate_ignore_entries(root / ".gitignore", REQUIRED_GITIGNORE_ENTRIES))
    violations.extend(
        validate_ignore_entries(root / ".dockerignore", REQUIRED_DOCKERIGNORE_ENTRIES)
    )
    return sorted(violations)


def build_parser() -> argparse.ArgumentParser:
    """Build the repository-hygiene command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Git repository root to validate.",
    )
    return parser


def main() -> int:
    """Run the hygiene gate and return a bounded process status."""
    args = build_parser().parse_args()
    try:
        violations = validate_repository(args.root.resolve())
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as exc:
        print(f"[repository-hygiene] ERROR: {exc}", file=sys.stderr)
        return 2
    if violations:
        print("[repository-hygiene] FAIL", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("[repository-hygiene] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
