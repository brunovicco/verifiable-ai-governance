from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from scripts.release_runtime_benchmark import (
    RuntimeBenchmarkError,
    evaluate_slo,
    policy_digest,
    self_digest,
    summarize_samples,
)


def _samples(
    values: list[float],
    *,
    failures: set[int] | None = None,
) -> list[dict[str, object]]:
    failures = failures or set()
    return [
        {
            "sequence": index + 1,
            "duration_ms": value,
            "ok": index not in failures,
        }
        for index, value in enumerate(values)
    ]


def _policy() -> dict[str, object]:
    return {
        "scenarios": {
            "scenario": {
                "minimum_samples": 4,
                "max_error_rate": 0.0,
                "max_p95_ms": 10.0,
                "max_p99_ms": 10.0,
                "min_observed_rate_per_second": 100.0,
            }
        }
    }


def test_summary_uses_nearest_rank_percentiles() -> None:
    summary = summarize_samples(_samples([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert summary["p50_ms"] == 3.0
    assert summary["p95_ms"] == 5.0
    assert summary["p99_ms"] == 5.0
    assert summary["error_rate"] == 0.0


def test_summary_counts_failures_without_dropping_latency() -> None:
    summary = summarize_samples(_samples([1.0, 2.0, 3.0, 4.0], failures={1}))
    assert summary["sample_count"] == 4
    assert summary["error_count"] == 1
    assert summary["error_rate"] == 0.25
    assert summary["mean_ms"] == 2.5


def test_slo_passes_only_when_every_check_passes() -> None:
    summary = summarize_samples(_samples([1.0, 2.0, 3.0, 4.0]))
    result = evaluate_slo("scenario", summary, _policy())
    assert result["verdict"] == "pass"
    assert all(result["checks"].values())


def test_slo_failure_is_explicit() -> None:
    summary = summarize_samples(_samples([1.0, 2.0, 3.0, 50.0]))
    result = evaluate_slo("scenario", summary, _policy())
    assert result["verdict"] == "fail"
    assert result["checks"]["max_p95_ms"] is False


def test_policy_digest_is_order_independent() -> None:
    left = {"b": 2, "a": {"d": 4, "c": 3}}
    right = {"a": {"c": 3, "d": 4}, "b": 2}
    assert policy_digest(left) == policy_digest(right)


def test_self_digest_excludes_only_digest_field() -> None:
    value: dict[str, object] = {"kind": "example", "value": 1}
    digest = self_digest(value, "bundle_digest")
    sealed = {**value, "bundle_digest": digest}
    assert self_digest(sealed, "bundle_digest") == digest
    sealed["value"] = 2
    assert self_digest(sealed, "bundle_digest") != digest


def test_schema_is_closed_at_top_level() -> None:
    schema = json.loads(Path("schemas/release-runtime-benchmark.schema.json").read_text())
    assert schema["additionalProperties"] is False
    assert "bundle_digest" in schema["required"]


def test_policy_contains_all_live_scenarios() -> None:
    policy = json.loads(Path("config/release-runtime-slo-policy.json").read_text())
    assert set(policy["scenarios"]) == {
        "governance_ready",
        "governed_routing_allowed",
        "runtime_telemetry_query",
        "runtime_control_state_read",
        "runtime_assurance_evaluation",
    }


def test_tampered_sample_changes_summary() -> None:
    original = _samples([1.0, 2.0, 3.0, 4.0])
    tampered = copy.deepcopy(original)
    tampered[3]["duration_ms"] = 400.0
    assert summarize_samples(original) != summarize_samples(tampered)


def test_empty_samples_fail_closed() -> None:
    with pytest.raises(RuntimeBenchmarkError, match="no samples"):
        summarize_samples([])


def test_git_runtime_equivalence_helper_rejects_runtime_change(tmp_path: Path) -> None:
    from scripts.release_runtime_benchmark import git_head, runtime_equivalence

    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "config", "user.name", "P2 Test"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "p2@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    runtime = tmp_path / "apps/api/src/example"
    runtime.mkdir(parents=True)
    (runtime / "service.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "release"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    release = git_head(tmp_path)
    (runtime / "service.py").write_text("VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "drift"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    with pytest.raises(RuntimeBenchmarkError, match="changed release runtime paths"):
        runtime_equivalence(tmp_path, release, git_head(tmp_path))
