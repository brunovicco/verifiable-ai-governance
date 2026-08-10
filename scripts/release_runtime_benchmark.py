"""Core helpers for P2.0d runtime benchmark and SLO evidence."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
KIND = "verifiable-ai-governance/release-runtime-benchmark"
CANONICALIZATION = "json-sort-keys-compact-v1"

RUNTIME_PATH_PREFIXES = (
    "apps/api/src/",
    "apps/api/alembic/",
    "packages/governance-schemas/src/",
    "packages/policy-engine/src/",
)
RUNTIME_EXACT_PATHS = {
    "apps/api/pyproject.toml",
    "pyproject.toml",
    "uv.lock",
}


class RuntimeBenchmarkError(RuntimeError):
    """Raised when benchmark evidence violates a release invariant."""


def canonical_json_bytes(value: object) -> bytes:
    """Return compact deterministic JSON."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_bytes(value: bytes) -> str:
    """Return the SHA-256 hex digest for bytes."""
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    """Read one JSON object from disk or fail closed."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeBenchmarkError(f"Could not read JSON evidence: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeBenchmarkError(f"JSON evidence must be an object: {path}")
    return value


def file_record(path: Path, root: Path) -> dict[str, object]:
    """Return bounded path, digest, and size evidence for one file."""
    data = path.read_bytes()
    return {
        "path": path.resolve().relative_to(root.resolve()).as_posix(),
        "sha256": sha256_bytes(data),
        "size_bytes": len(data),
    }


def self_digest(value: dict[str, object], field: str) -> str:
    """Compute a canonical digest while excluding the self-digest field."""
    payload = dict(value)
    payload.pop(field, None)
    return sha256_bytes(canonical_json_bytes(payload))


def _percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        raise RuntimeBenchmarkError("Cannot compute percentile over an empty sample")
    if not 0.0 < quantile <= 1.0:
        raise RuntimeBenchmarkError("Percentile quantile must be in (0, 1]")
    index = max(0, math.ceil(quantile * len(sorted_values)) - 1)
    return sorted_values[index]


def summarize_samples(samples: list[dict[str, object]]) -> dict[str, int | float]:
    """Derive stable latency/error/rate metrics from bounded raw samples."""
    if not samples:
        raise RuntimeBenchmarkError("Benchmark scenario has no samples")
    durations: list[float] = []
    errors = 0
    for item in samples:
        duration = item.get("duration_ms")
        ok = item.get("ok")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise RuntimeBenchmarkError("Benchmark sample duration_ms is invalid")
        if duration < 0:
            raise RuntimeBenchmarkError("Benchmark sample duration_ms must be non-negative")
        if not isinstance(ok, bool):
            raise RuntimeBenchmarkError("Benchmark sample ok flag is invalid")
        durations.append(float(duration))
        if not ok:
            errors += 1

    ordered = sorted(durations)
    total_ms = sum(durations)
    observed_rate = len(samples) / (total_ms / 1000.0) if total_ms > 0 else 0.0
    return {
        "sample_count": len(samples),
        "error_count": errors,
        "error_rate": errors / len(samples),
        "min_ms": min(ordered),
        "mean_ms": total_ms / len(samples),
        "p50_ms": _percentile(ordered, 0.50),
        "p95_ms": _percentile(ordered, 0.95),
        "p99_ms": _percentile(ordered, 0.99),
        "max_ms": max(ordered),
        "observed_rate_per_second": observed_rate,
    }


def policy_digest(policy: dict[str, Any]) -> str:
    """Return the canonical SHA-256 digest of the SLO policy."""
    return sha256_bytes(canonical_json_bytes(policy))


def evaluate_slo(
    scenario: str,
    summary: dict[str, int | float],
    policy: dict[str, Any],
) -> dict[str, object]:
    """Evaluate one benchmark summary against its configured SLO."""
    scenarios = policy.get("scenarios")
    if not isinstance(scenarios, dict):
        raise RuntimeBenchmarkError("SLO policy scenarios are invalid")
    configured = scenarios.get(scenario)
    if not isinstance(configured, dict):
        raise RuntimeBenchmarkError(f"SLO policy has no scenario: {scenario}")

    checks = {
        "minimum_samples": float(summary["sample_count"]) >= float(configured["minimum_samples"]),
        "max_error_rate": float(summary["error_rate"]) <= float(configured["max_error_rate"]),
        "max_p95_ms": float(summary["p95_ms"]) <= float(configured["max_p95_ms"]),
        "max_p99_ms": float(summary["p99_ms"]) <= float(configured["max_p99_ms"]),
        "min_observed_rate_per_second": float(summary["observed_rate_per_second"])
        >= float(configured["min_observed_rate_per_second"]),
    }
    return {
        "verdict": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "thresholds": configured,
    }


def git_head(repo: Path) -> str:
    """Return the exact Git HEAD for a repository."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if len(value) != 40:
        raise RuntimeBenchmarkError(f"Could not resolve Git HEAD for {repo}")
    return value


def require_clean(repo: Path, label: str) -> None:
    """Require an evidence-producing repository to have a clean worktree."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        raise RuntimeBenchmarkError(f"{label} worktree must be clean")


def changed_paths(repo: Path, base: str, head: str) -> list[str]:
    """Return sorted paths changed between two Git revisions."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}..{head}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def runtime_relevant(path: str) -> bool:
    """Return whether a path can change release runtime behavior."""
    return path in RUNTIME_EXACT_PATHS or path.startswith(RUNTIME_PATH_PREFIXES)


def runtime_equivalence(
    repo: Path,
    release_commit: str,
    benchmark_commit: str,
) -> dict[str, object]:
    """Prove benchmark tooling did not change frozen release-runtime paths."""
    paths = changed_paths(repo, release_commit, benchmark_commit)
    runtime_changes = [path for path in paths if runtime_relevant(path)]
    if runtime_changes:
        joined = ", ".join(runtime_changes)
        raise RuntimeBenchmarkError(
            f"Benchmark checkout changed release runtime paths after {release_commit}: {joined}"
        )
    return {
        "release_commit": release_commit,
        "benchmark_commit": benchmark_commit,
        "changed_path_count": len(paths),
        "runtime_changed_paths": [],
        "runtime_equivalent": True,
    }


def release_roots(
    release_manifest: dict[str, Any],
    security_bundle: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, object]:
    """Validate and return the immutable P2.0a/P2.0b/P2.0c roots."""
    manifest_digest = release_manifest.get("manifest_digest")
    security_digest = security_bundle.get("bundle_digest")
    provenance_digest = provenance.get("provenance_digest")
    for label, value in (
        ("release manifest", manifest_digest),
        ("security bundle", security_digest),
        ("build provenance", provenance_digest),
    ):
        if not isinstance(value, str) or len(value) != 64:
            raise RuntimeBenchmarkError(f"{label} digest is invalid")
    release = release_manifest.get("release")
    if not isinstance(release, dict) or provenance.get("release_version") != release.get("version"):
        raise RuntimeBenchmarkError("Build provenance release version does not match manifest")
    upstream = provenance.get("upstream_roots")
    if not isinstance(upstream, dict):
        raise RuntimeBenchmarkError("Build provenance upstream roots are invalid")
    release_root = upstream.get("release_manifest")
    security_root = upstream.get("security_evidence")
    if not isinstance(release_root, dict) or release_root.get("digest") != manifest_digest:
        raise RuntimeBenchmarkError("Build provenance does not bind the release manifest")
    if not isinstance(security_root, dict) or security_root.get("digest") != security_digest:
        raise RuntimeBenchmarkError("Build provenance does not bind the security bundle")
    return {
        "release_manifest_digest": manifest_digest,
        "security_bundle_digest": security_digest,
        "build_provenance_digest": provenance_digest,
    }


def verify_bundle(
    *,
    bundle_path: Path,
    raw_path: Path,
    policy_path: Path,
    release_manifest_path: Path,
    security_bundle_path: Path,
    provenance_path: Path,
    governance_repo: Path,
) -> dict[str, Any]:
    """Verify committed benchmark evidence without rerunning live measurements."""
    bundle = read_json(bundle_path)
    raw = read_json(raw_path)
    policy = read_json(policy_path)
    manifest = read_json(release_manifest_path)
    security = read_json(security_bundle_path)
    provenance = read_json(provenance_path)

    expected_digest = self_digest(bundle, "bundle_digest")
    if bundle.get("bundle_digest") != expected_digest:
        raise RuntimeBenchmarkError("Runtime benchmark bundle digest mismatch")
    if bundle.get("schema_version") != SCHEMA_VERSION or bundle.get("kind") != KIND:
        raise RuntimeBenchmarkError("Runtime benchmark bundle identity is invalid")
    if bundle.get("canonicalization") != CANONICALIZATION:
        raise RuntimeBenchmarkError("Runtime benchmark canonicalization is invalid")

    roots = release_roots(manifest, security, provenance)
    if bundle.get("upstream_roots") != roots:
        raise RuntimeBenchmarkError("Runtime benchmark upstream roots drifted")

    policy_record = bundle.get("policy")
    if not isinstance(policy_record, dict):
        raise RuntimeBenchmarkError("Runtime benchmark policy record is invalid")
    if policy_record.get("digest") != policy_digest(policy):
        raise RuntimeBenchmarkError("Runtime benchmark SLO policy digest mismatch")

    raw_record = bundle.get("raw_measurements")
    if not isinstance(raw_record, dict):
        raise RuntimeBenchmarkError("Runtime benchmark raw record is invalid")
    actual_raw = file_record(raw_path, governance_repo)
    if raw_record != actual_raw:
        raise RuntimeBenchmarkError("Runtime benchmark raw measurement digest mismatch")

    raw_scenarios = raw.get("scenarios")
    bundled_scenarios = bundle.get("scenarios")
    if not isinstance(raw_scenarios, dict) or not isinstance(bundled_scenarios, dict):
        raise RuntimeBenchmarkError("Runtime benchmark scenarios are invalid")

    recomputed: dict[str, object] = {}
    verdicts: list[str] = []
    for scenario, samples in sorted(raw_scenarios.items()):
        if not isinstance(scenario, str) or not isinstance(samples, list):
            raise RuntimeBenchmarkError("Runtime benchmark raw scenario is invalid")
        summary = summarize_samples(samples)
        slo = evaluate_slo(scenario, summary, policy)
        recomputed[scenario] = {"summary": summary, "slo": slo}
        verdicts.append(str(slo["verdict"]))
    if bundled_scenarios != recomputed:
        raise RuntimeBenchmarkError("Runtime benchmark summaries do not match raw measurements")

    expected_verdict = "pass" if verdicts and all(v == "pass" for v in verdicts) else "fail"
    if bundle.get("verdict") != expected_verdict:
        raise RuntimeBenchmarkError("Runtime benchmark aggregate verdict mismatch")

    implementation_commit = bundle.get("benchmark_implementation_commit")
    if not isinstance(implementation_commit, str) or len(implementation_commit) != 40:
        raise RuntimeBenchmarkError("Benchmark implementation commit is invalid")
    components = manifest.get("components")
    if not isinstance(components, dict):
        raise RuntimeBenchmarkError("Release components are invalid")
    release_component = components.get("governance")
    if not isinstance(release_component, dict):
        raise RuntimeBenchmarkError("Governance release component is missing")
    release_commit = release_component.get("commit")
    if not isinstance(release_commit, str):
        raise RuntimeBenchmarkError("Governance release commit is invalid")
    expected_equivalence = runtime_equivalence(
        governance_repo,
        release_commit,
        implementation_commit,
    )
    if bundle.get("runtime_equivalence") != expected_equivalence:
        raise RuntimeBenchmarkError("Runtime equivalence evidence drifted")
    return bundle
