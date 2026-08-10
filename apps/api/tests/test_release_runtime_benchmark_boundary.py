from pathlib import Path

_CORE = Path("scripts/release_runtime_benchmark.py")
_RUNNER = Path("scripts/run_release_runtime_benchmark.py")
_VERIFIER = Path("scripts/verify_release_runtime_benchmark.py")


def test_verifier_does_not_execute_live_network_or_benchmark_operations() -> None:
    source = _VERIFIER.read_text(encoding="utf-8").lower()
    for forbidden in (
        "httpx",
        "requests.",
        "urllib",
        "subprocess.run",
        "runtime-assurance-evaluations",
        "routing-decisions",
    ):
        assert forbidden not in source


def test_live_benchmark_does_not_invoke_llm_or_direct_runtime_actuation() -> None:
    source = _RUNNER.read_text(encoding="utf-8").lower()
    for forbidden in (
        "/runtime-control/activate",
        "/runtime-control/deactivate",
        "/kill-switch/engage",
        "/kill-switch/restore",
        "runtimecontrolservice.activate",
        "runtimecontrolservice.deactivate",
        "openai",
        "anthropic",
        "bedrock",
        "invoke_model",
        "chat.completions",
    ):
        assert forbidden not in source


def test_live_benchmark_reuses_existing_governance_boundaries() -> None:
    source = _RUNNER.read_text(encoding="utf-8")
    assert "/routing-decisions" in source
    assert "/runtime-telemetry" in source
    assert "/runtime-assurance-evaluations" in source
    assert "_read_runtime_state" in source
    assert "decision_source" in source
    assert "policy_model_router" in source


def test_core_runtime_equivalence_scope_covers_production_paths() -> None:
    source = _CORE.read_text(encoding="utf-8")
    assert '"apps/api/src/"' in source
    assert '"apps/api/alembic/"' in source
    assert '"packages/governance-schemas/src/"' in source
    assert '"packages/policy-engine/src/"' in source
    assert '"uv.lock"' in source


def test_raw_evidence_does_not_persist_response_bodies_or_credentials() -> None:
    source = _RUNNER.read_text(encoding="utf-8").lower()
    assert '"duration_ms"' in source
    assert '"status_code"' in source
    assert '"sequence"' in source
    assert "api_key" not in source
    assert "authorization" not in source
    assert "response.text" not in source
