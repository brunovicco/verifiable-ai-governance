"""Build and verify Governance Intelligence contracts from external consumer roots."""

import argparse
import ast
import re
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts/governance_intelligence_consumer_probe.py"
FIXTURE = ROOT / "contracts/governance-intelligence/examples/risk-candidate-v1.json"

EXPECTED_PACKAGE_NAME = "governance-schemas"
EXPECTED_RUNTIME_DEPENDENCIES = frozenset({"pydantic"})
FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "ai_governance_api",
        "anthropic",
        "asago",
        "deep_agents",
        "deepagents",
        "langchain",
        "langgraph",
        "openai",
    }
)
CONSUMER_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REQUIREMENT_NAME_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


class CompatibilityFailure(RuntimeError):
    """Represent one deterministic PH-1 compatibility failure."""


@dataclass(frozen=True, slots=True)
class ConsumerRepository:
    """Identify an external repository that consumes the portable contract."""

    name: str
    path: Path


@dataclass(frozen=True, slots=True)
class WheelInspection:
    """Record bounded metadata verified directly from the built wheel."""

    package_name: str
    version: str
    requires_python: str
    dependencies: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Build the PH-1 compatibility command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--consumer-repo",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help=(
            "external consumer repository; may be repeated. When omitted, an ephemeral "
            "empty consumer is used for the repository quality gate."
        ),
    )
    return parser


def parse_consumer_spec(spec: str) -> ConsumerRepository:
    """Parse and validate one NAME=PATH consumer specification."""
    name, separator, raw_path = spec.partition("=")
    name = name.strip()
    raw_path = raw_path.strip()
    if not separator or not name or not raw_path:
        raise CompatibilityFailure(f"invalid consumer specification: {spec!r}")
    if CONSUMER_NAME_PATTERN.fullmatch(name) is None:
        raise CompatibilityFailure(f"invalid consumer name: {name!r}")

    path = Path(raw_path).expanduser().resolve()
    if not path.is_dir():
        raise CompatibilityFailure(f"consumer repository does not exist: {path}")
    if not (path / "pyproject.toml").is_file():
        raise CompatibilityFailure(f"consumer repository has no pyproject.toml: {path}")
    return ConsumerRepository(name=name, path=path)


def parse_consumers(specs: list[str]) -> tuple[ConsumerRepository, ...]:
    """Parse consumer specifications and reject ambiguous names or paths."""
    consumers = tuple(parse_consumer_spec(spec) for spec in specs)
    names = [consumer.name for consumer in consumers]
    paths = [consumer.path for consumer in consumers]
    if len(names) != len(set(names)):
        raise CompatibilityFailure("consumer names must be unique")
    if len(paths) != len(set(paths)):
        raise CompatibilityFailure("consumer repository paths must be unique")
    return consumers


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        rendered = " ".join(command)
        raise CompatibilityFailure(f"command failed ({result.returncode}): {rendered}\n{detail}")
    return result


def build_wheel(output_directory: Path) -> Path:
    """Build exactly one governance-schemas wheel from the current checkout."""
    _run(
        [
            "uv",
            "build",
            "--wheel",
            "--package",
            EXPECTED_PACKAGE_NAME,
            "--out-dir",
            str(output_directory),
        ],
        cwd=ROOT,
    )
    wheels = tuple(sorted(output_directory.glob("*.whl")))
    if len(wheels) != 1:
        raise CompatibilityFailure(f"expected one built wheel, found {len(wheels)}")
    return wheels[0]


def _normalize_package_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _dependency_name(requirement: str) -> str:
    match = REQUIREMENT_NAME_PATTERN.match(requirement)
    if match is None:
        raise CompatibilityFailure(f"could not parse wheel dependency: {requirement!r}")
    return _normalize_package_name(match.group(1))


def _inspect_imports(archive: zipfile.ZipFile, python_members: tuple[str, ...]) -> None:
    for member in python_members:
        try:
            source = archive.read(member).decode("utf-8")
            tree = ast.parse(source, filename=member)
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise CompatibilityFailure(f"could not inspect wheel source {member}: {exc}") from exc

        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        forbidden = sorted(imported_roots & FORBIDDEN_IMPORT_ROOTS)
        if forbidden:
            raise CompatibilityFailure(
                f"wheel source {member} imports forbidden coupling: {', '.join(forbidden)}"
            )


def inspect_wheel(wheel: Path) -> WheelInspection:
    """Verify package contents, metadata, dependencies and import boundaries."""
    try:
        with zipfile.ZipFile(wheel) as archive:
            members = tuple(archive.namelist())
            required = {
                "governance_schemas/__init__.py",
                "governance_schemas/governance_intelligence.py",
            }
            missing = sorted(required - set(members))
            if missing:
                raise CompatibilityFailure(f"wheel is missing required files: {', '.join(missing)}")
            if any(member.startswith("ai_governance_api/") for member in members):
                raise CompatibilityFailure(
                    "wheel contains application-owned ai_governance_api files"
                )

            metadata_members = tuple(
                member for member in members if member.endswith(".dist-info/METADATA")
            )
            if len(metadata_members) != 1:
                raise CompatibilityFailure(
                    f"expected one wheel METADATA file, found {len(metadata_members)}"
                )
            metadata = Parser().parsestr(archive.read(metadata_members[0]).decode("utf-8"))
            package_name = _normalize_package_name(metadata.get("Name", ""))
            version = metadata.get("Version", "")
            requires_python = metadata.get("Requires-Python", "")
            requirements = tuple(metadata.get_all("Requires-Dist", []))
            dependencies = tuple(sorted({_dependency_name(value) for value in requirements}))

            python_members = tuple(
                member
                for member in members
                if member.startswith("governance_schemas/") and member.endswith(".py")
            )
            _inspect_imports(archive, python_members)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CompatibilityFailure(f"could not inspect wheel {wheel}: {exc}") from exc

    if package_name != EXPECTED_PACKAGE_NAME:
        raise CompatibilityFailure(f"unexpected wheel package name: {package_name!r}")
    if not version:
        raise CompatibilityFailure("wheel metadata has no package version")
    if requires_python != ">=3.12":
        raise CompatibilityFailure(f"unexpected Requires-Python boundary: {requires_python!r}")
    if frozenset(dependencies) != EXPECTED_RUNTIME_DEPENDENCIES:
        expected = ", ".join(sorted(EXPECTED_RUNTIME_DEPENDENCIES))
        actual = ", ".join(dependencies) or "none"
        raise CompatibilityFailure(
            f"wheel runtime dependencies changed; expected {expected}, found {actual}"
        )
    return WheelInspection(
        package_name=package_name,
        version=version,
        requires_python=requires_python,
        dependencies=dependencies,
    )


def install_wheel(wheel: Path, target: Path) -> None:
    """Install only the built wheel into an ephemeral target without resolving dependencies."""
    _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--target",
            str(target),
            "--no-deps",
            str(wheel),
        ],
        cwd=ROOT,
    )


def consumer_revision(consumer: ConsumerRepository) -> str:
    """Return a bounded Git revision label without requiring a Git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=consumer.path,
        check=False,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else "unversioned"


def run_consumer_probe(consumer: ConsumerRepository, package_root: Path) -> None:
    """Run the consumer contract checks from one repository in isolated Python mode."""
    result = _run(
        [
            sys.executable,
            "-I",
            str(PROBE),
            "--package-root",
            str(package_root),
            "--fixture",
            str(FIXTURE),
            "--consumer-name",
            consumer.name,
        ],
        cwd=consumer.path,
    )
    print(result.stdout.strip())


def _ephemeral_consumer(root: Path) -> ConsumerRepository:
    path = root / "external-adapter"
    path.mkdir()
    (path / "pyproject.toml").write_text(
        '[project]\nname = "governance-intelligence-external-adapter"\nversion = "0.0.0"\n',
        encoding="utf-8",
    )
    return ConsumerRepository(name="external-adapter", path=path)


def main() -> int:
    """Build the artifact and run the PH-1 gate for every requested consumer."""
    args = build_parser().parse_args()
    try:
        consumers = parse_consumers(args.consumer_repo)
        with tempfile.TemporaryDirectory(prefix="governance-intelligence-ph1-") as raw_temp:
            temporary_root = Path(raw_temp)
            if not consumers:
                consumers = (_ephemeral_consumer(temporary_root),)

            wheel_directory = temporary_root / "wheel"
            wheel_directory.mkdir()
            wheel = build_wheel(wheel_directory)
            inspection = inspect_wheel(wheel)
            install_target = temporary_root / "installed"
            install_wheel(wheel, install_target)

            dependencies = ",".join(inspection.dependencies)
            print(
                f"[ph-1] wheel={wheel.name} package={inspection.package_name} "
                f"version={inspection.version} dependencies={dependencies}"
            )
            for consumer in consumers:
                revision = consumer_revision(consumer)
                run_consumer_probe(consumer, install_target)
                print(f"[ph-1] consumer={consumer.name} revision={revision} PASS")
    except CompatibilityFailure as exc:
        print(f"[ph-1] FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"[ph-1] PASSED consumers={len(consumers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
