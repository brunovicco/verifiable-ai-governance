"""Live P1.7 cross-repository sanitized runtime-telemetry verification harness."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

_DEFAULT_GOVERNANCE_URL = "http://127.0.0.1:8000"
_DEFAULT_CREDIT_DESK_PORT = 8199
_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_USER_ID = "demo.requester"
_DEFAULT_MANIFEST = Path("artifacts/demo/canonical-seed-manifest.json")
_DEFAULT_REPORT = Path("artifacts/e2e/p1.7-cross-repo-telemetry-live-report.json")
_DEFAULT_OTLP_ENDPOINT = "http://127.0.0.1:4318/v1/traces"
_TELEMETRY_KEY_ENV = "P1_7_TELEMETRY_API_KEY"
_REQUIRED_CREDIT_DESK_BASELINE = "b326971bbe7910bd94bd45c0cafbaa11a03f8610"
_HEX_32 = re.compile(r"^[0-9a-f]{32}$")
_HEX_16 = re.compile(r"^[0-9a-f]{16}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")

_FORBIDDEN_SERIALIZED_FRAGMENTS = (
    "annual_revenue",
    "bureau_score",
    "credit_opinion",
    "model_output",
    "narrative",
    "prompt",
    "completion",
    "authorization",
    "credential",
    "api_key",
)


class VerificationError(RuntimeError):
    """Raised when one required P1.7d invariant is not observed."""


def require_equal(actual: object, expected: object, label: str) -> None:
    """Raise a stable verification error when one exact invariant differs."""
    if actual != expected:
        raise VerificationError(f"{label}: expected {expected!r}, got {actual!r}")


def load_agent_id(explicit: str | None, manifest_path: Path) -> str:
    """Resolve the canonical Agent identifier from CLI or seed manifest."""
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


def _telemetry_api_key() -> str:
    """Resolve the live-test machine credential without printing or persisting it."""
    value = os.environ.get(_TELEMETRY_KEY_ENV, "")
    if not value or len(value) > 1024 or "\r" in value or "\n" in value:
        raise VerificationError(
            f"{_TELEMETRY_KEY_ENV} must contain the bounded local telemetry credential"
        )
    return value


def _git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        text=True,
        capture_output=True,
    )
    value = result.stdout.strip()
    if not value:
        raise VerificationError(f"Could not resolve git HEAD for {path}")
    return value


def _require_git_ancestor(path: Path, ancestor: str, label: str) -> str:
    """Require a merged baseline without requiring an exact future HEAD."""
    head = _git_head(path)
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, head],
        cwd=path,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise VerificationError(f"{label} HEAD does not contain required baseline {ancestor}")
    return head


def _require_clean_worktree(path: Path, label: str) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=path,
        check=True,
        text=True,
        capture_output=True,
    )
    if result.stdout.strip():
        raise VerificationError(f"{label} worktree must be clean for the live producer proof")


def _require_port_available(host: str, port: int) -> None:
    if not 1 <= port <= 65_535:
        raise VerificationError("Credit Desk port must be in 1..65535")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError as exc:
            raise VerificationError(f"Credit Desk address is unavailable: {host}:{port}") from exc


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


def _parse_probe(stdout: str) -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise VerificationError("Credit Desk probe did not return JSON") from exc
    if not isinstance(payload, dict):
        raise VerificationError("Credit Desk probe result is invalid")

    result: dict[str, dict[str, str]] = {}
    for name in ("success", "failure"):
        item = payload.get(name)
        if not isinstance(item, dict):
            raise VerificationError(f"Credit Desk probe is missing {name}")
        context_id = item.get("context_id")
        task_id = item.get("task_id")
        state = item.get("state")
        if (
            not isinstance(context_id, str)
            or not context_id
            or not isinstance(task_id, str)
            or not task_id
            or not isinstance(state, str)
            or not state
        ):
            raise VerificationError(f"Credit Desk probe {name} identifiers are invalid")
        result[name] = {
            "context_id": context_id,
            "task_id": task_id,
            "state": state,
        }
    require_equal(result["success"]["state"], "completed", "success task state")
    require_equal(result["failure"]["state"], "failed", "failure task state")
    return result


def _run_credit_desk_probe(
    *,
    repo: Path,
    governance_url: str,
    agent_id: str,
    user_id: str,
    api_key: str,
    port: int,
    timeout_seconds: float,
    otlp_endpoint: str,
) -> tuple[dict[str, dict[str, str]], str]:
    """Run the real P1.7c producer with telemetry enabled and return structural task IDs."""
    repo = repo.resolve()
    if not (repo / "pyproject.toml").is_file():
        raise VerificationError(f"Credit Desk repository is invalid: {repo}")
    credit_head = _require_git_ancestor(
        repo,
        _REQUIRED_CREDIT_DESK_BASELINE,
        "Credit Desk",
    )
    _require_clean_worktree(repo, "Credit Desk")

    host = "127.0.0.1"
    base_url = f"http://{host}:{port}"
    env = {
        **os.environ,
        "DECISAO_AGENT_A2A_HOST": host,
        "DECISAO_AGENT_A2A_PORT": str(port),
        "DECISAO_AGENT_GOVERNANCE_BASE_URL": governance_url,
        "DECISAO_AGENT_GOVERNANCE_AGENT_ID": agent_id,
        "DECISAO_AGENT_GOVERNANCE_DEV_USER_ID": user_id,
        "DECISAO_AGENT_GOVERNANCE_TELEMETRY_ENABLED": "true",
        "DECISAO_AGENT_GOVERNANCE_TELEMETRY_API_KEY": api_key,
        "DECISAO_AGENT_ENV": "p1.7-live-e2e",
        "A2A_OTEL_ENABLED": "true",
        "A2A_OTEL_OTLP_ENDPOINT": otlp_endpoint,
        "A2A_OTEL_OTLP_TIMEOUT_SECONDS": "1",
        "A2A_OTEL_LOG_FORMAT": "json",
    }
    process = subprocess.Popen(
        [
            "uv",
            "run",
            "--package",
            "decisao-agent",
            "python",
            "-m",
            "decisao_agent.entrypoints.a2a_server",
        ],
        cwd=repo,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_http_ready(
            f"{base_url}/.well-known/agent-card.json",
            timeout_seconds=max(timeout_seconds, 20.0),
        )
        probe = Path(__file__).with_name("p1_7_credit_desk_probe.py").resolve()
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
            timeout=max(timeout_seconds, 45.0),
            check=False,
        )
        if completed.returncode != 0:
            raise VerificationError(
                "Credit Desk live probe failed: "
                + (completed.stderr.strip() or "structural probe error")
            )
        return _parse_probe(completed.stdout.strip()), credit_head
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def governance_headers(user_id: str) -> dict[str, str]:
    """Return the local/demo principal used by the canonical live scenario."""
    return {"X-User-Id": user_id}


def _list_runtime_events(
    client: httpx.Client,
    *,
    governance_url: str,
    agent_id: str,
    user_id: str,
) -> list[dict[str, Any]]:
    response = client.get(
        f"{governance_url.rstrip('/')}/api/v1/agents/{agent_id}/runtime-telemetry",
        headers=governance_headers(user_id),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise VerificationError("Runtime telemetry query did not return a list of objects")
    return payload


def _wait_for_runtime_event(
    client: httpx.Client,
    *,
    governance_url: str,
    agent_id: str,
    user_id: str,
    correlation_id: str,
    request_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        events = _list_runtime_events(
            client,
            governance_url=governance_url,
            agent_id=agent_id,
            user_id=user_id,
        )
        matches = [
            event
            for event in events
            if event.get("correlation_id") == correlation_id
            and event.get("request_id") == request_id
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise VerificationError("Runtime telemetry correlation matched more than one event")
        time.sleep(0.2)
    raise VerificationError(
        f"Runtime telemetry event did not appear for correlation={correlation_id!r}"
    )


def validate_runtime_event(
    record: dict[str, Any],
    *,
    agent_id: str,
    correlation_id: str,
    request_id: str,
    event_name: str,
    event_outcome: str,
    error_type: str | None,
    api_key: str,
) -> None:
    """Verify normalized producer->Governance evidence without trusting arbitrary payloads."""
    require_equal(record.get("agent_id"), agent_id, "telemetry agent_id")
    require_equal(record.get("source_schema_version"), 1, "source schema version")
    require_equal(record.get("event_name"), event_name, "event name")
    require_equal(record.get("event_outcome"), event_outcome, "event outcome")
    require_equal(record.get("service"), "decisao-agent", "service")
    require_equal(record.get("environment"), "p1.7-live-e2e", "environment")
    require_equal(record.get("version"), "0.1.0", "service version")
    require_equal(record.get("component"), "a2a_executor", "component")
    require_equal(record.get("operation"), "credit_evaluation", "operation")
    require_equal(record.get("correlation_id"), correlation_id, "correlation_id")
    require_equal(record.get("request_id"), request_id, "request_id")
    require_equal(record.get("error_type"), error_type, "error_type")
    require_equal(record.get("record_version"), 1, "record version")

    event_id = record.get("event_id")
    if not isinstance(event_id, str):
        raise VerificationError("runtime telemetry event_id is missing")
    try:
        parsed = UUID(event_id)
    except ValueError as exc:
        raise VerificationError("runtime telemetry event_id is not a UUID") from exc
    if parsed.int == 0 or str(parsed) != event_id:
        raise VerificationError("runtime telemetry event_id is not canonical")

    trace_id = record.get("trace_id")
    span_id = record.get("span_id")
    digest = record.get("payload_digest")
    if not isinstance(trace_id, str) or _HEX_32.fullmatch(trace_id) is None:
        raise VerificationError("runtime telemetry trace_id is not an active W3C trace id")
    if not isinstance(span_id, str) or _HEX_16.fullmatch(span_id) is None:
        raise VerificationError("runtime telemetry span_id is not an active W3C span id")
    if not isinstance(digest, str) or _HEX_64.fullmatch(digest) is None:
        raise VerificationError("runtime telemetry payload_digest is invalid")

    duration = record.get("duration_ms")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
        raise VerificationError("runtime telemetry duration_ms is invalid")

    serialized = json.dumps(record, sort_keys=True).lower()
    for fragment in _FORBIDDEN_SERIALIZED_FRAGMENTS:
        if fragment in serialized:
            raise VerificationError(f"forbidden runtime content appeared in evidence: {fragment}")
    if api_key.lower() in serialized:
        raise VerificationError("runtime telemetry credential appeared in persisted evidence")


def audit_event_hash(
    *,
    salt: str,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    entity_version: int,
    payload: dict[str, Any],
    previous_hash: str | None,
) -> str:
    """Recompute the canonical hash used by the Governance append-only audit chain."""
    canonical = json.dumps(
        {
            "actor_id": actor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_version": entity_version,
            "payload": payload,
            "previous_hash": previous_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(f"{salt}:{canonical}".encode()).hexdigest()


async def _verify_audit_events(
    records: list[dict[str, Any]],
    *,
    agent_id: str,
) -> dict[str, dict[str, object]]:
    """Verify minimized audit rows and their cryptographic predecessor links."""
    from ai_governance_api.config import get_settings
    from ai_governance_api.database import SessionFactory
    from ai_governance_api.models import AuditEvent
    from sqlalchemy import select

    result: dict[str, dict[str, object]] = {}
    settings = get_settings()
    async with SessionFactory() as session:
        for record in records:
            event_id = str(record["event_id"])
            rows = (
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.entity_id == event_id,
                        AuditEvent.action == "runtime_telemetry.ingested",
                        AuditEvent.entity_type == "runtime_telemetry_event",
                    )
                )
            ).all()
            if len(rows) != 1:
                raise VerificationError(
                    f"Expected exactly one runtime telemetry audit event for {event_id}"
                )
            row = rows[0]
            expected_payload = {
                "agent_id": agent_id,
                "ai_system_id": record["ai_system_id"],
                "event_name": record["event_name"],
                "event_outcome": record["event_outcome"],
                "service": record["service"],
                "payload_digest": record["payload_digest"],
            }
            require_equal(
                row.actor_id,
                f"runtime-telemetry:{agent_id}",
                "audit actor_id",
            )
            require_equal(row.entity_version, record["record_version"], "audit entity version")
            require_equal(row.payload, expected_payload, "minimized audit payload")
            expected_hash = audit_event_hash(
                salt=settings.audit_hash_salt,
                actor_id=row.actor_id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                entity_version=row.entity_version,
                payload=row.payload,
                previous_hash=row.previous_hash,
            )
            require_equal(row.event_hash, expected_hash, "audit event hash")

            predecessor_resolved = row.previous_hash is None
            if row.previous_hash is not None:
                predecessor = await session.scalar(
                    select(AuditEvent).where(AuditEvent.event_hash == row.previous_hash)
                )
                predecessor_resolved = predecessor is not None
                if not predecessor_resolved:
                    raise VerificationError("audit previous_hash does not resolve to an audit row")

            result[event_id] = {
                "audit_event_id": row.id,
                "event_hash": row.event_hash,
                "previous_hash": row.previous_hash,
                "predecessor_resolved": predecessor_resolved,
            }
    return result


def _event_report(
    record: dict[str, Any],
    audit: dict[str, object],
) -> dict[str, object]:
    """Return the intentionally content-free evidence report representation."""
    keys = (
        "event_id",
        "event_name",
        "event_outcome",
        "service",
        "environment",
        "version",
        "trace_id",
        "span_id",
        "correlation_id",
        "request_id",
        "duration_ms",
        "error_type",
        "payload_digest",
        "record_version",
    )
    return {
        **{key: record.get(key) for key in keys},
        "audit": audit,
    }


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_scenario(args: argparse.Namespace) -> dict[str, object]:
    """Run real Credit Desk success/failure events through Governance and verify audit evidence."""
    governance_url = args.governance_url.rstrip("/")
    agent_id = load_agent_id(args.agent_id, args.manifest)
    api_key = _telemetry_api_key()
    credit_repo = args.credit_desk_repo.resolve()
    _require_port_available("127.0.0.1", args.credit_desk_port)

    with httpx.Client(timeout=args.timeout_seconds) as client:
        _wait_http_ready(
            f"{governance_url}/health/ready",
            timeout_seconds=max(args.timeout_seconds, 10.0),
        )
        # This owner/admin query also proves the P1.7a read boundary is reachable
        # before the producer starts.
        _list_runtime_events(
            client,
            governance_url=governance_url,
            agent_id=agent_id,
            user_id=args.user_id,
        )

        probe, credit_head = _run_credit_desk_probe(
            repo=credit_repo,
            governance_url=governance_url,
            agent_id=agent_id,
            user_id=args.user_id,
            api_key=api_key,
            port=args.credit_desk_port,
            timeout_seconds=args.timeout_seconds,
            otlp_endpoint=args.otlp_endpoint,
        )

        success = _wait_for_runtime_event(
            client,
            governance_url=governance_url,
            agent_id=agent_id,
            user_id=args.user_id,
            correlation_id=probe["success"]["context_id"],
            request_id=probe["success"]["task_id"],
            timeout_seconds=args.timeout_seconds,
        )
        failure = _wait_for_runtime_event(
            client,
            governance_url=governance_url,
            agent_id=agent_id,
            user_id=args.user_id,
            correlation_id=probe["failure"]["context_id"],
            request_id=probe["failure"]["task_id"],
            timeout_seconds=args.timeout_seconds,
        )

    validate_runtime_event(
        success,
        agent_id=agent_id,
        correlation_id=probe["success"]["context_id"],
        request_id=probe["success"]["task_id"],
        event_name="decisao_agent.evaluation.completed",
        event_outcome="success",
        error_type=None,
        api_key=api_key,
    )
    validate_runtime_event(
        failure,
        agent_id=agent_id,
        correlation_id=probe["failure"]["context_id"],
        request_id=probe["failure"]["task_id"],
        event_name="decisao_agent.evaluation.failed",
        event_outcome="failure",
        error_type="ValidationError",
        api_key=api_key,
    )

    audit = asyncio.run(_verify_audit_events([success, failure], agent_id=agent_id))
    governance_head = _git_head(Path(__file__).resolve().parents[1])
    report: dict[str, object] = {
        "schema_version": "1.0",
        "result": "passed",
        "agent_id": agent_id,
        "baselines": {
            "governance_head": governance_head,
            "credit_desk_head": credit_head,
            "required_credit_desk_baseline": _REQUIRED_CREDIT_DESK_BASELINE,
            "a2a_otel_kit": "0.5.0",
        },
        "events": {
            "completed": _event_report(success, audit[str(success["event_id"])]),
            "failed": _event_report(failure, audit[str(failure["event_id"])]),
        },
    }
    serialized_report = json.dumps(report, sort_keys=True).lower()
    if api_key.lower() in serialized_report:
        raise VerificationError("telemetry credential leaked into the live evidence report")
    _write_report(args.report, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded P1.7d live-verification CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify sanitized runtime telemetry across Credit Desk, a2a-otel-kit and Governance. "
            "Governance must have P1.7a ingestion enabled for the same Agent/key."
        )
    )
    parser.add_argument("--governance-url", default=_DEFAULT_GOVERNANCE_URL)
    parser.add_argument("--agent-id")
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument("--user-id", default=_DEFAULT_USER_ID)
    parser.add_argument("--timeout-seconds", type=float, default=_DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--report", type=Path, default=_DEFAULT_REPORT)
    parser.add_argument("--credit-desk-repo", type=Path, required=True)
    parser.add_argument("--credit-desk-port", type=int, default=_DEFAULT_CREDIT_DESK_PORT)
    parser.add_argument("--otlp-endpoint", default=_DEFAULT_OTLP_ENDPOINT)
    return parser


def main() -> int:
    """Resolve configuration, run the live proof and print a concise content-free result."""
    args = build_parser().parse_args()
    try:
        if args.timeout_seconds <= 0:
            raise VerificationError("--timeout-seconds must be greater than zero")
        report = run_scenario(args)
    except (
        VerificationError,
        httpx.HTTPError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"[p1.7d] FAILED: {exc}", file=sys.stderr)
        return 2

    print("[p1.7d] PASSED")
    print(f"[p1.7d] report: {args.report}")
    events = report["events"]
    assert isinstance(events, dict)
    print("[p1.7d] completed+failed telemetry persisted with W3C trace/span correlation")
    print("[p1.7d] audit payloads minimized; event hashes and predecessor links verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
