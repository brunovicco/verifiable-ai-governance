"""Canonical P2.0b SBOM and vulnerability release evidence helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
KIND = "verifiable-ai-governance/release-security-evidence"
CANONICALIZATION = "json-sort-keys-compact-v1"

REQUIRED_ARTIFACT_ROLES = frozenset(
    {
        "python_requirements:a2a_otel_kit",
        "python_requirements:governance",
        "python_requirements:multi_agent_credit_desk",
        "python_requirements:policy_model_router",
        "python_sbom:a2a_otel_kit",
        "python_sbom:governance",
        "python_sbom:multi_agent_credit_desk",
        "python_sbom:policy_model_router",
        "python_audit:a2a_otel_kit",
        "python_audit:governance",
        "python_audit:multi_agent_credit_desk",
        "python_audit:policy_model_router",
        "npm_sbom:governance_web",
        "npm_audit:governance_web",
        "container_sbom:governance_api",
        "container_sbom:governance_web",
        "container_audit:governance_api",
        "container_audit:governance_web",
    }
)


class SecurityEvidenceError(RuntimeError):
    """Raised when release security evidence is incomplete or inconsistent."""


def canonical_json_bytes(value: object) -> bytes:
    """Return canonical compact JSON bytes."""
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash one file without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha256(value: object, label: str) -> str:
    """Require one canonical SHA-256 string."""
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SecurityEvidenceError(f"{label} is not a canonical SHA-256 digest")
    return value


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecurityEvidenceError(f"Cannot load JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SecurityEvidenceError(f"Expected JSON object in {path}")
    return value


def verify_self_digest(payload: Mapping[str, Any], field: str, label: str) -> str:
    """Verify a canonical self-digest field."""
    observed = require_sha256(payload.get(field), f"{label} {field}")
    unsigned = dict(payload)
    unsigned.pop(field, None)
    expected = sha256_bytes(canonical_json_bytes(unsigned))
    if observed != expected:
        raise SecurityEvidenceError(
            f"{label} digest mismatch: expected {expected}, observed {observed}"
        )
    return observed


def release_manifest_digest(manifest: Mapping[str, Any]) -> str:
    """Verify and return the P2.0a release manifest digest."""
    if manifest.get("canonicalization") != CANONICALIZATION:
        raise SecurityEvidenceError("Unsupported release-manifest canonicalization")
    return verify_self_digest(manifest, "manifest_digest", "release manifest")


def policy_digest(policy: Mapping[str, Any]) -> str:
    """Return the canonical security-policy digest."""
    return sha256_bytes(canonical_json_bytes(policy))


def build_artifact_record(path: Path, root: Path, role: str, media_type: str) -> dict[str, object]:
    """Build one content-addressed artifact record."""
    return {
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "media_type": media_type,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _iter_python_vulnerabilities(payload: object) -> Iterable[dict[str, object]]:
    if isinstance(payload, dict):
        dependencies = payload.get("dependencies", [])
    elif isinstance(payload, list):
        dependencies = payload
    else:
        raise SecurityEvidenceError("Unsupported pip-audit JSON structure")
    if not isinstance(dependencies, list):
        raise SecurityEvidenceError("pip-audit dependencies must be an array")
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        name = dependency.get("name")
        version = dependency.get("version")
        vulnerabilities = dependency.get("vulns", [])
        if not isinstance(vulnerabilities, list):
            continue
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                continue
            vuln_id = vulnerability.get("id")
            if not isinstance(vuln_id, str) or not vuln_id:
                continue
            aliases = vulnerability.get("aliases", [])
            fix_versions = vulnerability.get("fix_versions", [])
            yield {
                "id": vuln_id,
                "aliases": sorted(alias for alias in aliases if isinstance(alias, str)),
                "package": name if isinstance(name, str) else "unknown",
                "version": version if isinstance(version, str) else "unknown",
                "fix_versions": sorted(fixed for fixed in fix_versions if isinstance(fixed, str)),
            }


def _exception_matches(
    component: str,
    finding: Mapping[str, object],
    exception: Mapping[str, object],
    generated_on: date,
) -> bool:
    exception_component = exception.get("component")
    if exception_component not in (component, "*"):
        return False
    exception_id = exception.get("id")
    aliases = finding.get("aliases", [])
    candidates = {finding.get("id")}
    if isinstance(aliases, list):
        candidates.update(aliases)
    if exception_id not in candidates:
        return False
    reason = exception.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return False
    expires_on = exception.get("expires_on")
    if not isinstance(expires_on, str):
        return False
    try:
        expiry = date.fromisoformat(expires_on)
    except ValueError as exc:
        raise SecurityEvidenceError(f"Invalid exception expiry date: {expires_on}") from exc
    return generated_on <= expiry


def summarize_python_audit(
    payload: object,
    component: str,
    policy: Mapping[str, Any],
    generated_on: date,
) -> dict[str, object]:
    """Normalize pip-audit findings and apply release policy."""
    python_policy = policy.get("python")
    if not isinstance(python_policy, dict):
        raise SecurityEvidenceError("Security policy is missing python settings")
    exceptions = python_policy.get("exceptions", [])
    if not isinstance(exceptions, list):
        raise SecurityEvidenceError("Python exceptions must be an array")
    block_all = bool(python_policy.get("block_all_known_vulnerabilities", True))
    findings: list[dict[str, object]] = []
    blocking = 0
    excepted = 0
    for finding in _iter_python_vulnerabilities(payload):
        matched = any(
            isinstance(exception, dict)
            and _exception_matches(component, finding, exception, generated_on)
            for exception in exceptions
        )
        item = dict(finding)
        if matched:
            item["status"] = "excepted"
            excepted += 1
        elif block_all:
            item["status"] = "blocking"
            blocking += 1
        else:
            item["status"] = "observed"
        findings.append(item)
    findings.sort(key=lambda item: (str(item["package"]), str(item["id"])))
    return {
        "scanner": "pip-audit",
        "component": component,
        "finding_count": len(findings),
        "blocking_count": blocking,
        "excepted_count": excepted,
        "verdict": "pass" if blocking == 0 else "fail",
        "findings": findings,
    }


def summarize_npm_audit(payload: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, object]:
    """Normalize npm audit findings and apply severity policy."""
    npm_policy = policy.get("npm")
    if not isinstance(npm_policy, dict):
        raise SecurityEvidenceError("Security policy is missing npm settings")
    configured = npm_policy.get("block_severities", [])
    if not isinstance(configured, list):
        raise SecurityEvidenceError("npm block_severities must be an array")
    blocked = {str(value).lower() for value in configured}
    vulnerabilities = payload.get("vulnerabilities", {})
    if not isinstance(vulnerabilities, dict):
        raise SecurityEvidenceError("npm audit vulnerabilities must be an object")
    findings: list[dict[str, object]] = []
    blocking = 0
    for package, vulnerability in vulnerabilities.items():
        if not isinstance(package, str) or not isinstance(vulnerability, dict):
            continue
        severity = str(vulnerability.get("severity", "unknown")).lower()
        item = {
            "package": package,
            "severity": severity,
            "range": str(vulnerability.get("range", "")),
            "fix_available": bool(vulnerability.get("fixAvailable")),
            "status": "blocking" if severity in blocked else "observed",
        }
        findings.append(item)
        if severity in blocked:
            blocking += 1
    findings.sort(key=lambda item: (str(item["severity"]), str(item["package"])))
    return {
        "scanner": "npm-audit",
        "component": "governance_web",
        "finding_count": len(findings),
        "blocking_count": blocking,
        "verdict": "pass" if blocking == 0 else "fail",
        "findings": findings,
    }


def summarize_trivy_audit(
    payload: Mapping[str, Any],
    component: str,
    policy: Mapping[str, Any],
) -> dict[str, object]:
    """Normalize Trivy container findings and apply release policy."""
    container_policy = policy.get("container")
    if not isinstance(container_policy, dict):
        raise SecurityEvidenceError("Security policy is missing container settings")
    configured = container_policy.get("block_severities", [])
    if not isinstance(configured, list):
        raise SecurityEvidenceError("container block_severities must be an array")
    blocked = {str(value).upper() for value in configured}
    require_fix = bool(container_policy.get("require_fix_available", False))
    results = payload.get("Results", [])
    if not isinstance(results, list):
        raise SecurityEvidenceError("Trivy Results must be an array")
    findings: list[dict[str, object]] = []
    blocking = 0
    high_critical_unfixed = 0
    for result in results:
        if not isinstance(result, dict):
            continue
        vulnerabilities = result.get("Vulnerabilities", []) or []
        if not isinstance(vulnerabilities, list):
            continue
        target = str(result.get("Target", ""))
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                continue
            severity = str(vulnerability.get("Severity", "UNKNOWN")).upper()
            fixed_version = str(vulnerability.get("FixedVersion", ""))
            severity_blocks = severity in blocked
            fix_blocks = not require_fix or bool(fixed_version)
            is_blocking = severity_blocks and fix_blocks
            if severity_blocks and not fixed_version:
                high_critical_unfixed += 1
            item: dict[str, object] = {
                "id": str(vulnerability.get("VulnerabilityID", "unknown")),
                "package": str(vulnerability.get("PkgName", "unknown")),
                "installed_version": str(vulnerability.get("InstalledVersion", "")),
                "fixed_version": fixed_version,
                "severity": severity,
                "target": target,
                "status": "blocking" if is_blocking else "observed",
            }
            findings.append(item)
            if is_blocking:
                blocking += 1
    findings.sort(key=lambda item: (str(item["severity"]), str(item["package"]), str(item["id"])))
    return {
        "scanner": "trivy",
        "component": component,
        "finding_count": len(findings),
        "blocking_count": blocking,
        "high_critical_unfixed_count": high_critical_unfixed,
        "verdict": "pass" if blocking == 0 else "fail",
        "findings": findings,
    }


def verify_cyclonedx(path: Path) -> None:
    """Require a minimally valid CycloneDX JSON document."""
    payload = load_json_object(path)
    if payload.get("bomFormat") != "CycloneDX":
        raise SecurityEvidenceError(f"SBOM is not CycloneDX: {path}")
    if not isinstance(payload.get("specVersion"), str):
        raise SecurityEvidenceError(f"SBOM specVersion is missing: {path}")


def bundle_digest(bundle: Mapping[str, Any]) -> str:
    """Compute the canonical bundle digest."""
    unsigned = dict(bundle)
    unsigned.pop("bundle_digest", None)
    return sha256_bytes(canonical_json_bytes(unsigned))


def verify_bundle(
    bundle_path: Path,
    release_manifest_path: Path,
    policy_path: Path,
) -> dict[str, Any]:
    """Verify a P2.0b bundle without network or scanner execution."""
    bundle = load_json_object(bundle_path)
    if bundle.get("schema_version") != SCHEMA_VERSION or bundle.get("kind") != KIND:
        raise SecurityEvidenceError("Unsupported release security evidence contract")
    if bundle.get("canonicalization") != CANONICALIZATION:
        raise SecurityEvidenceError("Unsupported security-evidence canonicalization")
    observed_digest = require_sha256(bundle.get("bundle_digest"), "bundle_digest")
    expected_digest = bundle_digest(bundle)
    if observed_digest != expected_digest:
        raise SecurityEvidenceError("Security evidence bundle digest mismatch")

    release_manifest = load_json_object(release_manifest_path)
    expected_release_digest = release_manifest_digest(release_manifest)
    if bundle.get("release_manifest_digest") != expected_release_digest:
        raise SecurityEvidenceError("Security evidence is bound to another release manifest")
    release = release_manifest.get("release")
    if not isinstance(release, dict) or bundle.get("release_version") != release.get("version"):
        raise SecurityEvidenceError("Security evidence release version mismatch")
    components = release_manifest.get("components")
    if not isinstance(components, dict):
        raise SecurityEvidenceError("Release manifest components are missing")
    expected_bindings: dict[str, object] = {}
    for name in sorted(
        ("a2a_otel_kit", "governance", "multi_agent_credit_desk", "policy_model_router")
    ):
        component = components.get(name)
        if not isinstance(component, dict):
            raise SecurityEvidenceError(f"Release component is missing: {name}")
        lockfile = component.get("lockfile")
        if not isinstance(lockfile, dict):
            raise SecurityEvidenceError(f"Release lockfile is missing: {name}")
        expected_bindings[name] = {
            "repository": component.get("repository"),
            "commit": component.get("commit"),
            "lockfile_sha256": lockfile.get("sha256"),
        }
    if bundle.get("source_bindings") != expected_bindings:
        raise SecurityEvidenceError("Security evidence source bindings mismatch")
    governance_binding = expected_bindings["governance"]
    assert isinstance(governance_binding, dict)
    governance_commit = governance_binding.get("commit")
    images = bundle.get("images")
    if not isinstance(images, dict) or set(images) != {"governance_api", "governance_web"}:
        raise SecurityEvidenceError("Security evidence image bindings are incomplete")
    for name in ("governance_api", "governance_web"):
        image = images.get(name)
        if not isinstance(image, dict) or image.get("source_commit") != governance_commit:
            raise SecurityEvidenceError(f"Image source binding mismatch: {name}")

    policy = load_json_object(policy_path)
    expected_policy_digest = policy_digest(policy)
    if bundle.get("policy_digest") != expected_policy_digest:
        raise SecurityEvidenceError("Security evidence policy digest mismatch")

    root = bundle_path.resolve().parents[3]
    artifacts = bundle.get("artifacts")
    if not isinstance(artifacts, list):
        raise SecurityEvidenceError("Security evidence artifacts must be an array")
    roles: set[str] = set()
    for record in artifacts:
        if not isinstance(record, dict):
            raise SecurityEvidenceError("Invalid artifact record")
        role = record.get("role")
        relative = record.get("path")
        if not isinstance(role, str) or not isinstance(relative, str):
            raise SecurityEvidenceError("Artifact role/path is invalid")
        if role in roles:
            raise SecurityEvidenceError(f"Duplicate artifact role: {role}")
        roles.add(role)
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise SecurityEvidenceError(
                f"Artifact path escapes repository root: {relative}"
            ) from exc
        if not path.is_file():
            raise SecurityEvidenceError(f"Missing release security artifact: {relative}")
        digest = require_sha256(record.get("sha256"), f"artifact {relative} sha256")
        if sha256_file(path) != digest:
            raise SecurityEvidenceError(f"Artifact digest mismatch: {relative}")
        if path.stat().st_size != record.get("size_bytes"):
            raise SecurityEvidenceError(f"Artifact size mismatch: {relative}")
        if "_sbom:" in role:
            verify_cyclonedx(path)
    if roles != REQUIRED_ARTIFACT_ROLES:
        missing = sorted(REQUIRED_ARTIFACT_ROLES - roles)
        extra = sorted(roles - REQUIRED_ARTIFACT_ROLES)
        raise SecurityEvidenceError(f"Artifact role mismatch; missing={missing}, extra={extra}")

    generated_at = bundle.get("generated_at")
    if not isinstance(generated_at, str) or len(generated_at) < 10:
        raise SecurityEvidenceError("generated_at is missing")
    try:
        generated_on = date.fromisoformat(generated_at[:10])
    except ValueError as exc:
        raise SecurityEvidenceError("generated_at is not ISO-8601") from exc

    by_role = {str(record["role"]): root / str(record["path"]) for record in artifacts}
    summaries: dict[str, object] = {}
    for component in (
        "a2a_otel_kit",
        "governance",
        "multi_agent_credit_desk",
        "policy_model_router",
    ):
        audit = json.loads(by_role[f"python_audit:{component}"].read_text(encoding="utf-8"))
        summaries[f"python:{component}"] = summarize_python_audit(
            audit,
            component,
            policy,
            generated_on,
        )
    npm_audit = load_json_object(by_role["npm_audit:governance_web"])
    summaries["npm:governance_web"] = summarize_npm_audit(npm_audit, policy)
    for component in ("governance_api", "governance_web"):
        trivy = load_json_object(by_role[f"container_audit:{component}"])
        summaries[f"container:{component}"] = summarize_trivy_audit(trivy, component, policy)

    if bundle.get("summaries") != summaries:
        raise SecurityEvidenceError("Security evidence summaries do not match raw reports")
    expected_verdict = "pass"
    if any(
        isinstance(summary, dict) and summary.get("verdict") == "fail"
        for summary in summaries.values()
    ):
        expected_verdict = "fail"
    if bundle.get("verdict") != expected_verdict:
        raise SecurityEvidenceError("Security evidence verdict does not match policy evaluation")
    return bundle
