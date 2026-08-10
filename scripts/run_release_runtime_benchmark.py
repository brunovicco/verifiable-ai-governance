"""Run the live P2.0d runtime benchmark and persist content-addressed evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from scripts.release_runtime_benchmark import (
    CANONICALIZATION,
    KIND,
    SCHEMA_VERSION,
    RuntimeBenchmarkError,
    evaluate_slo,
    file_record,
    git_head,
    policy_digest,
    read_json,
    release_roots,
    require_clean,
    runtime_equivalence,
    self_digest,
    summarize_samples,
)
from scripts.verify_p1_7_cross_repo_telemetry_e2e import (
    _list_runtime_events,
    _wait_http_ready,
    governance_headers,
    load_agent_id,
)
from scripts.verify_p1_8_cross_repo_assurance_e2e import (
    _dispose_database_engine,
    _read_runtime_state,
)

_DEFAULT_MANIFEST = Path("artifacts/demo/canonical-seed-manifest.json")
_DEFAULT_OUTPUT_DIR = Path("artifacts/release/benchmark")
_DEFAULT_POLICY = Path("config/release-runtime-slo-policy.json")
_DEFAULT_GOVERNANCE_URL = "http://127.0.0.1:8000"
_DEFAULT_ROUTER_URL = "http://127.0.0.1:8082"
_DEFAULT_USER_ID = "demo.requester"


def _routing_payload(task_id: str) -> dict[str, object]:
    return {
        "workflow_id": "p2-0d-runtime-benchmark",
        "task_id": task_id,
        "workload": "opinion_drafting",
        "context_tokens_estimated": 3000,
        "max_output_tokens_estimated": 900,
        "structured_output_required": False,
        "max_latency_ms": 30_000,
        "max_cost_usd": "0.30",
    }


def _measure(operation: Callable[[], tuple[bool, int | None]]) -> dict[str, object]:
    start = time.perf_counter_ns()
    ok = False
    status_code: int | None = None
    try:
        ok, status_code = operation()
    except (httpx.HTTPError, RuntimeBenchmarkError):
        ok = False
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    result: dict[str, object] = {"duration_ms": elapsed_ms, "ok": ok}
    if status_code is not None:
        result["status_code"] = status_code
    return result


def _http_ready(client: httpx.Client, governance_url: str) -> tuple[bool, int]:
    response = client.get(f"{governance_url}/health/ready")
    return response.status_code == 200, response.status_code


def _routing_allowed(
    client: httpx.Client,
    *,
    governance_url: str,
    agent_id: str,
    user_id: str,
    task_id: str,
) -> tuple[bool, int]:
    response = client.post(
        f"{governance_url}/api/v1/agents/{agent_id}/routing-decisions",
        headers=governance_headers(user_id),
        json=_routing_payload(task_id),
    )
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return False, response.status_code
    ok = (
        response.status_code == 200
        and isinstance(payload, dict)
        and payload.get("outcome") == "allowed"
        and payload.get("decision_source") == "policy_model_router"
        and isinstance(payload.get("selected_model_group"), str)
    )
    return ok, response.status_code


def _telemetry_query(
    client: httpx.Client,
    *,
    governance_url: str,
    agent_id: str,
    user_id: str,
) -> tuple[bool, int]:
    response = client.get(
        f"{governance_url}/api/v1/agents/{agent_id}/runtime-telemetry",
        headers=governance_headers(user_id),
    )
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return False, response.status_code
    return response.status_code == 200 and isinstance(payload, list), response.status_code


def _assurance_evaluation(
    client: httpx.Client,
    *,
    governance_url: str,
    agent_id: str,
    user_id: str,
) -> tuple[bool, int]:
    response = client.post(
        f"{governance_url}/api/v1/agents/{agent_id}/runtime-assurance-evaluations",
        headers=governance_headers(user_id),
    )
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return False, response.status_code
    ok = (
        response.status_code == 201
        and isinstance(payload, dict)
        and payload.get("agent_id") == agent_id
        and isinstance(payload.get("evidence_digest"), str)
    )
    return ok, response.status_code


def _run_async_state(runner: asyncio.Runner, agent_id: str) -> tuple[bool, None]:
    state = runner.run(_read_runtime_state(agent_id=agent_id))
    ok = (
        state.get("agent_id") == agent_id
        and state.get("kill_switch_enabled") is True
        and state.get("kill_switch_engaged") is False
    )
    return ok, None


def _measure_sample(
    operation: Callable[[int], tuple[bool, int | None]],
    index: int,
) -> dict[str, object]:
    def invoke() -> tuple[bool, int | None]:
        return operation(index)

    return _measure(invoke)


def _collect(
    *,
    count: int,
    warmup: int,
    operation: Callable[[int], tuple[bool, int | None]],
) -> list[dict[str, object]]:
    for index in range(warmup):
        ok, _ = operation(-(index + 1))
        if not ok:
            raise RuntimeBenchmarkError("Benchmark warm-up failed")
    samples: list[dict[str, object]] = []
    for index in range(count):
        measured = _measure_sample(operation, index)
        measured["sequence"] = index + 1
        samples.append(measured)
    return samples


def _require_assurance_ready(
    client: httpx.Client,
    *,
    governance_url: str,
    agent_id: str,
    user_id: str,
) -> None:
    events = _list_runtime_events(
        client,
        governance_url=governance_url,
        agent_id=agent_id,
        user_id=user_id,
    )
    if len(events) < 2:
        raise RuntimeBenchmarkError(
            "P2.0d requires at least two persisted runtime telemetry events; "
            "run the P1.9e live governed-actuation E2E first"
        )
    response = client.get(
        f"{governance_url}/api/v1/agents/{agent_id}/runtime-assurance-policy",
        headers=governance_headers(user_id),
    )
    if response.status_code != 200:
        raise RuntimeBenchmarkError(
            "P2.0d requires an existing Runtime Assurance policy from P1.8/P1.9"
        )
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("enabled") is not True:
        raise RuntimeBenchmarkError("Runtime Assurance policy must already be enabled")


def _environment() -> dict[str, object]:
    return {
        "system": platform.system(),
        "system_release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "benchmark_mode": "sequential",
        "remote_llm_inference": False,
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    """Run live control-path measurements and persist benchmark evidence."""
    repo = Path(__file__).resolve().parents[1]
    require_clean(repo, "Governance")
    require_clean(args.policy_model_router_repo, "Policy Model Router")
    benchmark_commit = git_head(repo)

    manifest = read_json(repo / "artifacts/release/release-manifest.json")
    security = read_json(repo / "artifacts/release/security/security-evidence-bundle.json")
    provenance = read_json(repo / "artifacts/release/provenance/release-build-provenance.json")
    policy = read_json(args.policy)
    roots = release_roots(manifest, security, provenance)

    components = manifest.get("components")
    if not isinstance(components, dict):
        raise RuntimeBenchmarkError("P2.0d release component bindings are invalid")
    release_component = components.get("governance")
    router_component = components.get("policy_model_router")
    if not isinstance(release_component, dict) or not isinstance(router_component, dict):
        raise RuntimeBenchmarkError("P2.0d release component bindings are invalid")
    release_commit = release_component.get("commit")
    router_commit = router_component.get("commit")
    if not isinstance(release_commit, str) or not isinstance(router_commit, str):
        raise RuntimeBenchmarkError("P2.0d source commit bindings are invalid")
    if git_head(args.policy_model_router_repo) != router_commit:
        raise RuntimeBenchmarkError(
            f"Policy Model Router must be checked out exactly at {router_commit}"
        )
    equivalence = runtime_equivalence(repo, release_commit, benchmark_commit)

    governance_url = args.governance_url.rstrip("/")
    router_url = args.router_url.rstrip("/")
    agent_id = load_agent_id(args.agent_id, args.manifest)
    _wait_http_ready(f"{governance_url}/health/ready", timeout_seconds=args.timeout_seconds)
    _wait_http_ready(f"{router_url}/readyz", timeout_seconds=args.timeout_seconds)

    runner = asyncio.Runner()
    raw_scenarios: dict[str, list[dict[str, object]]] = {}
    try:
        initial_state = runner.run(_read_runtime_state(agent_id=agent_id))
        if initial_state.get("kill_switch_engaged") is not False:
            raise RuntimeBenchmarkError(
                "P2.0d requires the canonical Agent restored with kill switch inactive"
            )
        with httpx.Client(timeout=args.timeout_seconds) as client:
            _require_assurance_ready(
                client,
                governance_url=governance_url,
                agent_id=agent_id,
                user_id=args.user_id,
            )
            raw_scenarios["governance_ready"] = _collect(
                count=args.samples,
                warmup=args.warmup,
                operation=lambda _: _http_ready(client, governance_url),
            )
            raw_scenarios["governed_routing_allowed"] = _collect(
                count=args.samples,
                warmup=args.warmup,
                operation=lambda index: _routing_allowed(
                    client,
                    governance_url=governance_url,
                    agent_id=agent_id,
                    user_id=args.user_id,
                    task_id=f"p2-0d-routing-{benchmark_commit[:12]}-{index}",
                ),
            )
            raw_scenarios["runtime_telemetry_query"] = _collect(
                count=args.samples,
                warmup=args.warmup,
                operation=lambda _: _telemetry_query(
                    client,
                    governance_url=governance_url,
                    agent_id=agent_id,
                    user_id=args.user_id,
                ),
            )
            raw_scenarios["runtime_control_state_read"] = _collect(
                count=args.samples,
                warmup=args.warmup,
                operation=lambda _: _run_async_state(runner, agent_id),
            )
            raw_scenarios["runtime_assurance_evaluation"] = _collect(
                count=args.assurance_samples,
                warmup=min(args.warmup, 2),
                operation=lambda _: _assurance_evaluation(
                    client,
                    governance_url=governance_url,
                    agent_id=agent_id,
                    user_id=args.user_id,
                ),
            )
    finally:
        runner.run(_dispose_database_engine())
        runner.close()

    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    raw = {
        "schema_version": "1.0",
        "kind": "verifiable-ai-governance/release-runtime-benchmark-raw",
        "generated_at": generated_at,
        "benchmark_implementation_commit": benchmark_commit,
        "scenarios": raw_scenarios,
    }

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "runtime-benchmark-raw.json"
    raw_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    scenarios: dict[str, object] = {}
    verdicts: list[str] = []
    for scenario, samples in sorted(raw_scenarios.items()):
        summary = summarize_samples(samples)
        slo = evaluate_slo(scenario, summary, policy)
        scenarios[scenario] = {"summary": summary, "slo": slo}
        verdicts.append(str(slo["verdict"]))

    aggregate = "pass" if verdicts and all(value == "pass" for value in verdicts) else "fail"
    release = manifest.get("release")
    if not isinstance(release, dict) or not isinstance(release.get("version"), str):
        raise RuntimeBenchmarkError("P2.0d release version is invalid")
    bundle: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "canonicalization": CANONICALIZATION,
        "release_version": release["version"],
        "generated_at": generated_at,
        "benchmark_implementation_commit": benchmark_commit,
        "upstream_roots": roots,
        "runtime_equivalence": equivalence,
        "environment": _environment(),
        "policy": {
            "path": args.policy.resolve().relative_to(repo.resolve()).as_posix(),
            "digest": policy_digest(policy),
            "profile": policy.get("profile"),
        },
        "raw_measurements": file_record(raw_path, repo),
        "scenarios": scenarios,
        "verdict": aggregate,
    }
    bundle["bundle_digest"] = self_digest(bundle, "bundle_digest")
    bundle_path = output_dir / "runtime-benchmark-bundle.json"
    bundle_path.write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return bundle


def parse_args() -> argparse.Namespace:
    """Parse bounded P2.0d benchmark command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--governance-url", default=_DEFAULT_GOVERNANCE_URL)
    parser.add_argument("--router-url", default=_DEFAULT_ROUTER_URL)
    parser.add_argument("--user-id", default=_DEFAULT_USER_ID)
    parser.add_argument("--agent-id")
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument("--policy", type=Path, default=_DEFAULT_POLICY)
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--policy-model-router-repo",
        type=Path,
        default=Path("../policy-model-router"),
    )
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--assurance-samples", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args()
    if args.samples < 50:
        parser.error("--samples must be at least 50")
    if args.assurance_samples < 10:
        parser.error("--assurance-samples must be at least 10")
    if args.warmup < 0:
        parser.error("--warmup must be non-negative")
    return args


def main() -> int:
    """Generate runtime benchmark evidence and return its release verdict."""
    args = parse_args()
    try:
        bundle = run(args)
    except (RuntimeBenchmarkError, OSError, subprocess.SubprocessError) as exc:
        print(f"[p2.0d] FAILED: {exc}")
        return 1
    print("[p2.0d] GENERATED")
    print(f"[p2.0d] verdict: {bundle['verdict']}")
    print(f"[p2.0d] digest: {bundle['bundle_digest']}")
    return 0 if bundle["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
