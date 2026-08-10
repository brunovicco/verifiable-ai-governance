"""Live P1.9e proof for governed containment, enforcement, and restoration."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
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
    governance_headers,
    load_agent_id,
    require_equal,
    validate_runtime_event,
)
from scripts.verify_p1_8_cross_repo_assurance_e2e import (
    _dispose_database_engine,
    _put_assurance_policy,
    _read_runtime_state,
    _response_json,
    _runtime_package_version,
    _safe_assurance_report,
    _safe_promotion_report,
    _safe_recommendation_report,
    _verify_audit_entity,
    assert_safe_report,
    validate_assurance_evaluation,
    validate_promotion,
    validate_recommendation,
    validate_zero_actuation,
)

_DEFAULT_GOVERNANCE_URL = "http://127.0.0.1:8000"
_DEFAULT_ROUTER_URL = "http://127.0.0.1:8082"
_DEFAULT_CREDIT_DESK_PORT = 8199
_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_USER_ID = "demo.requester"
_DEFAULT_SECURITY_USER_ID = "demo.security"
_DEFAULT_MANIFEST = Path("artifacts/demo/canonical-seed-manifest.json")
_DEFAULT_REPORT = Path("artifacts/e2e/p1.9-governed-actuation-live-report.json")
_DEFAULT_OTLP_ENDPOINT = "http://127.0.0.1:4318/v1/traces"
_REQUIRED_GOVERNANCE_BASELINE = "27212f0e04a138cfbb51601c1edf88e9964e74b1"


def security_headers(user_id: str) -> dict[str, str]:
    """Return a distinct local Security principal for approval-only calls."""
    return {"X-User-Id": user_id, "X-User-Areas": "security"}


def owner_security_headers(user_id: str) -> dict[str, str]:
    """Return owner identity plus Security to prove self-approval still fails."""
    return {"X-User-Id": user_id, "X-User-Areas": "security"}


def routing_payload(task_id: str) -> dict[str, object]:
    """Build one deterministic Router command already proven by the P1.6 harness."""
    return {
        "workflow_id": "p1-9-governed-actuation-live-e2e",
        "task_id": task_id,
        "workload": "opinion_drafting",
        "context_tokens_estimated": 3000,
        "max_output_tokens_estimated": 900,
        "structured_output_required": False,
        "max_latency_ms": 30_000,
        "max_cost_usd": "0.30",
    }


def _routing_decision(
    client: httpx.Client,
    *,
    governance_url: str,
    agent_id: str,
    user_id: str,
    task_id: str,
) -> tuple[int, dict[str, Any]]:
    response = client.post(
        f"{governance_url}/api/v1/agents/{agent_id}/routing-decisions",
        headers=governance_headers(user_id),
        json=routing_payload(task_id),
    )
    payload = response.json()
    if not isinstance(payload, dict):
        raise VerificationError("Model-routing endpoint did not return an object")
    return response.status_code, payload


def validate_allowed_routing(status_code: int, payload: dict[str, Any], label: str) -> None:
    """Require a live Router-backed ALLOWED result."""
    require_equal(status_code, 200, f"{label} HTTP status")
    require_equal(payload.get("outcome"), "allowed", f"{label} outcome")
    require_equal(
        payload.get("decision_source"),
        "policy_model_router",
        f"{label} decision source",
    )
    selected = payload.get("selected_model_group")
    if not isinstance(selected, str) or not selected:
        raise VerificationError(f"{label} is missing selected_model_group")


def validate_kill_switch_block(status_code: int, payload: dict[str, Any]) -> None:
    """Require runtime-control enforcement to block routing before inference."""
    require_equal(status_code, 422, "active kill-switch routing HTTP status")
    require_equal(payload.get("outcome"), "blocked", "active kill-switch routing outcome")
    require_equal(
        payload.get("decision_source"),
        "governance_registry",
        "active kill-switch decision source",
    )
    require_equal(
        payload.get("reason_code"),
        "kill_switch_engaged",
        "active kill-switch reason code",
    )
    require_equal(
        payload.get("selected_model_group"),
        None,
        "active kill-switch selected model",
    )


def _sha256_field(payload: dict[str, Any], field: str, label: str) -> str:
    value = payload.get(field)
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise VerificationError(f"{label} {field} is not a canonical SHA-256 digest")
    return value


def validate_actuation_request(
    request: dict[str, Any],
    *,
    recommendation: dict[str, Any],
    owner_id: str,
) -> None:
    """Verify P1.9a immutable engage intent and source lineage."""
    require_equal(request.get("recommendation_id"), recommendation.get("id"), "request source")
    require_equal(
        request.get("recommendation_digest"),
        recommendation.get("recommendation_digest"),
        "request recommendation digest",
    )
    require_equal(
        request.get("promotion_id"),
        recommendation.get("promotion_id"),
        "request promotion",
    )
    require_equal(
        request.get("evaluation_id"),
        recommendation.get("evaluation_id"),
        "request evaluation",
    )
    require_equal(request.get("incident_id"), recommendation.get("incident_id"), "request incident")
    require_equal(request.get("agent_id"), recommendation.get("agent_id"), "request agent")
    require_equal(request.get("ai_system_id"), recommendation.get("ai_system_id"), "request system")
    require_equal(request.get("action"), "engage_kill_switch", "request action")
    require_equal(request.get("state"), "pending", "request state")
    require_equal(request.get("requested_by"), owner_id, "request requester")
    _sha256_field(request, "request_digest", "actuation request")


def validate_actuation_decision(
    decision: dict[str, Any],
    *,
    request: dict[str, Any],
    approver_id: str,
) -> None:
    """Verify P1.9b independent Security approval binding."""
    require_equal(decision.get("request_id"), request.get("id"), "decision request")
    require_equal(
        decision.get("request_digest"),
        request.get("request_digest"),
        "decision request digest",
    )
    require_equal(decision.get("action"), "engage_kill_switch", "decision action")
    require_equal(decision.get("decision"), "approved", "decision outcome")
    require_equal(decision.get("approval_area"), "security", "decision approval area")
    require_equal(decision.get("decided_by"), approver_id, "decision approver")
    _sha256_field(decision, "decision_digest", "actuation decision")


def validate_actuation_execution(
    execution: dict[str, Any],
    *,
    decision: dict[str, Any],
    request: dict[str, Any],
    owner_id: str,
) -> None:
    """Verify P1.9c applied containment receipt and digest chain."""
    require_equal(execution.get("decision_id"), decision.get("id"), "execution decision")
    require_equal(
        execution.get("decision_digest"),
        decision.get("decision_digest"),
        "execution decision digest",
    )
    require_equal(execution.get("request_id"), request.get("id"), "execution request")
    require_equal(
        execution.get("request_digest"),
        request.get("request_digest"),
        "execution request digest",
    )
    require_equal(execution.get("action"), "engage_kill_switch", "execution action")
    require_equal(execution.get("previous_state"), "inactive", "execution previous state")
    require_equal(execution.get("target_state"), "active", "execution target state")
    require_equal(execution.get("executed_by"), owner_id, "execution operator")
    _sha256_field(execution, "execution_digest", "actuation execution")


def validate_restore_request(
    request: dict[str, Any],
    *,
    source_execution: dict[str, Any],
    owner_id: str,
) -> None:
    """Verify P1.9d restore intent is new evidence over remediation."""
    require_equal(
        request.get("source_execution_id"),
        source_execution.get("id"),
        "restore source execution",
    )
    require_equal(
        request.get("source_execution_digest"),
        source_execution.get("execution_digest"),
        "restore source execution digest",
    )
    require_equal(request.get("action"), "restore_kill_switch", "restore request action")
    require_equal(request.get("state"), "pending", "restore request state")
    require_equal(request.get("incident_status"), "remediating", "restore incident state")
    require_equal(request.get("requested_by"), owner_id, "restore requester")
    _sha256_field(request, "remediation_digest", "restore request")
    _sha256_field(request, "request_digest", "restore request")


def validate_restore_decision(
    decision: dict[str, Any],
    *,
    request: dict[str, Any],
    source_execution: dict[str, Any],
    approver_id: str,
    engage_decision: dict[str, Any],
) -> None:
    """Verify independent restore approval cannot reuse engage authorization."""
    require_equal(decision.get("request_id"), request.get("id"), "restore decision request")
    require_equal(
        decision.get("request_digest"),
        request.get("request_digest"),
        "restore decision request digest",
    )
    require_equal(
        decision.get("source_execution_id"),
        source_execution.get("id"),
        "restore decision source",
    )
    require_equal(decision.get("action"), "restore_kill_switch", "restore decision action")
    require_equal(decision.get("decision"), "approved", "restore decision outcome")
    require_equal(decision.get("approval_area"), "security", "restore approval area")
    require_equal(decision.get("decided_by"), approver_id, "restore approver")
    digest = _sha256_field(decision, "decision_digest", "restore decision")
    if digest == engage_decision.get("decision_digest"):
        raise VerificationError("Restore decision reused engage decision digest")


def validate_restore_execution(
    execution: dict[str, Any],
    *,
    decision: dict[str, Any],
    request: dict[str, Any],
    source_execution: dict[str, Any],
    owner_id: str,
) -> None:
    """Verify P1.9d applied restoration receipt and independent chain."""
    require_equal(execution.get("decision_id"), decision.get("id"), "restore execution decision")
    require_equal(
        execution.get("decision_digest"),
        decision.get("decision_digest"),
        "restore execution decision digest",
    )
    require_equal(execution.get("request_id"), request.get("id"), "restore execution request")
    require_equal(
        execution.get("source_execution_id"),
        source_execution.get("id"),
        "restore execution source",
    )
    require_equal(execution.get("action"), "restore_kill_switch", "restore execution action")
    require_equal(execution.get("previous_state"), "active", "restore previous state")
    require_equal(execution.get("target_state"), "inactive", "restore target state")
    require_equal(execution.get("executed_by"), owner_id, "restore operator")
    _sha256_field(execution, "execution_digest", "restore execution")


def _post_json(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, object],
    label: str,
) -> dict[str, Any]:
    return _response_json(client.post(url, headers=headers, json=body), label)


def _expect_self_approval_forbidden(
    client: httpx.Client,
    url: str,
    *,
    owner_id: str,
    reason: str,
) -> None:
    response = client.post(
        url,
        headers=owner_security_headers(owner_id),
        json={"decision": "approved", "reason": reason},
    )
    require_equal(response.status_code, 403, "self-approval status")


def _safe_selected(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, object]:
    return {key: value.get(key) for key in keys}


def _safe_request(value: dict[str, Any]) -> dict[str, object]:
    return _safe_selected(
        value,
        (
            "id",
            "recommendation_id",
            "recommendation_digest",
            "promotion_id",
            "evaluation_id",
            "incident_id",
            "agent_id",
            "ai_system_id",
            "action",
            "state",
            "requested_by",
            "request_digest",
            "version",
        ),
    )


def _safe_decision(value: dict[str, Any]) -> dict[str, object]:
    return _safe_selected(
        value,
        (
            "id",
            "request_id",
            "request_digest",
            "action",
            "decision",
            "approval_area",
            "decided_by",
            "decision_digest",
            "version",
        ),
    )


def _safe_execution(value: dict[str, Any]) -> dict[str, object]:
    return _safe_selected(
        value,
        (
            "id",
            "decision_id",
            "decision_digest",
            "request_id",
            "request_digest",
            "action",
            "agent_id",
            "ai_system_id",
            "incident_id",
            "runtime_transition_id",
            "control_epoch",
            "previous_state",
            "target_state",
            "revoked_through_agent_version",
            "resulting_agent_version",
            "executed_by",
            "execution_digest",
            "version",
        ),
    )


def _safe_restore_request(value: dict[str, Any]) -> dict[str, object]:
    return _safe_selected(
        value,
        (
            "id",
            "source_execution_id",
            "source_execution_digest",
            "agent_id",
            "ai_system_id",
            "incident_id",
            "action",
            "state",
            "remediation_digest",
            "incident_status",
            "incident_version",
            "requested_by",
            "request_digest",
            "version",
        ),
    )


def _safe_restore_decision(value: dict[str, Any]) -> dict[str, object]:
    return _safe_selected(
        value,
        (
            "id",
            "request_id",
            "request_digest",
            "source_execution_id",
            "source_execution_digest",
            "action",
            "decision",
            "approval_area",
            "decided_by",
            "decision_digest",
            "version",
        ),
    )


def _safe_restore_execution(value: dict[str, Any]) -> dict[str, object]:
    return _safe_selected(
        value,
        (
            "id",
            "decision_id",
            "decision_digest",
            "request_id",
            "request_digest",
            "source_execution_id",
            "source_execution_digest",
            "action",
            "agent_id",
            "ai_system_id",
            "incident_id",
            "runtime_transition_id",
            "control_epoch",
            "previous_state",
            "target_state",
            "revoked_through_agent_version",
            "resulting_agent_version",
            "executed_by",
            "execution_digest",
            "version",
        ),
    )


def _safe_routing(value: dict[str, Any]) -> dict[str, object]:
    return _safe_selected(
        value,
        (
            "id",
            "agent_id",
            "outcome",
            "decision_source",
            "reason_code",
            "selected_model_group",
            "policy_id",
            "policy_version",
            "policy_digest",
            "version",
        ),
    )


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_scenario(args: argparse.Namespace, *, runner: asyncio.Runner) -> dict[str, object]:
    """Run the complete P1.8-to-P1.9 governed containment and recovery proof."""
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
    require_equal(initial_state["ai_system_owner_id"], args.user_id, "AI System owner")
    require_equal(initial_state["kill_switch_enabled"], True, "kill switch availability")
    require_equal(initial_state["kill_switch_engaged"], False, "preflight kill switch")
    initial_count_value = initial_state["runtime_control_transition_count"]
    if isinstance(initial_count_value, bool) or not isinstance(initial_count_value, int):
        raise VerificationError("Initial Runtime Control transition count is invalid")
    initial_count = initial_count_value

    with httpx.Client(timeout=args.timeout_seconds) as client:
        _wait_http_ready(
            f"{governance_url}/health/ready",
            timeout_seconds=max(args.timeout_seconds, 10.0),
        )
        _wait_http_ready(
            f"{args.router_url.rstrip('/')}/readyz",
            timeout_seconds=max(args.timeout_seconds, 10.0),
        )
        pre_status, pre_routing = _routing_decision(
            client,
            governance_url=governance_url,
            agent_id=agent_id,
            user_id=args.user_id,
            task_id="p1-9-preflight",
        )
        validate_allowed_routing(pre_status, pre_routing, "preflight routing")

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
        promotion = _post_json(
            client,
            f"{governance_url}/api/v1/runtime-assurance-evaluations/"
            f"{evaluation['id']}/incident-promotion",
            headers=governance_headers(args.user_id),
            body={},
            label="Runtime Assurance incident promotion",
        )
        validate_promotion(promotion, evaluation=evaluation, agent_id=agent_id)
        incident_id = str(promotion["incident_id"])
        before_recommendation = runner.run(
            _read_runtime_state(agent_id=agent_id, incident_id=incident_id)
        )
        recommendation = _post_json(
            client,
            f"{governance_url}/api/v1/runtime-assurance-incident-promotions/"
            f"{promotion['promotion_id']}/response-recommendations",
            headers=governance_headers(args.user_id),
            body={},
            label="Runtime response recommendation",
        )
        validate_recommendation(
            recommendation,
            promotion=promotion,
            before=before_recommendation,
        )
        after_recommendation = runner.run(
            _read_runtime_state(agent_id=agent_id, incident_id=incident_id)
        )
        zero_actuation = validate_zero_actuation(
            before_recommendation,
            after_recommendation,
        )

        request_url = (
            f"{governance_url}/api/v1/runtime-assurance-response-recommendations/"
            f"{recommendation['id']}/actuation-request"
        )
        actuation_request = _post_json(
            client,
            request_url,
            headers=governance_headers(args.user_id),
            body={},
            label="Governed actuation request",
        )
        validate_actuation_request(
            actuation_request,
            recommendation=recommendation,
            owner_id=args.user_id,
        )
        request_replay = _post_json(
            client,
            request_url,
            headers=governance_headers(args.user_id),
            body={},
            label="Governed actuation request replay",
        )
        require_equal(request_replay.get("id"), actuation_request.get("id"), "request replay")

        decision_url = (
            f"{governance_url}/api/v1/runtime-assurance-actuation-requests/"
            f"{actuation_request['id']}/decision"
        )
        _expect_self_approval_forbidden(
            client,
            decision_url,
            owner_id=args.user_id,
            reason="P1.9e self-approval must fail.",
        )
        engage_reason = "P1.9e independent Security approval for controlled containment."
        actuation_decision = _post_json(
            client,
            decision_url,
            headers=security_headers(args.security_user_id),
            body={"decision": "approved", "reason": engage_reason},
            label="Governed actuation approval",
        )
        validate_actuation_decision(
            actuation_decision,
            request=actuation_request,
            approver_id=args.security_user_id,
        )
        decision_replay = _post_json(
            client,
            decision_url,
            headers=security_headers(args.security_user_id),
            body={"decision": "approved", "reason": engage_reason},
            label="Governed actuation approval replay",
        )
        require_equal(
            decision_replay.get("id"),
            actuation_decision.get("id"),
            "engage decision replay",
        )

        execution_url = (
            f"{governance_url}/api/v1/runtime-assurance-actuation-decisions/"
            f"{actuation_decision['id']}/execution"
        )
        actuation_execution = _post_json(
            client,
            execution_url,
            headers=governance_headers(args.user_id),
            body={},
            label="Governed actuation execution",
        )
        validate_actuation_execution(
            actuation_execution,
            decision=actuation_decision,
            request=actuation_request,
            owner_id=args.user_id,
        )
        state_active = runner.run(_read_runtime_state(agent_id=agent_id, incident_id=incident_id))
        require_equal(state_active["kill_switch_engaged"], True, "contained kill switch")
        require_equal(
            state_active["runtime_control_transition_count"],
            initial_count + 1,
            "engage transition count",
        )
        execution_replay = _post_json(
            client,
            execution_url,
            headers=governance_headers(args.user_id),
            body={},
            label="Governed actuation execution replay",
        )
        require_equal(
            execution_replay.get("id"),
            actuation_execution.get("id"),
            "engage execution replay",
        )
        replay_active = runner.run(_read_runtime_state(agent_id=agent_id, incident_id=incident_id))
        require_equal(
            replay_active["runtime_control_transition_count"],
            initial_count + 1,
            "engage replay transition count",
        )

        blocked_status, blocked_routing = _routing_decision(
            client,
            governance_url=governance_url,
            agent_id=agent_id,
            user_id=args.user_id,
            task_id="p1-9-contained",
        )
        validate_kill_switch_block(blocked_status, blocked_routing)

        incident = _response_json(
            client.get(
                f"{governance_url}/api/v1/incidents/{incident_id}",
                headers=governance_headers(args.user_id),
            ),
            "Incident query before remediation",
        )
        incident_version = incident.get("version")
        if isinstance(incident_version, bool) or not isinstance(incident_version, int):
            raise VerificationError("Incident version is invalid before remediation")
        remediation_due_at = datetime.now(UTC) + timedelta(days=1)
        remediated = _post_json(
            client,
            f"{governance_url}/api/v1/incidents/{incident_id}/remediation-plan",
            headers=governance_headers(args.user_id),
            body={
                "remediation_owner_id": args.user_id,
                "remediation_description": (
                    "P1.9e controlled recovery evidence after containment verification."
                ),
                "remediation_due_at": remediation_due_at.isoformat(),
                "expected_version": incident_version,
            },
            label="Incident remediation plan",
        )
        require_equal(remediated.get("status"), "remediating", "remediation status")

        restore_request_url = (
            f"{governance_url}/api/v1/runtime-assurance-actuation-executions/"
            f"{actuation_execution['id']}/restore-request"
        )
        restore_request = _post_json(
            client,
            restore_request_url,
            headers=governance_headers(args.user_id),
            body={},
            label="Governed restore request",
        )
        validate_restore_request(
            restore_request,
            source_execution=actuation_execution,
            owner_id=args.user_id,
        )
        restore_request_replay = _post_json(
            client,
            restore_request_url,
            headers=governance_headers(args.user_id),
            body={},
            label="Governed restore request replay",
        )
        require_equal(
            restore_request_replay.get("id"),
            restore_request.get("id"),
            "restore request replay",
        )

        restore_decision_url = (
            f"{governance_url}/api/v1/runtime-assurance-restore-requests/"
            f"{restore_request['id']}/decision"
        )
        _expect_self_approval_forbidden(
            client,
            restore_decision_url,
            owner_id=args.user_id,
            reason="P1.9e restore self-approval must fail.",
        )
        restore_reason = "P1.9e remediation reviewed; controlled restoration approved."
        restore_decision = _post_json(
            client,
            restore_decision_url,
            headers=security_headers(args.security_user_id),
            body={"decision": "approved", "reason": restore_reason},
            label="Governed restore approval",
        )
        validate_restore_decision(
            restore_decision,
            request=restore_request,
            source_execution=actuation_execution,
            approver_id=args.security_user_id,
            engage_decision=actuation_decision,
        )
        restore_decision_replay = _post_json(
            client,
            restore_decision_url,
            headers=security_headers(args.security_user_id),
            body={"decision": "approved", "reason": restore_reason},
            label="Governed restore approval replay",
        )
        require_equal(
            restore_decision_replay.get("id"),
            restore_decision.get("id"),
            "restore decision replay",
        )

        restore_execution_url = (
            f"{governance_url}/api/v1/runtime-assurance-restore-decisions/"
            f"{restore_decision['id']}/execution"
        )
        restore_execution = _post_json(
            client,
            restore_execution_url,
            headers=governance_headers(args.user_id),
            body={},
            label="Governed restore execution",
        )
        validate_restore_execution(
            restore_execution,
            decision=restore_decision,
            request=restore_request,
            source_execution=actuation_execution,
            owner_id=args.user_id,
        )
        final_state = runner.run(_read_runtime_state(agent_id=agent_id, incident_id=incident_id))
        require_equal(final_state["kill_switch_engaged"], False, "restored kill switch")
        require_equal(
            final_state["runtime_control_transition_count"],
            initial_count + 2,
            "restore transition count",
        )
        restore_execution_replay = _post_json(
            client,
            restore_execution_url,
            headers=governance_headers(args.user_id),
            body={},
            label="Governed restore execution replay",
        )
        require_equal(
            restore_execution_replay.get("id"),
            restore_execution.get("id"),
            "restore execution replay",
        )
        replay_restored = runner.run(
            _read_runtime_state(agent_id=agent_id, incident_id=incident_id)
        )
        require_equal(
            replay_restored["runtime_control_transition_count"],
            initial_count + 2,
            "restore replay transition count",
        )

        post_status, post_routing = _routing_decision(
            client,
            governance_url=governance_url,
            agent_id=agent_id,
            user_id=args.user_id,
            task_id="p1-9-restored",
        )
        validate_allowed_routing(post_status, post_routing, "post-restore routing")

    telemetry_audit = runner.run(_verify_audit_events([success, failure], agent_id=agent_id))
    audit_specs = (
        (
            "actuation_request",
            actuation_request,
            "runtime_assurance.actuation_requested",
            "runtime_assurance_actuation_request",
        ),
        (
            "actuation_decision",
            actuation_decision,
            "runtime_assurance.actuation_approved",
            "runtime_assurance_actuation_decision",
        ),
        (
            "actuation_execution",
            actuation_execution,
            "runtime_assurance.actuation_executed",
            "runtime_assurance_actuation_execution",
        ),
        (
            "restore_request",
            restore_request,
            "runtime_assurance.restore_requested",
            "runtime_assurance_restore_request",
        ),
        (
            "restore_decision",
            restore_decision,
            "runtime_assurance.restore_approved",
            "runtime_assurance_restore_decision",
        ),
        (
            "restore_execution",
            restore_execution,
            "runtime_assurance.restore_executed",
            "runtime_assurance_restore_execution",
        ),
    )
    governance_audit: dict[str, object] = {}
    for key, record, action, entity_type in audit_specs:
        governance_audit[key] = runner.run(
            _verify_audit_entity(
                entity_id=str(record["id"]),
                action=action,
                entity_type=entity_type,
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
        "producer": {"success": probe["success"], "failure": probe["failure"]},
        "telemetry": {
            "completed": _event_report(success, telemetry_audit[str(success["event_id"])]),
            "failed": _event_report(failure, telemetry_audit[str(failure["event_id"])]),
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
        "zero_automatic_actuation": zero_actuation,
        "routing": {
            "preflight": _safe_routing(pre_routing),
            "contained": _safe_routing(blocked_routing),
            "restored": _safe_routing(post_routing),
        },
        "engage": {
            "request": _safe_request(actuation_request),
            "decision": _safe_decision(actuation_decision),
            "execution": _safe_execution(actuation_execution),
        },
        "remediation": {
            "incident_id": remediated.get("id"),
            "status": remediated.get("status"),
            "version": remediated.get("version"),
        },
        "restore": {
            "request": _safe_restore_request(restore_request),
            "decision": _safe_restore_decision(restore_decision),
            "execution": _safe_restore_execution(restore_execution),
        },
        "state": {
            "initial_transition_count": initial_count,
            "active_transition_count": state_active["runtime_control_transition_count"],
            "final_transition_count": final_state["runtime_control_transition_count"],
            "active_kill_switch": state_active["kill_switch_engaged"],
            "final_kill_switch": final_state["kill_switch_engaged"],
        },
        "audit": governance_audit,
    }
    assert_safe_report(report, secret=secret)
    _write_report(args.report, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the live governed-actuation verification CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify Credit Desk telemetry -> assurance -> governed engage -> runtime block -> "
            "remediation -> independent governed restore -> routing recovery."
        )
    )
    parser.add_argument("--governance-url", default=_DEFAULT_GOVERNANCE_URL)
    parser.add_argument("--router-url", default=_DEFAULT_ROUTER_URL)
    parser.add_argument("--agent-id")
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument("--user-id", default=_DEFAULT_USER_ID)
    parser.add_argument("--security-user-id", default=_DEFAULT_SECURITY_USER_ID)
    parser.add_argument("--timeout-seconds", type=float, default=_DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--report", type=Path, default=_DEFAULT_REPORT)
    parser.add_argument("--credit-desk-repo", type=Path, required=True)
    parser.add_argument("--credit-desk-port", type=int, default=_DEFAULT_CREDIT_DESK_PORT)
    parser.add_argument("--otlp-endpoint", default=_DEFAULT_OTLP_ENDPOINT)
    return parser


def main() -> int:
    """Run the P1.9e live proof and print only structural result information."""
    args = build_parser().parse_args()
    try:
        if args.timeout_seconds <= 0:
            raise VerificationError("--timeout-seconds must be greater than zero")
        if args.user_id == args.security_user_id:
            raise VerificationError("owner and Security approver must be different principals")
        with asyncio.Runner() as runner:
            try:
                run_scenario(args, runner=runner)
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
        print(f"[p1.9e] FAILED: {exc}", file=sys.stderr)
        return 2

    print("[p1.9e] PASSED")
    print(f"[p1.9e] report: {args.report}")
    print("[p1.9e] governed engage blocked routing; governed restore re-enabled fresh routing")
    print("[p1.9e] engage and restore used independent Security approvals and evidence chains")
    return 0


if __name__ == "__main__":
    sys.exit(main())
