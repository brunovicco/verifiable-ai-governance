"""Tests for the PH-1 Governance Intelligence compatibility gate."""

import json
import zipfile
from pathlib import Path

import pytest
from governance_schemas import GovernanceFindingEnvelope

from scripts.verify_governance_intelligence_compatibility import (
    CompatibilityFailure,
    inspect_wheel,
    parse_consumer_spec,
    parse_consumers,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "contracts/governance-intelligence/examples/risk-candidate-v1.json"


def _write_wheel(
    path: Path,
    *,
    dependency: str = "pydantic<3,>=2.11.0",
    package_source: str = "from pydantic import BaseModel\n",
    extra_members: tuple[str, ...] = (),
) -> None:
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: governance-schemas\n"
        "Version: 0.1.0\n"
        "Requires-Python: >=3.12\n"
        f"Requires-Dist: {dependency}\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("governance_schemas/__init__.py", package_source)
        archive.writestr("governance_schemas/governance_intelligence.py", package_source)
        archive.writestr("governance_schemas-0.1.0.dist-info/METADATA", metadata)
        for member in extra_members:
            archive.writestr(member, "")


def test_checked_in_fixture_matches_public_contract() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    envelope = GovernanceFindingEnvelope.model_validate(payload)

    assert envelope.schema_version == "1.0"
    assert envelope.candidate.trust_level == "untrusted"
    assert envelope.candidate.advisory_only is True


def test_consumer_spec_requires_named_python_repository(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    (repository / "pyproject.toml").write_text("[project]\nname = 'consumer'\n", encoding="utf-8")

    consumer = parse_consumer_spec(f"policy-router={repository}")

    assert consumer.name == "policy-router"
    assert consumer.path == repository.resolve()


@pytest.mark.parametrize(
    "spec",
    ["missing-separator", "INVALID NAME=/tmp", "name=/path/that/does/not/exist"],
)
def test_invalid_consumer_spec_is_rejected(spec: str) -> None:
    with pytest.raises(CompatibilityFailure):
        parse_consumer_spec(spec)


def test_duplicate_consumer_is_rejected(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for repository in (first, second):
        repository.mkdir()
        (repository / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")

    with pytest.raises(CompatibilityFailure, match="names must be unique"):
        parse_consumers([f"consumer={first}", f"consumer={second}"])


def test_portable_wheel_metadata_and_source_are_accepted(tmp_path: Path) -> None:
    wheel = tmp_path / "governance_schemas-0.1.0-py3-none-any.whl"
    _write_wheel(wheel)

    inspection = inspect_wheel(wheel)

    assert inspection.package_name == "governance-schemas"
    assert inspection.version == "0.1.0"
    assert inspection.dependencies == ("pydantic",)


@pytest.mark.parametrize("dependency", ["openai>=2", "langgraph>=1"])
def test_provider_or_framework_dependency_is_rejected(tmp_path: Path, dependency: str) -> None:
    wheel = tmp_path / "governance_schemas-0.1.0-py3-none-any.whl"
    _write_wheel(wheel, dependency=dependency)

    with pytest.raises(CompatibilityFailure, match="runtime dependencies changed"):
        inspect_wheel(wheel)


def test_provider_import_is_rejected_even_without_declared_dependency(tmp_path: Path) -> None:
    wheel = tmp_path / "governance_schemas-0.1.0-py3-none-any.whl"
    _write_wheel(wheel, package_source="from langgraph import StateGraph\n")

    with pytest.raises(CompatibilityFailure, match="forbidden coupling: langgraph"):
        inspect_wheel(wheel)


def test_application_package_cannot_leak_into_portable_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "governance_schemas-0.1.0-py3-none-any.whl"
    _write_wheel(wheel, extra_members=("ai_governance_api/application.py",))

    with pytest.raises(CompatibilityFailure, match="application-owned"):
        inspect_wheel(wheel)
