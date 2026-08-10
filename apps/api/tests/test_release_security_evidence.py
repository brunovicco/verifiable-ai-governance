import json
from datetime import date
from pathlib import Path

import pytest

from scripts.release_security_evidence import (
    SecurityEvidenceError,
    bundle_digest,
    canonical_json_bytes,
    policy_digest,
    release_manifest_digest,
    sha256_bytes,
    summarize_npm_audit,
    summarize_python_audit,
    summarize_trivy_audit,
)


def _policy() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "python": {"block_all_known_vulnerabilities": True, "exceptions": []},
        "npm": {"block_severities": ["high", "critical"]},
        "container": {
            "block_severities": ["HIGH", "CRITICAL"],
            "require_fix_available": True,
        },
    }


def test_canonical_digest_is_order_independent() -> None:
    left = {"b": 2, "a": {"d": 4, "c": 3}}
    right = {"a": {"c": 3, "d": 4}, "b": 2}
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert sha256_bytes(canonical_json_bytes(left)) == sha256_bytes(canonical_json_bytes(right))


def test_release_manifest_self_digest_is_verified() -> None:
    manifest: dict[str, object] = {
        "canonicalization": "json-sort-keys-compact-v1",
        "release": {"version": "0.2.0-rc1"},
    }
    manifest["manifest_digest"] = sha256_bytes(canonical_json_bytes(manifest))
    assert release_manifest_digest(manifest) == manifest["manifest_digest"]
    manifest["release"] = {"version": "tampered"}
    with pytest.raises(SecurityEvidenceError, match="digest mismatch"):
        release_manifest_digest(manifest)


def test_bundle_digest_excludes_only_self_digest() -> None:
    bundle = {"kind": "example", "value": 1}
    digest = bundle_digest(bundle)
    with_digest = {**bundle, "bundle_digest": digest}
    assert bundle_digest(with_digest) == digest
    with_digest["value"] = 2
    assert bundle_digest(with_digest) != digest


def test_python_audit_blocks_known_vulnerability() -> None:
    audit = {
        "dependencies": [
            {
                "name": "example",
                "version": "1.0",
                "vulns": [
                    {
                        "id": "CVE-2026-0001",
                        "aliases": ["GHSA-aaaa-bbbb-cccc"],
                        "fix_versions": ["1.1"],
                    }
                ],
            }
        ]
    }
    summary = summarize_python_audit(audit, "governance", _policy(), date(2026, 8, 9))
    assert summary["verdict"] == "fail"
    assert summary["blocking_count"] == 1


def test_python_audit_supports_expiring_exception() -> None:
    policy = _policy()
    python_policy = policy["python"]
    assert isinstance(python_policy, dict)
    python_policy["exceptions"] = [
        {
            "component": "governance",
            "id": "GHSA-aaaa-bbbb-cccc",
            "reason": "accepted temporarily",
            "expires_on": "2026-08-31",
        }
    ]
    audit = {
        "dependencies": [
            {
                "name": "example",
                "version": "1.0",
                "vulns": [
                    {
                        "id": "CVE-2026-0001",
                        "aliases": ["GHSA-aaaa-bbbb-cccc"],
                        "fix_versions": [],
                    }
                ],
            }
        ]
    }
    active = summarize_python_audit(audit, "governance", policy, date(2026, 8, 9))
    expired = summarize_python_audit(audit, "governance", policy, date(2026, 9, 1))
    assert active["verdict"] == "pass"
    assert active["excepted_count"] == 1
    assert expired["verdict"] == "fail"


def test_npm_high_and_critical_are_blocking() -> None:
    audit = {
        "vulnerabilities": {
            "low-package": {"severity": "low", "range": "<2", "fixAvailable": True},
            "high-package": {"severity": "high", "range": "<3", "fixAvailable": True},
        }
    }
    summary = summarize_npm_audit(audit, _policy())
    assert summary["finding_count"] == 2
    assert summary["blocking_count"] == 1
    assert summary["verdict"] == "fail"


def test_trivy_matches_existing_ignore_unfixed_semantics() -> None:
    audit = {
        "Results": [
            {
                "Target": "python",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-FIXED",
                        "PkgName": "fixed",
                        "InstalledVersion": "1",
                        "FixedVersion": "2",
                        "Severity": "HIGH",
                    },
                    {
                        "VulnerabilityID": "CVE-UNFIXED",
                        "PkgName": "unfixed",
                        "InstalledVersion": "1",
                        "FixedVersion": "",
                        "Severity": "CRITICAL",
                    },
                ],
            }
        ]
    }
    summary = summarize_trivy_audit(audit, "governance_api", _policy())
    assert summary["blocking_count"] == 1
    assert summary["high_critical_unfixed_count"] == 1
    assert summary["verdict"] == "fail"


def test_policy_digest_changes_on_policy_change() -> None:
    policy = _policy()
    initial = policy_digest(policy)
    npm_policy = policy["npm"]
    assert isinstance(npm_policy, dict)
    npm_policy["block_severities"] = ["critical"]
    assert policy_digest(policy) != initial


def test_schema_is_closed_at_top_level() -> None:
    schema = json.loads(Path("schemas/release-security-evidence.schema.json").read_text())
    assert schema["additionalProperties"] is False
    assert schema["properties"]["bundle_digest"]["$ref"] == "#/$defs/sha256"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def test_full_bundle_verification_detects_artifact_tamper(tmp_path: Path) -> None:
    from scripts.release_security_evidence import (
        REQUIRED_ARTIFACT_ROLES,
        build_artifact_record,
        summarize_trivy_audit,
        verify_bundle,
    )

    release_manifest = {
        "canonicalization": "json-sort-keys-compact-v1",
        "release": {"version": "0.2.0-rc1"},
        "components": {
            name: {
                "repository": f"brunovicco/{name}",
                "commit": (str(index + 1) * 40)[:40],
                "lockfile": {"sha256": (str(index + 5) * 64)[:64]},
            }
            for index, name in enumerate(
                (
                    "a2a_otel_kit",
                    "governance",
                    "multi_agent_credit_desk",
                    "policy_model_router",
                )
            )
        },
    }
    release_manifest["manifest_digest"] = sha256_bytes(canonical_json_bytes(release_manifest))
    release_manifest_path = tmp_path / "artifacts/release/release-manifest.json"
    _write_json(release_manifest_path, release_manifest)

    policy = _policy()
    policy_path = tmp_path / "config/release-security-policy.json"
    _write_json(policy_path, policy)

    bundle_path = tmp_path / "artifacts/release/security/security-evidence-bundle.json"
    artifacts: list[dict[str, object]] = []
    summaries: dict[str, object] = {}
    generated_on = date(2026, 8, 9)
    for component in (
        "a2a_otel_kit",
        "governance",
        "multi_agent_credit_desk",
        "policy_model_router",
    ):
        requirements = tmp_path / f"artifacts/release/security/inputs/{component}-requirements.txt"
        requirements.parent.mkdir(parents=True, exist_ok=True)
        requirements.write_text("example==1.0\n", encoding="utf-8")
        audit = tmp_path / f"artifacts/release/security/vulnerabilities/{component}-pip-audit.json"
        _write_json(audit, {"dependencies": []})
        sbom = tmp_path / f"artifacts/release/security/sbom/{component}-python.cdx.json"
        _write_json(sbom, {"bomFormat": "CycloneDX", "specVersion": "1.5"})
        artifacts.extend(
            [
                build_artifact_record(
                    requirements,
                    tmp_path,
                    f"python_requirements:{component}",
                    "text/plain",
                ),
                build_artifact_record(
                    audit,
                    tmp_path,
                    f"python_audit:{component}",
                    "application/json",
                ),
                build_artifact_record(
                    sbom,
                    tmp_path,
                    f"python_sbom:{component}",
                    "application/vnd.cyclonedx+json",
                ),
            ]
        )
        summaries[f"python:{component}"] = summarize_python_audit(
            {"dependencies": []}, component, policy, generated_on
        )

    npm_sbom = tmp_path / "artifacts/release/security/sbom/governance-web-npm.cdx.json"
    _write_json(npm_sbom, {"bomFormat": "CycloneDX", "specVersion": "1.5"})
    npm_audit = (
        tmp_path / "artifacts/release/security/vulnerabilities/governance-web-npm-audit.json"
    )
    _write_json(npm_audit, {"vulnerabilities": {}})
    artifacts.extend(
        [
            build_artifact_record(
                npm_sbom,
                tmp_path,
                "npm_sbom:governance_web",
                "application/vnd.cyclonedx+json",
            ),
            build_artifact_record(
                npm_audit,
                tmp_path,
                "npm_audit:governance_web",
                "application/json",
            ),
        ]
    )
    summaries["npm:governance_web"] = summarize_npm_audit({"vulnerabilities": {}}, policy)

    for component in ("governance_api", "governance_web"):
        trivy_payload = {"Results": []}
        audit = tmp_path / f"artifacts/release/security/vulnerabilities/{component}-trivy.json"
        _write_json(audit, trivy_payload)
        sbom = tmp_path / f"artifacts/release/security/sbom/{component}-image.cdx.json"
        _write_json(sbom, {"bomFormat": "CycloneDX", "specVersion": "1.5"})
        artifacts.extend(
            [
                build_artifact_record(
                    audit,
                    tmp_path,
                    f"container_audit:{component}",
                    "application/json",
                ),
                build_artifact_record(
                    sbom,
                    tmp_path,
                    f"container_sbom:{component}",
                    "application/vnd.cyclonedx+json",
                ),
            ]
        )
        summaries[f"container:{component}"] = summarize_trivy_audit(
            trivy_payload, component, policy
        )

    assert {str(record["role"]) for record in artifacts} == REQUIRED_ARTIFACT_ROLES
    artifacts.sort(key=lambda record: str(record["role"]))
    bundle: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "verifiable-ai-governance/release-security-evidence",
        "canonicalization": "json-sort-keys-compact-v1",
        "generated_at": "2026-08-09T23:30:00Z",
        "release_version": "0.2.0-rc1",
        "release_manifest_digest": release_manifest["manifest_digest"],
        "policy_digest": policy_digest(policy),
        "source_bindings": {
            name: {
                "repository": component["repository"],
                "commit": component["commit"],
                "lockfile_sha256": component["lockfile"]["sha256"],
            }
            for name, component in sorted(release_manifest["components"].items())
        },
        "tools": {},
        "images": {
            "governance_api": {
                "source_commit": release_manifest["components"]["governance"]["commit"],
                "image_id": "sha256:api",
            },
            "governance_web": {
                "source_commit": release_manifest["components"]["governance"]["commit"],
                "image_id": "sha256:web",
            },
        },
        "artifacts": artifacts,
        "summaries": summaries,
        "verdict": "pass",
    }
    bundle["bundle_digest"] = bundle_digest(bundle)
    _write_json(bundle_path, bundle)
    assert verify_bundle(bundle_path, release_manifest_path, policy_path)["verdict"] == "pass"

    first_artifact = tmp_path / str(artifacts[0]["path"])
    first_artifact.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SecurityEvidenceError, match="Artifact digest mismatch"):
        verify_bundle(bundle_path, release_manifest_path, policy_path)
