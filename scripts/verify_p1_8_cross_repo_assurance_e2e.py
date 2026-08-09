"""Live P1.8d cross-repository Runtime Assurance verification harness."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

from scripts.verify_p1_7_cross_repo_telemetry_e2e import (
    VerificationError,
    _event_report,
    _list_runtime_events,
    _require_git_ancestor,
    _run_credit_desk_probe,
    _telemetry_api_key,
    _verify_audit_events,
    _wait_for_runtime_event,
    _wait_http_ready,
    audit_event_hash,
    governance_headers,
    load_agent_id,
    require_equal,
    validate_runtime_event,
)

_DEFAULT_GOVERNANCE_URL = "http://127.0.0.1:8000"
_DEFAULT_CREDIT_DESK_PORT = 8199
_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_USER_ID = "demo.requester"
_DEFAULT_MANIFEST = Path("artifacts/demo/canonical-seed-manifest.json")
_DEFAULT_REPORT = Path("artifacts/e2e/p1.8-cross-repo-assurance-live-report.json")
_DEFAULT_OTLP_ENDPOINT = "http://127.0.0.1:4318/v1/traces"

_REQUIRED_GOVERNANCE_BASELINE = "d69d827d6bfa47ea1f11743accd9c33df4c223e8"
_REQUIRED_A2A_OTEL_KIT_VERSION = "0.5.0"
_ALLOWED_PROMOTION_DISPOSITIONS = {
    "created",
    "deduplicated",
    "severity_escalated",
}
_ACTIVE_INCIDENT_STATUSES = {"open", "contained", "remediating"}
_REQUIRED_RECOMMENDATION_ACTIONS = {
    "investigate_failures",
    "prepare_containment",
    "consider_kill_switch",
}
_REQUIRED_RATIONALE_CODES = {
    "failure_rate_exceeded",
    "elevated_severity",
    "critical_kill_switch_available",
}
_FORBIDDEN_REPORT_FRAGMENTS = (
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
    "customer",
)


def _response_json(response: httpx.Response, label: str) -> dict[str, Any]:
    """Return one JSON object or fail with a bounded status-only message."""
    if response.status_code >= 400:
        raise VerificationError(f"{label} failed with HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise VerificationError(f"{label} did not return a JSON object")
    return payload


def _runtime_package_version(credit_repo: Path) -> str:
    """Return the a2a-otel-kit version used by the Credit Desk runtime."""
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--package",
            "decisao-agent",
            "python",
            "-c",
            "import importlib.metadata as m; print(m.version('a2a-otel-kit'))",
        ],
        cwd=credit_repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise VerificationError("Could not resolve Credit Desk a2a-otel-kit runtime version")
    version = completed.stdout.strip()
    require_equal(
        version,
        _REQUIRED_A2A_OTEL_KIT_VERSION,
        "Credit Desk a2a-otel-kit runtime version",
    )
    return version


def _put_assurance_policy(
    client: httpx.Client,
    *,
    governance_url: str,
    agent_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Configure a two-sample policy that breaches deterministically on one failure."""
    url = f"{governance_url}/api/v1/agents/{agent_id}/runtime-assurance-policy"
    headers = governance_headers(user_id)
    current = client.get(url, headers=headers)
    expected_version: int | None
    if current.status_code == 404:
        expected_version = None
    else:
        current_payload = _response_json(current, "Runtime Assurance policy query")
        raw_version = current_payload.get("version")
        if isinstance(raw_version, bool) or not isinstance(raw_version, int) or raw_version < 1:
            raise VerificationError("Runtime Assurance policy version is invalid")
        expected_version = raw_version

    request: dict[str, object] = {
        "enabled": True,
        "lookback_seconds": 600,
        "evaluation_sample_size": 2,
        "minimum_samples": 2,
        "max_failure_rate": 0.0,
        "max_p95_duration_ms": None,
        "max_consecutive_failures": None,
        "breach_severity": "critical",
    }
    if expected_version is not None:
        request["expected_version"] = expected_version

    policy = _response_json(
        client.put(url, headers=headers, json=request),
        "Runtime Assurance policy upsert",
    )
    require_equal(policy.get("enabled"), True, "assurance policy enabled")
    require_equal(policy.get("evaluation_sample_size"), 2, "assurance sample size")
    require_equal(policy.get("minimum_samples"), 2, "assurance minimum samples")
    require_equal(policy.get("max_failure_rate"), 0.0, "assurance max failure rate")
    require_equal(policy.get("breach_severity"), "critical", "assurance breach severity")
    return policy


def validate_assurance_evaluation(
    evaluation: dict[str, Any],
    *,
    agent_id: str,
    source_event_ids: set[str],
) -> None:
    """Verify a critical breach bound exactly to the two fresh producer events."""
    require_equal(evaluation.get("agent_id"), agent_id, "assurance agent_id")
    require_equal(evaluation.get("outcome"), "breached", "assurance outcome")
    require_equal(evaluation.get("severity"), "critical", "assurance severity")
    require_equal(evaluation.get("sample_count"), 2, "assurance sample count")
    require_equal(evaluation.get("failure_count"), 1, "assurance failure count")
    require_equal(evaluation.get("failure_rate"), 0.5, "assurance failure rate")
    require_equal(
        evaluation.get("breach_reasons"),
        ["failure_rate_exceeded"],
        "assurance breach reasons",
    )
    raw_sources = evaluation.get("source_event_ids")
    if not isinstance(raw_sources, list) or not all(isinstance(item, str) for item in raw_sources):
        raise VerificationError("assurance source_event_ids are invalid")
    if len(raw_sources) != 2 or set(raw_sources) != source_event_ids:
        raise VerificationError(
            "assurance evaluation is not bound exactly to the fresh Credit Desk events"
        )
    for field in ("id", "evidence_digest"):
        value = evaluation.get(field)
        if not isinstance(value, str) or not value:
            raise VerificationError(f"assurance {field} is missing")
    digest = evaluation["evidence_digest"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise VerificationError("assurance evidence_digest is invalid")


def validate_promotion(
    promotion: dict[str, Any],
    *,
    evaluation: dict[str, Any],
    agent_id: str,
) -> None:
    """Verify incident-promotion lineage without manufacturing a new incident."""
    require_equal(
        promotion.get("evaluation_id"),
        evaluation.get("id"),
        "promotion evaluation_id",
    )
    require_equal(promotion.get("agent_id"), agent_id, "promotion agent_id")
    disposition = promotion.get("disposition")
    if disposition not in _ALLOWED_PROMOTION_DISPOSITIONS:
        raise VerificationError(f"unsupported incident-promotion disposition: {disposition!r}")
    status = promotion.get("incident_status")
    if status not in _ACTIVE_INCIDENT_STATUSES:
        raise VerificationError(f"promoted incident is not active: {status!r}")
    require_equal(promotion.get("incident_severity"), "critical", "incident severity")
    require_equal(
        promotion.get("evidence_digest"),
        evaluation.get("evidence_digest"),
        "promotion source evidence digest",
    )
    for field in ("promotion_id", "incident_id", "breach_fingerprint"):
        value = promotion.get(field)
        if not isinstance(value, str) or not value:
            raise VerificationError(f"promotion {field} is missing")
    fingerprint = promotion["breach_fingerprint"]
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise VerificationError("promotion breach_fingerprint is invalid")


def validate_recommendation(
    recommendation: dict[str, Any],
    *,
    promotion: dict[str, Any],
    before: dict[str, object],
) -> None:
    """Verify the strongest critical advisory path remains non-actuating."""
    require_equal(
        recommendation.get("promotion_id"),
        promotion.get("promotion_id"),
        "recommendation promotion_id",
    )
    require_equal(
        recommendation.get("evaluation_id"),
        promotion.get("evaluation_id"),
        "recommendation evaluation_id",
    )
    require_equal(
        recommendation.get("incident_id"),
        promotion.get("incident_id"),
        "recommendation incident_id",
    )
    require_equal(
        recommendation.get("breach_fingerprint"),
        promotion.get("breach_fingerprint"),
        "recommendation breach fingerprint",
    )
    require_equal(recommendation.get("advisory_only"), True, "advisory_only")
    require_equal(
        recommendation.get("policy_id"),
        "runtime-assurance-response",
        "response policy id",
    )
    require_equal(
        recommendation.get("policy_version"),
        "1.0",
        "response policy version",
    )
    for response_field, state_field in (
        ("incident_status", "incident_status"),
        ("incident_severity", "incident_severity"),
        ("incident_version", "incident_version"),
        ("kill_switch_enabled", "kill_switch_enabled"),
        ("kill_switch_engaged", "kill_switch_engaged"),
    ):
        require_equal(
            recommendation.get(response_field),
            before[state_field],
            f"recommendation {response_field} snapshot",
        )

    actions = recommendation.get("actions")
    if not isinstance(actions, list) or not all(isinstance(item, str) for item in actions):
        raise VerificationError("response recommendation actions are invalid")
    if not _REQUIRED_RECOMMENDATION_ACTIONS.issubset(set(actions)):
        raise VerificationError("critical response recommendation is missing required actions")

    rationale_codes = recommendation.get("rationale_codes")
    if not isinstance(rationale_codes, list) or not all(
        isinstance(item, str) for item in rationale_codes
    ):
        raise VerificationError("response recommendation rationale_codes are invalid")
    if not _REQUIRED_RATIONALE_CODES.issubset(set(rationale_codes)):
        raise VerificationError("critical response recommendation is missing rationale evidence")

    for field in (
        "id",
        "policy_digest",
        "recommendation_digest",
        "source_evidence_digest",
    ):
        value = recommendation.get(field)
        if not isinstance(value, str) or not value:
            raise VerificationError(f"recommendation {field} is missing")
    for field in ("policy_digest", "recommendation_digest", "source_evidence_digest"):
        value = recommendation[field]
        if not isinstance(value, str) or len(value) != 64:
            raise VerificationError(f"recommendation {field} is not a SHA-256 digest")


async def _read_runtime_state(
    *,
    agent_id: str,
    incident_id: str | None = None,
) -> dict[str, object]:
    """Read content-minimized mutable state for auth and zero-actuation proof."""
    from ai_governance_api.database import SessionFactory
    from ai_governance_api.models import (
        Agent,
        AISystem,
        Incident,
        RuntimeControlTransitionEntry,
    )
    from sqlalchemy import func, select

    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(Agent, AISystem)
                .join(AISystem, AISystem.id == Agent.ai_system_id)
                .where(Agent.id == agent_id)
            )
        ).one_or_none()
        if row is None:
            raise VerificationError("Canonical Agent is not available in Governance")
        agent, ai_system = row

        transition_count = await session.scalar(
            select(func.count())
            .select_from(RuntimeControlTransitionEntry)
            .where(RuntimeControlTransitionEntry.agent_id == agent_id)
        )
        state: dict[str, object] = {
            "agent_id": agent.id,
            "ai_system_id": ai_system.id,
            "ai_system_owner_id": ai_system.owner_id,
            "agent_version": agent.version,
            "kill_switch_enabled": agent.kill_switch_enabled,
            "kill_switch_engaged": agent.kill_switch_engaged,
            "runtime_control_transition_count": int(transition_count or 0),
        }
        if incident_id is not None:
            incident = await session.get(Incident, incident_id)
            if incident is None or incident.ai_system_id != ai_system.id:
                raise VerificationError("Promoted incident is not available in the Agent AI System")
            state.update(
                {
                    "incident_id": incident.id,
                    "incident_status": incident.status.value,
                    "incident_severity": incident.severity.value,
                    "incident_version": incident.version,
                }
            )
        return state


async def _verify_audit_entity(
    *,
    entity_id: str,
    action: str,
    entity_type: str,
) -> dict[str, object]:
    """Verify one expected audit event and its canonical predecessor linkage."""
    from ai_governance_api.config import get_settings
    from ai_governance_api.database import SessionFactory
    from ai_governance_api.models import AuditEvent
    from sqlalchemy import select

    settings = get_settings()
    async with SessionFactory() as session:
        rows = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.entity_id == entity_id,
                    AuditEvent.action == action,
                    AuditEvent.entity_type == entity_type,
                )
            )
        ).all()
        if len(rows) != 1:
            raise VerificationError(f"Expected one audit row for {action} entity {entity_id}")
        row = rows[0]
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
        require_equal(row.event_hash, expected_hash, f"{action} audit hash")

        predecessor_resolved = row.previous_hash is None
        if row.previous_hash is not None:
            predecessor = await session.scalar(
                select(AuditEvent).where(AuditEvent.event_hash == row.previous_hash)
            )
            predecessor_resolved = predecessor is not None
        if not predecessor_resolved:
            raise VerificationError(f"{action} previous_hash did not resolve")

        return {
            "audit_event_id": row.id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "entity_version": row.entity_version,
            "event_hash": row.event_hash,
            "previous_hash": row.previous_hash,
            "predecessor_resolved": predecessor_resolved,
        }


async def _dispose_database_engine() -> None:
    # Dispose pooled async DB connections before the shared loop closes.
    from ai_governance_api.database import engine

    await engine.dispose()


def validate_zero_actuation(
    before: dict[str, object],
    after: dict[str, object],
) -> dict[str, bool]:
    """Prove recommendation generation did not mutate Incident, Agent, or control."""
    incident_unchanged = all(
        before.get(field) == after.get(field)
        for field in (
            "incident_id",
            "incident_status",
            "incident_severity",
            "incident_version",
        )
    )
    agent_unchanged = all(
        before.get(field) == after.get(field)
        for field in (
            "agent_id",
            "agent_version",
            "kill_switch_enabled",
            "kill_switch_engaged",
        )
    )
    runtime_control_unchanged = before.get("runtime_control_transition_count") == after.get(
        "runtime_control_transition_count"
    )
    proof = {
        "incident_unchanged": incident_unchanged,
        "agent_unchanged": agent_unchanged,
        "runtime_control_transition_count_unchanged": runtime_control_unchanged,
    }
    if not all(proof.values()):
        raise VerificationError("Runtime response recommendation caused unexpected actuation")
    return proof


def _selected(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, object]:
    """Return a stable allowlisted report projection."""
    return {key: value.get(key) for key in keys}


def _safe_assurance_report(evaluation: dict[str, Any]) -> dict[str, object]:
    return _selected(
        evaluation,
        (
            "id",
            "agent_id",
            "ai_system_id",
            "policy_version",
            "sample_count",
            "failure_count",
            "failure_rate",
            "outcome",
            "breach_reasons",
            "severity",
            "source_event_ids",
            "evidence_digest",
            "version",
        ),
    )


def _safe_promotion_report(promotion: dict[str, Any]) -> dict[str, object]:
    return _selected(
        promotion,
        (
            "promotion_id",
            "evaluation_id",
            "agent_id",
            "ai_system_id",
            "incident_id",
            "breach_fingerprint",
            "disposition",
            "evidence_digest",
            "incident_status",
            "incident_severity",
            "incident_version",
        ),
    )


def _safe_recommendation_report(
    recommendation: dict[str, Any],
) -> dict[str, object]:
    return _selected(
        recommendation,
        (
            "id",
            "promotion_id",
            "evaluation_id",
            "agent_id",
            "ai_system_id",
            "incident_id",
            "breach_fingerprint",
            "source_evidence_digest",
            "policy_id",
            "policy_version",
            "policy_digest",
            "incident_status",
            "incident_severity",
            "incident_version",
            "kill_switch_enabled",
            "kill_switch_engaged",
            "actions",
            "rationale_codes",
            "advisory_only",
            "recommendation_digest",
            "version",
        ),
    )


def assert_safe_report(report: dict[str, object], *, secret: str) -> None:
    """Fail if committed proof contains known business/security content."""
    serialized = json.dumps(report, sort_keys=True).lower()
    for fragment in _FORBIDDEN_REPORT_FRAGMENTS:
        if fragment in serialized:
            raise VerificationError(f"forbidden content appeared in P1.8d report: {fragment}")
    if secret.lower() in serialized:
        raise VerificationError("telemetry secret appeared in P1.8d report")


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_scenario(
    args: argparse.Namespace,
    *,
    runner: asyncio.Runner,
) -> dict[str, object]:
    """Run producer-to-advisory chain and persist content-minimized proof."""
    governance_root = Path(__file__).resolve().parents[1]
    governance_head = _require_git_ancestor(
        governance_root,
        _REQUIRED_GOVERNANCE_BASELINE,
        "Governance",
    )
    governance_url = args.governance_url.rstrip("/")
    agent_id = load_agent_id(args.agent_id, args.manifest)
    secret = _telemetry_api_key()
    credit_repo = args.credit_desk_repo.resolve()
    kit_version = _runtime_package_version(credit_repo)

    initial_state = runner.run(_read_runtime_state(agent_id=agent_id))
    require_equal(
        initial_state["ai_system_owner_id"],
        args.user_id,
        "live scenario AI System owner",
    )
    require_equal(
        initial_state["kill_switch_enabled"],
        True,
        "kill switch availability",
    )
    require_equal(
        initial_state["kill_switch_engaged"],
        False,
        "kill switch preflight state",
    )

    with httpx.Client(timeout=args.timeout_seconds) as client:
        _wait_http_ready(
            f"{governance_url}/health/ready",
            timeout_seconds=max(args.timeout_seconds, 10.0),
        )
        _list_runtime_events(
            client,
            governance_url=governance_url,
            agent_id=agent_id,
            user_id=args.user_id,
        )
        policy = _put_assurance_policy(
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
            api_key=secret,
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
            api_key=secret,
        )
        validate_runtime_event(
            failure,
            agent_id=agent_id,
            correlation_id=probe["failure"]["context_id"],
            request_id=probe["failure"]["task_id"],
            event_name="decisao_agent.evaluation.failed",
            event_outcome="failure",
            error_type="ValidationError",
            api_key=secret,
        )

        event_ids = {str(success["event_id"]), str(failure["event_id"])}
        evaluation = _response_json(
            client.post(
                f"{governance_url}/api/v1/agents/{agent_id}/runtime-assurance-evaluations",
                headers=governance_headers(args.user_id),
            ),
            "Runtime Assurance evaluation",
        )
        validate_assurance_evaluation(
            evaluation,
            agent_id=agent_id,
            source_event_ids=event_ids,
        )

        promotion = _response_json(
            client.post(
                f"{governance_url}/api/v1/runtime-assurance-evaluations/"
                f"{evaluation['id']}/incident-promotion",
                headers=governance_headers(args.user_id),
                json={},
            ),
            "Runtime Assurance incident promotion",
        )
        validate_promotion(
            promotion,
            evaluation=evaluation,
            agent_id=agent_id,
        )

        before = runner.run(
            _read_runtime_state(
                agent_id=agent_id,
                incident_id=str(promotion["incident_id"]),
            )
        )
        require_equal(
            before["incident_severity"],
            "critical",
            "pre-advice severity",
        )
        require_equal(
            before["kill_switch_enabled"],
            True,
            "pre-advice kill switch availability",
        )
        require_equal(
            before["kill_switch_engaged"],
            False,
            "pre-advice kill switch state",
        )

        recommendation_url = (
            f"{governance_url}/api/v1/runtime-assurance-incident-promotions/"
            f"{promotion['promotion_id']}/response-recommendations"
        )
        recommendation = _response_json(
            client.post(
                recommendation_url,
                headers=governance_headers(args.user_id),
                json={},
            ),
            "Runtime response recommendation",
        )
        validate_recommendation(
            recommendation,
            promotion=promotion,
            before=before,
        )

        replay = _response_json(
            client.post(
                recommendation_url,
                headers=governance_headers(args.user_id),
                json={},
            ),
            "Runtime response recommendation replay",
        )
        require_equal(
            replay.get("id"),
            recommendation.get("id"),
            "recommendation replay id",
        )
        require_equal(
            replay.get("recommendation_digest"),
            recommendation.get("recommendation_digest"),
            "recommendation replay digest",
        )

        fetched = _response_json(
            client.get(
                recommendation_url,
                headers=governance_headers(args.user_id),
            ),
            "Runtime response recommendation query",
        )
        require_equal(
            fetched,
            recommendation,
            "persisted recommendation query",
        )

    after = runner.run(
        _read_runtime_state(
            agent_id=agent_id,
            incident_id=str(promotion["incident_id"]),
        )
    )
    zero_actuation = validate_zero_actuation(before, after)

    telemetry_audit = runner.run(_verify_audit_events([success, failure], agent_id=agent_id))
    assurance_audit = runner.run(
        _verify_audit_entity(
            entity_id=str(evaluation["id"]),
            action="runtime_assurance.evaluated",
            entity_type="runtime_assurance_evaluation",
        )
    )
    promotion_audit = runner.run(
        _verify_audit_entity(
            entity_id=str(promotion["promotion_id"]),
            action="runtime_assurance.incident_promoted",
            entity_type="runtime_assurance_incident_promotion",
        )
    )
    recommendation_audit = runner.run(
        _verify_audit_entity(
            entity_id=str(recommendation["id"]),
            action="runtime_assurance.response_recommended",
            entity_type="runtime_assurance_response_recommendation",
        )
    )

    report: dict[str, object] = {
        "schema_version": "1.0",
        "result": "passed",
        "baselines": {
            "governance_head": governance_head,
            "required_governance_baseline": _REQUIRED_GOVERNANCE_BASELINE,
            "credit_desk_head": credit_head,
            "a2a_otel_kit_runtime_version": kit_version,
        },
        "producer": {
            "success": probe["success"],
            "failure": probe["failure"],
        },
        "telemetry": {
            "completed": _event_report(
                success,
                telemetry_audit[str(success["event_id"])],
            ),
            "failed": _event_report(
                failure,
                telemetry_audit[str(failure["event_id"])],
            ),
        },
        "assurance_policy": {
            "version": policy.get("version"),
            "evaluation_sample_size": policy.get("evaluation_sample_size"),
            "minimum_samples": policy.get("minimum_samples"),
            "max_failure_rate": policy.get("max_failure_rate"),
            "breach_severity": policy.get("breach_severity"),
        },
        "assurance_evaluation": _safe_assurance_report(evaluation),
        "incident_promotion": _safe_promotion_report(promotion),
        "response_recommendation": _safe_recommendation_report(recommendation),
        "audit": {
            "assurance_evaluation": assurance_audit,
            "incident_promotion": promotion_audit,
            "response_recommendation": recommendation_audit,
        },
        "zero_actuation": zero_actuation,
    }
    assert_safe_report(report, secret=secret)
    _write_report(args.report, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the P1.8d live verification CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify Credit Desk -> sanitized telemetry -> deterministic assurance -> "
            "governed incident promotion -> advisory-only response recommendation."
        )
    )
    parser.add_argument("--governance-url", default=_DEFAULT_GOVERNANCE_URL)
    parser.add_argument("--agent-id")
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument("--user-id", default=_DEFAULT_USER_ID)
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=_DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument("--report", type=Path, default=_DEFAULT_REPORT)
    parser.add_argument("--credit-desk-repo", type=Path, required=True)
    parser.add_argument(
        "--credit-desk-port",
        type=int,
        default=_DEFAULT_CREDIT_DESK_PORT,
    )
    parser.add_argument("--otlp-endpoint", default=_DEFAULT_OTLP_ENDPOINT)
    return parser


def main() -> int:
    """Run the proof and print a concise structural result."""
    args = build_parser().parse_args()
    try:
        if args.timeout_seconds <= 0:
            raise VerificationError("--timeout-seconds must be greater than zero")
        with asyncio.Runner() as runner:
            try:
                report = run_scenario(args, runner=runner)
            finally:
                runner.run(_dispose_database_engine())
    except (
        VerificationError,
        httpx.HTTPError,
        importlib.metadata.PackageNotFoundError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        print(f"[p1.8d] FAILED: {exc}", file=sys.stderr)
        return 2

    promotion = report["incident_promotion"]
    assert isinstance(promotion, dict)
    print("[p1.8d] PASSED")
    print(f"[p1.8d] report: {args.report}")
    print("[p1.8d] Credit Desk -> telemetry -> assurance -> incident -> advisory response verified")
    print(f"[p1.8d] incident promotion disposition: {promotion['disposition']}")
    print("[p1.8d] recommendation included consider_kill_switch; zero actuation verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
