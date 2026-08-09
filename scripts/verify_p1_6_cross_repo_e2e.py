"""Live P1.6 cross-repository runtime-control verification harness."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

_MAX_PROXY_BODY_BYTES = 1_048_576
_DEFAULT_GOVERNANCE_URL = "http://127.0.0.1:8000"
_DEFAULT_ROUTER_URL = "http://127.0.0.1:8082"
_DEFAULT_PROXY_HOST = "127.0.0.1"
_DEFAULT_PROXY_PORT = 18082
_DEFAULT_CREDIT_DESK_PORT = 8199
_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_USER_ID = "demo.requester"
_DEFAULT_MANIFEST = Path("artifacts/demo/canonical-seed-manifest.json")
_DEFAULT_REPORT = Path("artifacts/e2e/p1.6-cross-repo-live-report.json")

_ALLOWED_FORWARD_HEADERS = frozenset(
    {
        "content-type",
        "x-api-key",
        "x-correlation-id",
        "traceparent",
        "tracestate",
    }
)


class VerificationError(RuntimeError):
    """Raised when one required P1.6 invariant is not observed."""


@dataclass(frozen=True, slots=True)
class CapturedRouterRequest:
    """One exact request Governance sent through the barrier proxy."""

    ordinal: int
    body: bytes
    headers: dict[str, str]
    authorization_id: str
    agent_version: int
    workflow_id: str
    task_id: str
    correlation_id: str

    def report(self) -> dict[str, object]:
        """Return a secret-free report representation."""
        return {
            "ordinal": self.ordinal,
            "authorization_id": self.authorization_id,
            "agent_version": self.agent_version,
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            "correlation_id": self.correlation_id,
        }


@dataclass(slots=True)
class BarrierState:
    """Mutable state shared by the proxy thread and scenario driver."""

    governance_url: str
    router_url: str
    agent_id: str
    user_id: str
    timeout_seconds: float
    lock: threading.Lock = field(default_factory=threading.Lock)
    request_count: int = 0
    activate_on_next: bool = False
    activation_response: dict[str, Any] | None = None
    activation_error: str | None = None
    captures: list[CapturedRouterRequest] = field(default_factory=list)

    def arm_activation(self) -> None:
        """Activate the kill switch after the next signed request reaches the proxy."""
        with self.lock:
            if self.activate_on_next:
                raise VerificationError("Barrier proxy is already armed")
            self.activate_on_next = True

    def record(self, body: bytes, headers: dict[str, str]) -> tuple[CapturedRouterRequest, bool]:
        """Capture a bounded Router request and atomically consume the barrier arm."""
        parsed = parse_router_envelope(body)
        with self.lock:
            self.request_count += 1
            capture = CapturedRouterRequest(
                ordinal=self.request_count,
                body=body,
                headers=headers,
                authorization_id=parsed["authorization_id"],
                agent_version=parsed["agent_version"],
                workflow_id=parsed["workflow_id"],
                task_id=parsed["task_id"],
                correlation_id=headers.get("x-correlation-id", ""),
            )
            self.captures.append(capture)
            activate = self.activate_on_next
            self.activate_on_next = False
        return capture, activate

    def activate(self, expected_version: int) -> None:
        """Synchronously commit/project the kill switch before forwarding the captured request."""
        payload = {
            "expected_version": expected_version,
            "reason": "P1.6d controlled TOCTOU barrier verification",
            "incident_id": None,
            "evidence_reference": "p1.6d-cross-repo-live-e2e",
        }
        url = (
            f"{self.governance_url.rstrip('/')}/api/v1/agents/"
            f"{self.agent_id}/runtime-control/activate"
        )
        try:
            response = httpx.post(
                url,
                headers=governance_headers(self.user_id),
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            document = require_json_object(response)
            require_equal(document.get("target_state"), "active", "activation target_state")
            require_equal(document.get("status"), "applied", "activation status")
            require_equal(document.get("kill_switch_engaged"), True, "kill switch state")
            self.activation_response = document
        except Exception as exc:
            self.activation_error = str(exc)
            raise


class _BarrierProxy(ThreadingHTTPServer):
    """HTTP server carrying the shared P1.6 barrier state."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], state: BarrierState) -> None:
        super().__init__(address, _BarrierHandler)
        self.state = state


class _BarrierHandler(BaseHTTPRequestHandler):
    """Forward Governance Router calls, activating Runtime Control at the armed barrier."""

    server: _BarrierProxy

    def do_POST(self) -> None:  # noqa: N802
        """Handle the single Router route endpoint used by the live scenario."""
        if self.path != "/route":
            self.send_error(404)
            return

        try:
            body = self._read_bounded_body()
            headers = {
                key.lower(): value
                for key, value in self.headers.items()
                if key.lower() in _ALLOWED_FORWARD_HEADERS
            }
            capture, activate = self.server.state.record(body, headers)

            if activate:
                self.server.state.activate(capture.agent_version)

            forward_headers = {
                key: value for key, value in headers.items() if key != "content-length"
            }
            response = httpx.post(
                f"{self.server.state.router_url.rstrip('/')}/route",
                headers=forward_headers,
                content=body,
                timeout=self.server.state.timeout_seconds,
            )
            self.send_response(response.status_code)
            self.send_header(
                "Content-Type",
                response.headers.get("content-type", "application/json"),
            )
            correlation_id = response.headers.get("x-correlation-id")
            if correlation_id:
                self.send_header("X-Correlation-Id", correlation_id)
            self.end_headers()
            self.wfile.write(response.content)
        except Exception as exc:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "error": {
                            "code": "p1_6_barrier_proxy_failed",
                            "message": type(exc).__name__,
                        }
                    }
                ).encode("utf-8")
            )

    def log_message(self, format: str, *args: object) -> None:
        """Keep the verification output deterministic and concise."""
        del format, args

    def _read_bounded_body(self) -> bytes:
        raw_length = self.headers.get("content-length")
        if raw_length is None:
            raise VerificationError("Barrier proxy requires Content-Length")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise VerificationError("Barrier proxy received invalid Content-Length") from exc
        if length < 0 or length > _MAX_PROXY_BODY_BYTES:
            raise VerificationError("Barrier proxy request exceeds the bounded body size")
        return self.rfile.read(length)


@dataclass(frozen=True, slots=True)
class ScenarioConfig:
    """Resolved URLs, identities and local repository paths."""

    governance_url: str
    router_url: str
    proxy_host: str
    proxy_port: int
    agent_id: str
    user_id: str
    timeout_seconds: float
    report_path: Path
    credit_desk_repo: Path | None
    credit_desk_port: int
    skip_credit_desk: bool


def governance_headers(user_id: str) -> dict[str, str]:
    """Return the local/demo identity header used by the canonical scenario."""
    return {"X-User-Id": user_id}


def parse_router_envelope(body: bytes) -> dict[str, Any]:
    """Extract only the signed identifiers needed by the barrier and report."""
    try:
        payload = json.loads(body)
        request = payload["request"]
        authorization = payload["authorization"]
        claims = authorization["claims"]
        subject = claims["subject"]
        result = {
            "authorization_id": claims["authorization_id"],
            "agent_version": subject["agent_version"],
            "workflow_id": request["workflow_id"],
            "task_id": request["task_id"],
        }
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise VerificationError("Barrier proxy received an invalid Router envelope") from exc

    if not isinstance(result["authorization_id"], str) or not result["authorization_id"]:
        raise VerificationError("Captured authorization_id is invalid")
    if (
        not isinstance(result["agent_version"], int)
        or isinstance(result["agent_version"], bool)
        or result["agent_version"] < 1
    ):
        raise VerificationError("Captured agent_version is invalid")
    for name in ("workflow_id", "task_id"):
        value = result[name]
        if not isinstance(value, str) or not value:
            raise VerificationError(f"Captured {name} is invalid")
    return result


def require_json_object(response: httpx.Response) -> dict[str, Any]:
    """Require a JSON object response without trusting arbitrary shapes."""
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerificationError("Expected a JSON response") from exc
    if not isinstance(payload, dict):
        raise VerificationError("Expected a JSON object response")
    return payload


def require_equal(actual: object, expected: object, label: str) -> None:
    """Raise a stable verification failure for a mismatched invariant."""
    if actual != expected:
        raise VerificationError(f"{label}: expected {expected!r}, got {actual!r}")


def routing_payload(task_id: str) -> dict[str, object]:
    """Build one deterministic opinion-drafting routing command."""
    return {
        "workflow_id": "p1-6-cross-repo-live-e2e",
        "task_id": task_id,
        "workload": "opinion_drafting",
        "context_tokens_estimated": 3000,
        "max_output_tokens_estimated": 900,
        "structured_output_required": False,
        "max_latency_ms": 30_000,
        "max_cost_usd": "0.30",
    }


def load_agent_id(explicit: str | None, manifest_path: Path) -> str:
    """Resolve the canonical agent identifier from CLI or seed manifest."""
    if explicit is not None:
        value = explicit.strip()
        if not value:
            raise VerificationError("--agent-id must not be blank")
        return value
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        value = payload["agent_id"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise VerificationError(
            f"Could not load canonical agent id from {manifest_path}; "
            "pass --agent-id or run the canonical seed"
        ) from exc
    if not isinstance(value, str) or not value:
        raise VerificationError("Canonical manifest contains an invalid agent_id")
    return value


def _request_routing(
    client: httpx.Client,
    config: ScenarioConfig,
    task_id: str,
) -> tuple[int, dict[str, Any]]:
    url = f"{config.governance_url.rstrip('/')}/api/v1/agents/{config.agent_id}/routing-decisions"
    response = client.post(
        url,
        headers=governance_headers(config.user_id),
        json=routing_payload(task_id),
    )
    return response.status_code, require_json_object(response)


def _deactivate(
    client: httpx.Client,
    config: ScenarioConfig,
    *,
    expected_version: int,
) -> dict[str, Any]:
    url = (
        f"{config.governance_url.rstrip('/')}/api/v1/agents/"
        f"{config.agent_id}/runtime-control/deactivate"
    )
    response = client.post(
        url,
        headers=governance_headers(config.user_id),
        json={
            "expected_version": expected_version,
            "reason": "P1.6d controlled restore after kill-switch verification",
            "incident_id": None,
            "evidence_reference": "p1.6d-cross-repo-live-e2e",
        },
    )
    response.raise_for_status()
    document = require_json_object(response)
    require_equal(document.get("target_state"), "inactive", "deactivation target_state")
    require_equal(document.get("status"), "applied", "deactivation status")
    require_equal(document.get("kill_switch_engaged"), False, "restored kill switch state")
    return document


def _verify_persisted_violation(
    client: httpx.Client,
    config: ScenarioConfig,
    decision_id: str,
) -> dict[str, Any]:
    url = f"{config.governance_url.rstrip('/')}/api/v1/agents/{config.agent_id}/routing-decisions"
    response = client.get(url, headers=governance_headers(config.user_id))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise VerificationError("Routing evidence endpoint did not return a list")
    matches = [item for item in payload if isinstance(item, dict) and item.get("id") == decision_id]
    if len(matches) != 1:
        raise VerificationError("Kill-switch routing evidence was not persisted exactly once")
    record = matches[0]
    require_equal(record.get("outcome"), "blocked", "persisted B outcome")
    require_equal(record.get("reason_code"), "kill_switch_engaged", "persisted B reason")
    violation = record.get("runtime_violation")
    if not isinstance(violation, dict):
        raise VerificationError("Persisted B decision is missing RuntimeViolation evidence")
    event = violation.get("event")
    if not isinstance(event, dict):
        raise VerificationError("Persisted RuntimeViolation event is invalid")
    require_equal(event.get("code"), "kill_switch_engaged", "persisted violation code")
    authorization = event.get("authorization")
    if not isinstance(authorization, dict):
        raise VerificationError("Persisted violation authorization binding is missing")
    require_equal(authorization.get("state"), "verified", "violation authorization state")
    return record


def _retry_captured_authorization(
    client: httpx.Client,
    config: ScenarioConfig,
    capture: CapturedRouterRequest,
) -> dict[str, Any]:
    response = client.post(
        f"{config.router_url.rstrip('/')}/route",
        headers=capture.headers,
        content=capture.body,
    )
    require_equal(response.status_code, 403, "old B Router status after restore")
    document = require_json_object(response)
    error = document.get("error")
    if not isinstance(error, dict):
        raise VerificationError("Old B denial is missing error envelope")
    require_equal(error.get("code"), "runtime_authorization_revoked", "old B denial code")
    violation = document.get("violation")
    if not isinstance(violation, dict):
        raise VerificationError("Old B denial is missing RuntimeViolation")
    event = violation.get("event")
    if not isinstance(event, dict):
        raise VerificationError("Old B RuntimeViolation event is invalid")
    require_equal(event.get("code"), "runtime_authorization_revoked", "old B violation code")
    authorization = event.get("authorization")
    if not isinstance(authorization, dict):
        raise VerificationError("Old B revocation evidence lost authorization binding")
    require_equal(
        authorization.get("authorization_id"),
        capture.authorization_id,
        "old B authorization_id",
    )
    require_equal(authorization.get("state"), "verified", "old B authorization state")
    return document


def _wait_http_ready(url: str, *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=1.0)
            if response.status_code < 500:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.2)
    raise VerificationError(f"Service did not become reachable: {url}")


def _run_credit_desk_probe(config: ScenarioConfig) -> dict[str, Any]:
    if config.credit_desk_repo is None:
        raise VerificationError("Credit Desk repository path is required for the live probe")
    repo = config.credit_desk_repo.resolve()
    if not (repo / "pyproject.toml").is_file():
        raise VerificationError(f"Credit Desk repository is invalid: {repo}")

    host = "127.0.0.1"
    base_url = f"http://{host}:{config.credit_desk_port}"
    env = {
        **os.environ,
        "DECISAO_AGENT_A2A_HOST": host,
        "DECISAO_AGENT_A2A_PORT": str(config.credit_desk_port),
        "DECISAO_AGENT_GOVERNANCE_BASE_URL": config.governance_url,
        "DECISAO_AGENT_GOVERNANCE_AGENT_ID": config.agent_id,
        "DECISAO_AGENT_GOVERNANCE_DEV_USER_ID": config.user_id,
        "DECISAO_AGENT_ENV": "p1.6-live-e2e",
        "A2A_OTEL_ENABLED": "false",
    }
    command = [
        "uv",
        "run",
        "--package",
        "decisao-agent",
        "python",
        "-m",
        "decisao_agent.entrypoints.a2a_server",
    ]
    process = subprocess.Popen(
        command,
        cwd=repo,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_http_ready(
            f"{base_url}/.well-known/agent-card.json",
            timeout_seconds=max(config.timeout_seconds, 20.0),
        )
        probe = Path(__file__).with_name("p1_6_credit_desk_probe.py").resolve()
        completed = subprocess.run(
            [
                "uv",
                "run",
                "--package",
                "decisao-agent",
                "python",
                str(probe),
                "--url",
                base_url,
            ],
            cwd=repo,
            env=env,
            text=True,
            capture_output=True,
            timeout=max(config.timeout_seconds, 30.0),
            check=False,
        )
        if completed.returncode != 0:
            raise VerificationError(
                "Credit Desk live probe failed: "
                + (completed.stderr.strip() or completed.stdout.strip())
            )
        try:
            payload = json.loads(completed.stdout.strip())
        except json.JSONDecodeError as exc:
            raise VerificationError("Credit Desk probe did not return JSON") from exc
        if not isinstance(payload, dict):
            raise VerificationError("Credit Desk probe result is invalid")
        require_equal(payload.get("decision"), "APPROVAL_RECOMMENDED", "credit decision")
        require_equal(payload.get("narrative"), None, "kill-switch narrative")
        return payload
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _git_head(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_scenario(config: ScenarioConfig) -> dict[str, object]:
    """Run A/B/kill/restore/B-revoked/C plus the live Credit Desk fail-closed probe."""
    state = BarrierState(
        governance_url=config.governance_url,
        router_url=config.router_url,
        agent_id=config.agent_id,
        user_id=config.user_id,
        timeout_seconds=config.timeout_seconds,
    )
    proxy = _BarrierProxy((config.proxy_host, config.proxy_port), state)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()

    report: dict[str, object] = {
        "schema_version": "1.0",
        "agent_id": config.agent_id,
        "governance_url": config.governance_url,
        "router_url": config.router_url,
        "proxy": f"http://{config.proxy_host}:{config.proxy_port}",
        "steps": {},
    }
    steps = report["steps"]
    assert isinstance(steps, dict)

    try:
        with httpx.Client(timeout=config.timeout_seconds) as client:
            # A proves normal issuance + replay consumption before the emergency transition.
            status_a, decision_a = _request_routing(client, config, "p1-6-a-consumed")
            require_equal(status_a, 200, "A Governance status")
            require_equal(decision_a.get("outcome"), "allowed", "A outcome")
            if state.request_count != 1:
                raise VerificationError(
                    "Governance is not routing through the P1.6 barrier proxy; "
                    "check POLICY_MODEL_ROUTER_BASE_URL"
                )
            capture_a = state.captures[-1]
            steps["A_consumed"] = {
                "routing_decision_id": decision_a.get("id"),
                **capture_a.report(),
            }

            # B is signed while Governance still observes inactive. The barrier then activates
            # Runtime Control before the exact request is forwarded to the real Router.
            state.arm_activation()
            status_b, decision_b = _request_routing(client, config, "p1-6-b-pre-kill")
            require_equal(status_b, 422, "B Governance status")
            require_equal(decision_b.get("outcome"), "blocked", "B outcome")
            require_equal(decision_b.get("reason_code"), "kill_switch_engaged", "B reason")
            if state.activation_error is not None:
                raise VerificationError(f"Barrier activation failed: {state.activation_error}")
            if state.activation_response is None:
                raise VerificationError("Barrier did not activate Runtime Control")
            capture_b = state.captures[-1]
            if capture_b.ordinal != 2:
                raise VerificationError("B was not the second Router request")
            persisted_b = _verify_persisted_violation(
                client,
                config,
                str(decision_b.get("id")),
            )
            steps["B_kill_switch"] = {
                "routing_decision_id": decision_b.get("id"),
                "reason_code": decision_b.get("reason_code"),
                "runtime_violation_persisted": persisted_b.get("runtime_violation") is not None,
                "activation": {
                    key: state.activation_response.get(key)
                    for key in (
                        "transition_id",
                        "control_epoch",
                        "revoked_through_agent_version",
                        "agent_version",
                    )
                },
                **capture_b.report(),
            }

            # While active, the real Credit Desk must keep its deterministic decision and skip
            # the optional LLM narrative because Governance rejects model routing.
            if config.skip_credit_desk:
                steps["credit_desk_kill_switch"] = {"skipped": True}
            else:
                credit_result = _run_credit_desk_probe(config)
                steps["credit_desk_kill_switch"] = {
                    "skipped": False,
                    "decision": credit_result.get("decision"),
                    "narrative": credit_result.get("narrative"),
                    "policy_version": credit_result.get("policy_version"),
                }

            activated_version = state.activation_response.get("agent_version")
            if (
                not isinstance(activated_version, int)
                or isinstance(activated_version, bool)
                or activated_version <= capture_b.agent_version
            ):
                raise VerificationError("Activation did not advance agent_version")

            deactivation = _deactivate(
                client,
                config,
                expected_version=activated_version,
            )
            restored_version = deactivation.get("agent_version")
            if (
                not isinstance(restored_version, int)
                or isinstance(restored_version, bool)
                or restored_version <= activated_version
            ):
                raise VerificationError("Deactivation did not advance agent_version")
            floor = deactivation.get("revoked_through_agent_version")
            require_equal(floor, activated_version, "restore revocation floor")
            if floor < capture_b.agent_version:
                raise VerificationError(
                    "Restore revocation floor does not cover pre-kill authorization B"
                )
            steps["restore"] = {
                key: deactivation.get(key)
                for key in (
                    "transition_id",
                    "control_epoch",
                    "revoked_through_agent_version",
                    "agent_version",
                )
            }

            # B was never consumed: runtime control runs before replay. After restore, exact B is
            # denied by the persistent revocation floor, not by replay.
            revoked_b = _retry_captured_authorization(client, config, capture_b)
            steps["B_after_restore"] = {
                "authorization_id": capture_b.authorization_id,
                "reason_code": revoked_b["error"]["code"],
            }

            # Fresh C is issued against the incremented Agent generation and must route normally.
            status_c, decision_c = _request_routing(client, config, "p1-6-c-post-restore")
            require_equal(status_c, 200, "C Governance status")
            require_equal(decision_c.get("outcome"), "allowed", "C outcome")
            capture_c = state.captures[-1]
            if capture_c.agent_version <= capture_b.agent_version:
                raise VerificationError("C did not carry a newer signed agent_version")
            steps["C_allowed"] = {
                "routing_decision_id": decision_c.get("id"),
                **capture_c.report(),
            }

        report["result"] = "passed"
        _write_report(config.report_path, report)
        return report
    except Exception:
        report["result"] = "failed"
        report["captures"] = [capture.report() for capture in state.captures]
        _write_report(config.report_path, report)
        raise
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join(timeout=5)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded P1.6d live-verification CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify P1.6 Runtime Control across Governance, policy-model-router and Credit Desk. "
            "Governance must be configured to call the barrier proxy URL."
        )
    )
    parser.add_argument("--governance-url", default=_DEFAULT_GOVERNANCE_URL)
    parser.add_argument("--router-url", default=_DEFAULT_ROUTER_URL)
    parser.add_argument("--proxy-host", default=_DEFAULT_PROXY_HOST)
    parser.add_argument("--proxy-port", type=int, default=_DEFAULT_PROXY_PORT)
    parser.add_argument("--agent-id")
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument("--user-id", default=_DEFAULT_USER_ID)
    parser.add_argument("--timeout-seconds", type=float, default=_DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--report", type=Path, default=_DEFAULT_REPORT)
    parser.add_argument("--credit-desk-repo", type=Path)
    parser.add_argument("--credit-desk-port", type=int, default=_DEFAULT_CREDIT_DESK_PORT)
    parser.add_argument("--skip-credit-desk", action="store_true")
    return parser


def _require_port_available(host: str, port: int) -> None:
    if not 1 <= port <= 65_535:
        raise VerificationError("proxy port must be in 1..65535")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError as exc:
            raise VerificationError(f"proxy address is unavailable: {host}:{port}") from exc


def main() -> int:
    """Resolve configuration, run the live scenario and print a concise summary."""
    args = build_parser().parse_args()
    try:
        if args.timeout_seconds <= 0:
            raise VerificationError("--timeout-seconds must be greater than zero")
        _require_port_available(args.proxy_host, args.proxy_port)
        agent_id = load_agent_id(args.agent_id, args.manifest)
        if not args.skip_credit_desk and args.credit_desk_repo is None:
            raise VerificationError(
                "--credit-desk-repo is required unless --skip-credit-desk is used"
            )
        config = ScenarioConfig(
            governance_url=args.governance_url.rstrip("/"),
            router_url=args.router_url.rstrip("/"),
            proxy_host=args.proxy_host,
            proxy_port=args.proxy_port,
            agent_id=agent_id,
            user_id=args.user_id,
            timeout_seconds=args.timeout_seconds,
            report_path=args.report,
            credit_desk_repo=args.credit_desk_repo,
            credit_desk_port=args.credit_desk_port,
            skip_credit_desk=args.skip_credit_desk,
        )
        report = run_scenario(config)
    except (VerificationError, httpx.HTTPError, OSError, subprocess.SubprocessError) as exc:
        print(f"[p1.6d] FAILED: {exc}", file=sys.stderr)
        return 2

    print("[p1.6d] PASSED")
    print(f"[p1.6d] report: {config.report_path}")
    steps = report["steps"]
    assert isinstance(steps, dict)
    print(
        "[p1.6d] A=allowed, B=kill_switch_engaged, "
        "B-after-restore=runtime_authorization_revoked, C=allowed"
    )
    if config.skip_credit_desk:
        print("[p1.6d] Credit Desk live probe: skipped")
    else:
        print("[p1.6d] Credit Desk: deterministic decision preserved, narrative omitted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
