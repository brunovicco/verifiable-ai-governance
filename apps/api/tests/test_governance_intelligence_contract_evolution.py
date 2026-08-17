"""Tests for Governance Finding version dispatch and PH-2 evolution policy."""

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from governance_schemas import (
    GOVERNANCE_FINDING_SCHEMA_VERSION,
    SUPPORTED_GOVERNANCE_FINDING_SCHEMA_VERSIONS,
    GovernanceFindingEnvelope,
    UnsupportedGovernanceFindingSchemaVersion,
    parse_governance_finding,
)

from scripts.verify_governance_intelligence_contract_evolution import (
    CONTRACT_ROOT,
    POLICY_PATH,
    CompatibilityPolicy,
    ContractEvolutionFailure,
    ContractVersion,
    parse_policy_document,
    validate_policy,
    verify_contract_evolution,
)

EXAMPLE = CONTRACT_ROOT / "examples/risk-candidate-v1.json"


def _example() -> dict[str, object]:
    payload: object = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _version(**overrides: object) -> ContractVersion:
    values: dict[str, object] = {
        "schema_version": "1.0",
        "status": "current",
        "model": "governance_schemas:GovernanceFindingEnvelope",
        "schema": "v1.schema.json",
        "schema_sha256": "a" * 64,
        "examples": ("examples/risk-candidate-v1.json",),
        "read_compatible_with": ("1.0",),
        "introduced_in_package": "0.1.0",
    }
    values.update(overrides)
    return ContractVersion(**values)


def test_public_dispatch_parses_the_current_explicit_version() -> None:
    envelope = parse_governance_finding(_example())

    assert isinstance(envelope, GovernanceFindingEnvelope)
    assert envelope.schema_version == GOVERNANCE_FINDING_SCHEMA_VERSION
    assert frozenset({"1.0"}) == SUPPORTED_GOVERNANCE_FINDING_SCHEMA_VERSIONS


@pytest.mark.parametrize("schema_version", [None, 1.0, "1.1", "2.0"])
def test_public_dispatch_fails_closed_for_absent_or_unknown_version(
    schema_version: object,
) -> None:
    payload = _example()
    if schema_version is None:
        payload.pop("schema_version")
    else:
        payload["schema_version"] = schema_version

    with pytest.raises(UnsupportedGovernanceFindingSchemaVersion):
        parse_governance_finding(payload)


def test_unsupported_version_error_is_bounded() -> None:
    with pytest.raises(UnsupportedGovernanceFindingSchemaVersion) as captured:
        parse_governance_finding({"schema_version": "9" * 10_000})

    assert len(str(captured.value)) < 140


def test_checked_in_policy_schema_and_examples_are_current() -> None:
    policy = verify_contract_evolution()

    assert policy.current_schema_version == "1.0"
    assert tuple(record.schema_version for record in policy.versions) == ("1.0",)


def test_policy_document_is_closed() -> None:
    document = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    document["unreviewed_rule"] = True

    with pytest.raises(ContractEvolutionFailure, match="extra=unreviewed_rule"):
        parse_policy_document(document)


def test_new_minor_must_read_every_prior_minor_in_the_same_major() -> None:
    first = replace(_version(), status="supported")
    second = replace(
        _version(),
        schema_version="1.1",
        model="governance_schemas:GovernanceFindingEnvelopeV1_1",
        schema="v1.1.schema.json",
        examples=("examples/risk-candidate-v1.1.json",),
        read_compatible_with=("1.1",),
    )
    policy = CompatibilityPolicy(
        policy_version="1.0",
        contract="governance-finding",
        current_schema_version="1.1",
        versions=(first, second),
    )

    with pytest.raises(ContractEvolutionFailure, match="must read prior same-major versions: 1.0"):
        validate_policy(policy)


def test_forward_read_compatibility_is_not_required() -> None:
    first = replace(_version(), status="supported")
    second = replace(
        _version(),
        schema_version="1.1",
        model="governance_schemas:GovernanceFindingEnvelopeV1_1",
        schema="v1.1.schema.json",
        examples=("examples/risk-candidate-v1.1.json",),
        read_compatible_with=("1.0", "1.1"),
    )
    policy = CompatibilityPolicy(
        policy_version="1.0",
        contract="governance-finding",
        current_schema_version="1.1",
        versions=(first, second),
    )

    validate_policy(policy)


def test_each_version_requires_dedicated_model_and_artifacts() -> None:
    first = replace(_version(), status="supported")
    second = replace(
        _version(),
        schema_version="1.1",
        read_compatible_with=("1.0", "1.1"),
    )
    policy = CompatibilityPolicy(
        policy_version="1.0",
        contract="governance-finding",
        current_schema_version="1.1",
        versions=(first, second),
    )

    with pytest.raises(ContractEvolutionFailure, match="dedicated model"):
        validate_policy(policy)


def test_schema_byte_drift_is_rejected(tmp_path: Path) -> None:
    contract_root = tmp_path / "governance-intelligence"
    shutil.copytree(CONTRACT_ROOT, contract_root)
    schema = contract_root / "v1.schema.json"
    schema.write_bytes(schema.read_bytes() + b"\n")

    with pytest.raises(ContractEvolutionFailure, match="digest drift"):
        verify_contract_evolution(contract_root / POLICY_PATH.name, contract_root)


def test_updating_digest_cannot_overwrite_a_version_snapshot(tmp_path: Path) -> None:
    contract_root = tmp_path / "governance-intelligence"
    shutil.copytree(CONTRACT_ROOT, contract_root)
    schema_path = contract_root / "v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["title"] = "SilentlyChangedGovernanceFindingEnvelope"
    schema_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    policy_path = contract_root / POLICY_PATH.name
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["versions"][0]["schema_sha256"] = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ContractEvolutionFailure, match="introduce a new schema version"):
        verify_contract_evolution(policy_path, contract_root)
