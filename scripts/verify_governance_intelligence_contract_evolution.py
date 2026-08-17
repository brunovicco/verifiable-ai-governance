"""Verify Governance Finding version policy, snapshots, fixtures and public dispatch."""

import argparse
import copy
import hashlib
import importlib
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from governance_schemas import (
    GOVERNANCE_FINDING_SCHEMA_VERSION,
    SUPPORTED_GOVERNANCE_FINDING_SCHEMA_VERSIONS,
    parse_governance_finding,
)
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contracts/governance-intelligence"
POLICY_PATH = CONTRACT_ROOT / "compatibility-policy.json"

POLICY_FIELDS = frozenset(
    {
        "contract",
        "current_schema_version",
        "policy_version",
        "versions",
    }
)
VERSION_FIELDS = frozenset(
    {
        "examples",
        "introduced_in_package",
        "model",
        "read_compatible_with",
        "schema",
        "schema_sha256",
        "schema_version",
        "status",
    }
)
ALLOWED_STATUSES = frozenset({"current", "supported", "deprecated"})
WIRE_VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
PACKAGE_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9.+-]*)$")
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
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


class ContractEvolutionFailure(RuntimeError):
    """Represent one deterministic contract-evolution policy failure."""


@dataclass(frozen=True, slots=True)
class ContractVersion:
    """Describe one supported immutable Governance Finding wire version."""

    schema_version: str
    status: str
    model: str
    schema: str
    schema_sha256: str
    examples: tuple[str, ...]
    read_compatible_with: tuple[str, ...]
    introduced_in_package: str

    @property
    def version_key(self) -> tuple[int, int]:
        """Return the numeric major/minor pair after manifest validation."""
        major, minor = self.schema_version.split(".", maxsplit=1)
        return int(major), int(minor)


@dataclass(frozen=True, slots=True)
class CompatibilityPolicy:
    """Describe the complete supported Governance Finding version set."""

    policy_version: str
    contract: str
    current_schema_version: str
    versions: tuple[ContractVersion, ...]


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractEvolutionFailure(f"{label} must be a JSON object with string keys")
    return cast(dict[str, object], value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractEvolutionFailure(f"{label} must be a non-empty string")
    return value


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ContractEvolutionFailure(f"{label} must be a non-empty string array")
    if any(not isinstance(item, str) or not item for item in value):
        raise ContractEvolutionFailure(f"{label} must contain only non-empty strings")
    return tuple(cast(list[str], value))


def _require_exact_fields(
    document: Mapping[str, object], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(document)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if extra:
            details.append(f"extra={','.join(extra)}")
        raise ContractEvolutionFailure(f"{label} fields are invalid: {'; '.join(details)}")


def _parse_version(raw: object, index: int) -> ContractVersion:
    document = _object(raw, f"versions[{index}]")
    _require_exact_fields(document, VERSION_FIELDS, f"versions[{index}]")
    version = ContractVersion(
        schema_version=_string(document["schema_version"], "schema_version"),
        status=_string(document["status"], "status"),
        model=_string(document["model"], "model"),
        schema=_string(document["schema"], "schema"),
        schema_sha256=_string(document["schema_sha256"], "schema_sha256"),
        examples=_string_list(document["examples"], "examples"),
        read_compatible_with=_string_list(
            document["read_compatible_with"], "read_compatible_with"
        ),
        introduced_in_package=_string(
            document["introduced_in_package"], "introduced_in_package"
        ),
    )
    if WIRE_VERSION_PATTERN.fullmatch(version.schema_version) is None:
        raise ContractEvolutionFailure(
            f"invalid MAJOR.MINOR schema version: {version.schema_version!r}"
        )
    if version.status not in ALLOWED_STATUSES:
        raise ContractEvolutionFailure(f"invalid contract status: {version.status!r}")
    if DIGEST_PATTERN.fullmatch(version.schema_sha256) is None:
        raise ContractEvolutionFailure("schema_sha256 must be lowercase SHA-256 hex")
    if PACKAGE_VERSION_PATTERN.fullmatch(version.introduced_in_package) is None:
        raise ContractEvolutionFailure(
            f"invalid introduced package version: {version.introduced_in_package!r}"
        )
    if len(version.examples) != len(set(version.examples)):
        raise ContractEvolutionFailure(f"duplicate example for schema {version.schema_version}")
    if len(version.read_compatible_with) != len(set(version.read_compatible_with)):
        raise ContractEvolutionFailure(
            f"duplicate read compatibility for schema {version.schema_version}"
        )
    return version


def parse_policy_document(raw: object) -> CompatibilityPolicy:
    """Parse and structurally validate a closed compatibility policy document."""
    document = _object(raw, "compatibility policy")
    _require_exact_fields(document, POLICY_FIELDS, "compatibility policy")
    raw_versions = document["versions"]
    if not isinstance(raw_versions, list) or not raw_versions:
        raise ContractEvolutionFailure("versions must be a non-empty array")
    policy = CompatibilityPolicy(
        policy_version=_string(document["policy_version"], "policy_version"),
        contract=_string(document["contract"], "contract"),
        current_schema_version=_string(
            document["current_schema_version"], "current_schema_version"
        ),
        versions=tuple(_parse_version(item, index) for index, item in enumerate(raw_versions)),
    )
    validate_policy(policy)
    return policy


def validate_policy(policy: CompatibilityPolicy) -> None:
    """Validate version ordering, lifecycle and backward-reader guarantees."""
    if policy.policy_version != "1.0":
        raise ContractEvolutionFailure(f"unsupported policy version: {policy.policy_version!r}")
    if policy.contract != "governance-finding":
        raise ContractEvolutionFailure(f"unexpected contract name: {policy.contract!r}")

    versions = [record.schema_version for record in policy.versions]
    if len(versions) != len(set(versions)):
        raise ContractEvolutionFailure("schema versions must be unique")
    models = [record.model for record in policy.versions]
    if len(models) != len(set(models)):
        raise ContractEvolutionFailure("each schema version must use a dedicated model")
    schemas = [record.schema for record in policy.versions]
    if len(schemas) != len(set(schemas)):
        raise ContractEvolutionFailure("each schema version must use a dedicated snapshot")
    examples = [example for record in policy.versions for example in record.examples]
    if len(examples) != len(set(examples)):
        raise ContractEvolutionFailure("each schema version must use dedicated examples")
    if [record.version_key for record in policy.versions] != sorted(
        record.version_key for record in policy.versions
    ):
        raise ContractEvolutionFailure("schema versions must be ordered numerically")
    if policy.current_schema_version != policy.versions[-1].schema_version:
        raise ContractEvolutionFailure("current schema version must be the newest version")

    current = tuple(record for record in policy.versions if record.status == "current")
    if len(current) != 1 or current[0].schema_version != policy.current_schema_version:
        raise ContractEvolutionFailure("exactly the declared current version must be current")

    supported = frozenset(versions)
    for record in policy.versions:
        declared = frozenset(record.read_compatible_with)
        unknown = sorted(declared - supported)
        if unknown:
            raise ContractEvolutionFailure(
                f"schema {record.schema_version} references unknown read versions: "
                f"{', '.join(unknown)}"
            )
        required = {
            candidate.schema_version
            for candidate in policy.versions
            if candidate.version_key[0] == record.version_key[0]
            and candidate.version_key <= record.version_key
        }
        missing = sorted(required - declared)
        if missing:
            raise ContractEvolutionFailure(
                f"schema {record.schema_version} must read prior same-major versions: "
                f"{', '.join(missing)}"
            )


def load_policy(path: Path = POLICY_PATH) -> CompatibilityPolicy:
    """Load the checked-in compatibility policy."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractEvolutionFailure(f"could not load compatibility policy: {exc}") from exc
    return parse_policy_document(raw)


def _contract_path(contract_root: Path, relative: str, label: str) -> Path:
    raw_path = Path(relative)
    if raw_path.is_absolute():
        raise ContractEvolutionFailure(f"{label} path must be relative: {relative}")
    root = contract_root.resolve()
    path = (root / raw_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ContractEvolutionFailure(f"{label} path escapes contract root: {relative}") from exc
    if not path.is_file():
        raise ContractEvolutionFailure(f"{label} file does not exist: {relative}")
    return path


def _model(model_reference: str) -> type[BaseModel]:
    module_name, separator, attribute = model_reference.partition(":")
    if not separator or not module_name or not attribute:
        raise ContractEvolutionFailure(f"invalid model reference: {model_reference!r}")
    try:
        candidate = getattr(importlib.import_module(module_name), attribute)
    except (AttributeError, ImportError) as exc:
        raise ContractEvolutionFailure(f"could not import model {model_reference}: {exc}") from exc
    if not isinstance(candidate, type) or not issubclass(candidate, BaseModel):
        raise ContractEvolutionFailure(
            f"model reference is not a Pydantic model: {model_reference}"
        )
    return candidate


def _declared_property_names(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            names.update(str(name) for name in properties)
        for nested in value.values():
            names.update(_declared_property_names(nested))
    elif isinstance(value, list):
        for nested in value:
            names.update(_declared_property_names(nested))
    return names


def _verify_schema(record: ContractVersion, contract_root: Path, model: type[BaseModel]) -> None:
    schema_path = _contract_path(contract_root, record.schema, "schema")
    schema_bytes = schema_path.read_bytes()
    digest = hashlib.sha256(schema_bytes).hexdigest()
    if digest != record.schema_sha256:
        raise ContractEvolutionFailure(
            f"schema {record.schema_version} digest drift: expected {record.schema_sha256}, "
            f"found {digest}"
        )
    try:
        checked_schema: object = json.loads(schema_bytes)
    except json.JSONDecodeError as exc:
        raise ContractEvolutionFailure(f"schema {record.schema_version} is invalid JSON") from exc
    generated_schema = model.model_json_schema()
    if checked_schema != generated_schema:
        raise ContractEvolutionFailure(
            f"schema {record.schema_version} differs from {record.model}; "
            "introduce a new schema version instead of overwriting the snapshot"
        )
    forbidden_fields = sorted(
        _declared_property_names(generated_schema) & (AUTHORITY_FIELDS | CONTENT_DUMP_FIELDS)
    )
    if forbidden_fields:
        raise ContractEvolutionFailure(
            f"schema {record.schema_version} exposes forbidden fields: "
            f"{', '.join(forbidden_fields)}"
        )


def _mapping_field(document: dict[str, object], field: str, label: str) -> dict[str, object]:
    value = document.get(field)
    if not isinstance(value, dict):
        raise ContractEvolutionFailure(f"{label} must contain object field {field!r}")
    return cast(dict[str, object], value)


def _expect_model_rejection(
    model: type[BaseModel], document: dict[str, object], label: str
) -> None:
    try:
        model.model_validate(document)
    except ValidationError:
        return
    raise ContractEvolutionFailure(f"model accepted forbidden advisory-boundary mutation: {label}")


def _verify_advisory_boundary(
    model: type[BaseModel], document: dict[str, object], relative: str
) -> None:
    candidate = _mapping_field(document, "candidate", relative)
    if candidate.get("trust_level") != "untrusted":
        raise ContractEvolutionFailure(f"example {relative} is not explicitly untrusted")
    if candidate.get("advisory_only") is not True:
        raise ContractEvolutionFailure(f"example {relative} is not explicitly advisory-only")

    for field in sorted(AUTHORITY_FIELDS):
        mutated = copy.deepcopy(document)
        _mapping_field(mutated, "candidate", relative)[field] = True
        _expect_model_rejection(model, mutated, field)

    trusted = copy.deepcopy(document)
    _mapping_field(trusted, "candidate", relative)["trust_level"] = "trusted"
    _expect_model_rejection(model, trusted, "trust_level=trusted")

    authoritative = copy.deepcopy(document)
    _mapping_field(authoritative, "candidate", relative)["advisory_only"] = False
    _expect_model_rejection(model, authoritative, "advisory_only=false")

    for field in sorted(CONTENT_DUMP_FIELDS):
        mutated = copy.deepcopy(document)
        mutated_candidate = _mapping_field(mutated, "candidate", relative)
        provenance = _mapping_field(mutated_candidate, "provenance", relative)
        provenance[field] = "sensitive content"
        _expect_model_rejection(model, mutated, field)


def _verify_examples(
    record: ContractVersion, contract_root: Path, model: type[BaseModel]
) -> None:
    for relative in record.examples:
        example_path = _contract_path(contract_root, relative, "example")
        try:
            raw: object = json.loads(example_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ContractEvolutionFailure(f"example is invalid JSON: {relative}") from exc
        document = _object(raw, f"example {relative}")
        if document.get("schema_version") != record.schema_version:
            raise ContractEvolutionFailure(
                f"example {relative} does not declare schema {record.schema_version}"
            )
        _verify_advisory_boundary(model, document, relative)
        parsed = model.model_validate(document)
        dispatched = parse_governance_finding(document)
        if type(parsed) is not type(dispatched):
            raise ContractEvolutionFailure(
                f"public dispatch selected the wrong model for {record.schema_version}"
            )


def verify_contract_evolution(
    policy_path: Path = POLICY_PATH,
    contract_root: Path = CONTRACT_ROOT,
) -> CompatibilityPolicy:
    """Verify the complete checked-in policy against package behavior and artifacts."""
    policy = load_policy(policy_path)
    declared_versions = frozenset(record.schema_version for record in policy.versions)
    if declared_versions != SUPPORTED_GOVERNANCE_FINDING_SCHEMA_VERSIONS:
        raise ContractEvolutionFailure(
            "public supported-version registry differs from compatibility policy"
        )
    if policy.current_schema_version != GOVERNANCE_FINDING_SCHEMA_VERSION:
        raise ContractEvolutionFailure(
            "public current schema version differs from compatibility policy"
        )

    for record in policy.versions:
        model = _model(record.model)
        _verify_schema(record, contract_root, model)
        _verify_examples(record, contract_root, model)
        print(
            f"[ph-2] schema={record.schema_version} status={record.status} "
            f"read={','.join(record.read_compatible_with)} digest={record.schema_sha256} PASS"
        )
    return policy


def build_parser() -> argparse.ArgumentParser:
    """Build the contract-evolution verifier command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--contract-root", type=Path, default=CONTRACT_ROOT)
    return parser


def main() -> int:
    """Run PH-2 contract-evolution verification with bounded errors."""
    args = build_parser().parse_args()
    try:
        policy = verify_contract_evolution(args.policy.resolve(), args.contract_root.resolve())
    except (ContractEvolutionFailure, OSError, ValidationError) as exc:
        print(f"[ph-2] FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        f"[ph-2] PASSED current={policy.current_schema_version} "
        f"supported={len(policy.versions)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
