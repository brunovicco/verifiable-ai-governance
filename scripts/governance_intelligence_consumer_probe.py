"""Exercise the Governance Intelligence contract from an installed wheel target."""

import argparse
import copy
import importlib
import importlib.metadata
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from pydantic import ValidationError

PUBLIC_EXPORTS = frozenset(
    {
        "AgentRunProvenance",
        "ExternalTaxonomyReference",
        "GOVERNANCE_FINDING_SCHEMA_VERSION",
        "GovernanceFindingCandidate",
        "GovernanceFindingEnvelope",
        "GovernanceFindingType",
        "GovernanceSourceReference",
        "SUPPORTED_GOVERNANCE_FINDING_SCHEMA_VERSIONS",
        "UnsupportedGovernanceFindingSchemaVersion",
        "parse_governance_finding",
    }
)
AUTHORITY_FIELDS = frozenset(
    {
        "approval_status",
        "approved",
        "authorization_status",
        "authorized",
        "compliant",
        "control_approved",
        "release_authorized",
        "runtime_authorized",
    }
)
CONTENT_DUMP_FIELDS = frozenset(
    {
        "chain_of_thought",
        "document_body",
        "document_content",
        "full_prompt",
        "model_response",
    }
)


class ProbeFailure(RuntimeError):
    """Represent one consumer-visible compatibility failure."""


def build_parser() -> argparse.ArgumentParser:
    """Build the isolated consumer probe command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package-root",
        required=True,
        type=Path,
        help="Temporary target containing the wheel installation.",
    )
    parser.add_argument(
        "--fixture",
        required=True,
        type=Path,
        help="Checked-in Governance Finding v1 fixture.",
    )
    parser.add_argument(
        "--consumer-name",
        required=True,
        help="Stable consumer name reported with the result.",
    )
    return parser


def _load_installed_package(package_root: Path) -> tuple[ModuleType, Path]:
    resolved_root = package_root.resolve()
    if not resolved_root.is_dir():
        raise ProbeFailure(f"installed package root does not exist: {resolved_root}")

    sys.path.insert(0, str(resolved_root))
    package = importlib.import_module("governance_schemas")
    if package.__file__ is None:
        raise ProbeFailure("governance_schemas has no import origin")

    origin = Path(package.__file__).resolve()
    try:
        origin.relative_to(resolved_root)
    except ValueError as exc:
        raise ProbeFailure(
            f"governance_schemas was not imported from the wheel target: {origin}"
        ) from exc

    missing_exports = sorted(name for name in PUBLIC_EXPORTS if not hasattr(package, name))
    if missing_exports:
        raise ProbeFailure(f"public contract exports are missing: {', '.join(missing_exports)}")
    return package, origin


def _load_fixture(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeFailure(f"could not read fixture {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProbeFailure("fixture must be a JSON object")
    return payload


def _installed_distribution_version(package_root: Path) -> str:
    distributions = tuple(importlib.metadata.distributions(path=[str(package_root.resolve())]))
    matching = tuple(
        distribution
        for distribution in distributions
        if distribution.metadata.get("Name", "").lower().replace("_", "-")
        == "governance-schemas"
    )
    if len(matching) != 1:
        raise ProbeFailure(
            "wheel target must contain exactly one governance-schemas distribution, "
            f"found {len(matching)}"
        )
    return matching[0].version


def _candidate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("candidate")
    if not isinstance(candidate, dict):
        raise ProbeFailure("fixture candidate must be a JSON object")
    return candidate


def _expect_rejected(model: Any, payload: dict[str, Any], reason: str) -> None:
    try:
        model.model_validate(payload)
    except ValidationError:
        return
    raise ProbeFailure(f"contract accepted forbidden mutation: {reason}")


def _verify_closed_authority_boundary(package: ModuleType, payload: dict[str, Any]) -> None:
    envelope_type = package.GovernanceFindingEnvelope
    candidate_type = package.GovernanceFindingCandidate
    provenance_type = package.AgentRunProvenance
    source_type = package.GovernanceSourceReference

    candidate_fields = frozenset(candidate_type.model_fields)
    if candidate_fields & AUTHORITY_FIELDS:
        unexpected = ", ".join(sorted(candidate_fields & AUTHORITY_FIELDS))
        raise ProbeFailure(f"candidate exposes authority fields: {unexpected}")

    provenance_fields = frozenset(provenance_type.model_fields)
    source_fields = frozenset(source_type.model_fields)
    dumped_fields = (candidate_fields | provenance_fields | source_fields) & CONTENT_DUMP_FIELDS
    if dumped_fields:
        rendered_fields = ", ".join(sorted(dumped_fields))
        raise ProbeFailure(f"contract exposes content-dump fields: {rendered_fields}")

    for field in sorted(AUTHORITY_FIELDS):
        mutated = copy.deepcopy(payload)
        _candidate_payload(mutated)[field] = True
        _expect_rejected(envelope_type, mutated, field)

    trusted = copy.deepcopy(payload)
    _candidate_payload(trusted)["trust_level"] = "trusted"
    _expect_rejected(envelope_type, trusted, "trust_level=trusted")

    authoritative = copy.deepcopy(payload)
    _candidate_payload(authoritative)["advisory_only"] = False
    _expect_rejected(envelope_type, authoritative, "advisory_only=false")

    overconfident = copy.deepcopy(payload)
    _candidate_payload(overconfident)["confidence"] = 1.01
    _expect_rejected(envelope_type, overconfident, "confidence>1")


def run_probe(package_root: Path, fixture: Path, consumer_name: str) -> dict[str, object]:
    """Run the portable contract assertions and return a bounded result."""
    package, origin = _load_installed_package(package_root)
    payload = _load_fixture(fixture)
    envelope = package.parse_governance_finding(payload)

    if package.GOVERNANCE_FINDING_SCHEMA_VERSION != "1.0":
        raise ProbeFailure("public schema version is not 1.0")
    if envelope.schema_version != "1.0":
        raise ProbeFailure("fixture did not validate as schema version 1.0")
    if envelope.candidate.trust_level != "untrusted":
        raise ProbeFailure("candidate trust level is not untrusted")
    if envelope.candidate.advisory_only is not True:
        raise ProbeFailure("candidate is not advisory-only")
    supported_versions = package.SUPPORTED_GOVERNANCE_FINDING_SCHEMA_VERSIONS
    if not isinstance(supported_versions, frozenset):
        raise ProbeFailure("public supported-version registry is not an immutable frozenset")
    if package.GOVERNANCE_FINDING_SCHEMA_VERSION not in supported_versions:
        raise ProbeFailure("public current schema version is absent from the supported registry")

    unsupported = copy.deepcopy(payload)
    unknown_major = 999_999
    while f"{unknown_major}.0" in supported_versions:
        unknown_major += 1
    unknown_version = f"{unknown_major}.0"
    unsupported["schema_version"] = unknown_version
    try:
        package.parse_governance_finding(unsupported)
    except package.UnsupportedGovernanceFindingSchemaVersion:
        pass
    else:
        raise ProbeFailure(f"public parser accepted unsupported schema version {unknown_version}")

    _verify_closed_authority_boundary(package, payload)
    return {
        "consumer": consumer_name,
        "contract": "governance-finding",
        "import_origin": str(origin),
        "package_version": _installed_distribution_version(package_root),
        "schema_version": envelope.schema_version,
        "status": "pass",
    }


def main() -> int:
    """Execute the consumer probe with bounded error reporting."""
    args = build_parser().parse_args()
    try:
        result = run_probe(args.package_root, args.fixture, args.consumer_name)
    except (OSError, ProbeFailure, ValidationError) as exc:
        print(f"[ph-1:{args.consumer_name}] FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
