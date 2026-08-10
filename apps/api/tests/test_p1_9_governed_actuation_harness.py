import pytest

from scripts.verify_p1_7_cross_repo_telemetry_e2e import VerificationError
from scripts.verify_p1_9_governed_actuation_e2e import (
    validate_actuation_decision,
    validate_actuation_execution,
    validate_actuation_request,
    validate_allowed_routing,
    validate_kill_switch_block,
    validate_restore_decision,
    validate_restore_execution,
    validate_restore_request,
)

_OWNER = "demo.requester"
_SECURITY = "demo.security"
_AGENT = "agent-1"
_SYSTEM = "system-1"
_INCIDENT = "incident-1"


def _recommendation() -> dict[str, object]:
    return {
        "id": "recommendation-1",
        "recommendation_digest": "a" * 64,
        "promotion_id": "promotion-1",
        "evaluation_id": "evaluation-1",
        "incident_id": _INCIDENT,
        "agent_id": _AGENT,
        "ai_system_id": _SYSTEM,
    }


def _request() -> dict[str, object]:
    return {
        "id": "request-1",
        "recommendation_id": "recommendation-1",
        "recommendation_digest": "a" * 64,
        "promotion_id": "promotion-1",
        "evaluation_id": "evaluation-1",
        "incident_id": _INCIDENT,
        "agent_id": _AGENT,
        "ai_system_id": _SYSTEM,
        "action": "engage_kill_switch",
        "state": "pending",
        "requested_by": _OWNER,
        "request_digest": "b" * 64,
    }


def _decision() -> dict[str, object]:
    return {
        "id": "decision-1",
        "request_id": "request-1",
        "request_digest": "b" * 64,
        "action": "engage_kill_switch",
        "decision": "approved",
        "approval_area": "security",
        "decided_by": _SECURITY,
        "decision_digest": "c" * 64,
    }


def _execution() -> dict[str, object]:
    return {
        "id": "execution-1",
        "decision_id": "decision-1",
        "decision_digest": "c" * 64,
        "request_id": "request-1",
        "request_digest": "b" * 64,
        "action": "engage_kill_switch",
        "agent_id": _AGENT,
        "ai_system_id": _SYSTEM,
        "incident_id": _INCIDENT,
        "previous_state": "inactive",
        "target_state": "active",
        "executed_by": _OWNER,
        "execution_digest": "d" * 64,
    }


def _restore_request() -> dict[str, object]:
    return {
        "id": "restore-request-1",
        "source_execution_id": "execution-1",
        "source_execution_digest": "d" * 64,
        "action": "restore_kill_switch",
        "state": "pending",
        "incident_status": "remediating",
        "requested_by": _OWNER,
        "remediation_digest": "e" * 64,
        "request_digest": "f" * 64,
    }


def _restore_decision() -> dict[str, object]:
    return {
        "id": "restore-decision-1",
        "request_id": "restore-request-1",
        "request_digest": "f" * 64,
        "source_execution_id": "execution-1",
        "action": "restore_kill_switch",
        "decision": "approved",
        "approval_area": "security",
        "decided_by": _SECURITY,
        "decision_digest": "1" * 64,
    }


def _restore_execution() -> dict[str, object]:
    return {
        "id": "restore-execution-1",
        "decision_id": "restore-decision-1",
        "decision_digest": "1" * 64,
        "request_id": "restore-request-1",
        "source_execution_id": "execution-1",
        "action": "restore_kill_switch",
        "previous_state": "active",
        "target_state": "inactive",
        "executed_by": _OWNER,
        "execution_digest": "2" * 64,
    }


def test_engage_chain_validators_accept_independent_governed_evidence() -> None:
    validate_actuation_request(_request(), recommendation=_recommendation(), owner_id=_OWNER)
    validate_actuation_decision(
        _decision(),
        request=_request(),
        approver_id=_SECURITY,
    )
    validate_actuation_execution(
        _execution(),
        decision=_decision(),
        request=_request(),
        owner_id=_OWNER,
    )


def test_restore_chain_validators_accept_distinct_governed_evidence() -> None:
    validate_restore_request(
        _restore_request(),
        source_execution=_execution(),
        owner_id=_OWNER,
    )
    validate_restore_decision(
        _restore_decision(),
        request=_restore_request(),
        source_execution=_execution(),
        approver_id=_SECURITY,
        engage_decision=_decision(),
    )
    validate_restore_execution(
        _restore_execution(),
        decision=_restore_decision(),
        request=_restore_request(),
        source_execution=_execution(),
        owner_id=_OWNER,
    )


def test_restore_decision_rejects_engage_digest_reuse() -> None:
    restore = _restore_decision()
    restore["decision_digest"] = _decision()["decision_digest"]
    with pytest.raises(VerificationError, match="reused engage decision digest"):
        validate_restore_decision(
            restore,
            request=_restore_request(),
            source_execution=_execution(),
            approver_id=_SECURITY,
            engage_decision=_decision(),
        )


def test_kill_switch_block_requires_governance_reason_code() -> None:
    validate_kill_switch_block(
        422,
        {
            "outcome": "blocked",
            "decision_source": "governance_registry",
            "reason_code": "kill_switch_engaged",
            "selected_model_group": None,
        },
    )
    with pytest.raises(VerificationError, match="reason code"):
        validate_kill_switch_block(
            422,
            {
                "outcome": "blocked",
                "decision_source": "governance_registry",
                "reason_code": "router_unavailable",
                "selected_model_group": None,
            },
        )


def test_allowed_routing_requires_real_router_source() -> None:
    validate_allowed_routing(
        200,
        {
            "outcome": "allowed",
            "decision_source": "policy_model_router",
            "selected_model_group": "reasoning-strong",
        },
        "routing",
    )
    with pytest.raises(VerificationError, match="decision source"):
        validate_allowed_routing(
            200,
            {
                "outcome": "allowed",
                "decision_source": "governance_registry",
                "selected_model_group": "reasoning-strong",
            },
            "routing",
        )


def test_tampered_digest_is_rejected() -> None:
    request = _request()
    request["request_digest"] = "not-a-digest"
    with pytest.raises(VerificationError, match="SHA-256"):
        validate_actuation_request(request, recommendation=_recommendation(), owner_id=_OWNER)
