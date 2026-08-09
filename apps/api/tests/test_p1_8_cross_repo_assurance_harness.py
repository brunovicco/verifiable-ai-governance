"""Pure tests for the P1.8d cross-repository Runtime Assurance harness."""

import json

import pytest

from scripts.verify_p1_7_cross_repo_telemetry_e2e import VerificationError
from scripts.verify_p1_8_cross_repo_assurance_e2e import (
    assert_safe_report,
    validate_assurance_evaluation,
    validate_promotion,
    validate_recommendation,
    validate_zero_actuation,
)

_AGENT_ID = "11111111-1111-4111-8111-111111111111"
_SUCCESS_ID = "22222222-2222-4222-8222-222222222222"
_FAILURE_ID = "33333333-3333-4333-8333-333333333333"


def _evaluation(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "44444444-4444-4444-8444-444444444444",
        "agent_id": _AGENT_ID,
        "ai_system_id": "55555555-5555-4555-8555-555555555555",
        "policy_version": 3,
        "sample_count": 2,
        "failure_count": 1,
        "failure_rate": 0.5,
        "outcome": "breached",
        "breach_reasons": ["failure_rate_exceeded"],
        "severity": "critical",
        "source_event_ids": [_SUCCESS_ID, _FAILURE_ID],
        "evidence_digest": "a" * 64,
        "version": 1,
    }
    value.update(overrides)
    return value


def _promotion(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "promotion_id": "66666666-6666-4666-8666-666666666666",
        "evaluation_id": _evaluation()["id"],
        "agent_id": _AGENT_ID,
        "ai_system_id": _evaluation()["ai_system_id"],
        "incident_id": "77777777-7777-4777-8777-777777777777",
        "breach_fingerprint": "b" * 64,
        "disposition": "deduplicated",
        "evidence_digest": _evaluation()["evidence_digest"],
        "incident_status": "open",
        "incident_severity": "critical",
        "incident_version": 2,
    }
    value.update(overrides)
    return value


def _before() -> dict[str, object]:
    return {
        "agent_id": _AGENT_ID,
        "agent_version": 6,
        "kill_switch_enabled": True,
        "kill_switch_engaged": False,
        "incident_id": _promotion()["incident_id"],
        "incident_status": "open",
        "incident_severity": "critical",
        "incident_version": 2,
        "runtime_control_transition_count": 4,
    }


def _recommendation(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "88888888-8888-4888-8888-888888888888",
        "promotion_id": _promotion()["promotion_id"],
        "evaluation_id": _promotion()["evaluation_id"],
        "incident_id": _promotion()["incident_id"],
        "breach_fingerprint": _promotion()["breach_fingerprint"],
        "source_evidence_digest": "a" * 64,
        "policy_id": "runtime-assurance-response",
        "policy_version": "1.0",
        "policy_digest": "c" * 64,
        "incident_status": "open",
        "incident_severity": "critical",
        "incident_version": 2,
        "kill_switch_enabled": True,
        "kill_switch_engaged": False,
        "actions": [
            "investigate_failures",
            "prepare_containment",
            "consider_kill_switch",
        ],
        "rationale_codes": [
            "failure_rate_exceeded",
            "elevated_severity",
            "critical_kill_switch_available",
        ],
        "advisory_only": True,
        "recommendation_digest": "d" * 64,
        "version": 1,
    }
    value.update(overrides)
    return value


def test_assurance_must_bind_exactly_to_fresh_success_and_failure_events() -> None:
    validate_assurance_evaluation(
        _evaluation(),
        agent_id=_AGENT_ID,
        source_event_ids={_SUCCESS_ID, _FAILURE_ID},
    )


def test_assurance_rejects_stale_or_unrelated_source_event() -> None:
    with pytest.raises(VerificationError, match="fresh Credit Desk events"):
        validate_assurance_evaluation(
            _evaluation(source_event_ids=[_SUCCESS_ID, "unrelated"]),
            agent_id=_AGENT_ID,
            source_event_ids={_SUCCESS_ID, _FAILURE_ID},
        )


@pytest.mark.parametrize(
    "disposition",
    ["created", "deduplicated", "severity_escalated"],
)
def test_promotion_accepts_all_governed_active_dispositions(disposition: str) -> None:
    validate_promotion(
        _promotion(disposition=disposition),
        evaluation=_evaluation(),
        agent_id=_AGENT_ID,
    )


def test_recommendation_requires_critical_advisory_kill_switch_consideration() -> None:
    validate_recommendation(
        _recommendation(),
        promotion=_promotion(),
        before=_before(),
    )


def test_recommendation_rejects_missing_consider_kill_switch() -> None:
    with pytest.raises(VerificationError, match="required actions"):
        validate_recommendation(
            _recommendation(actions=["investigate_failures", "prepare_containment"]),
            promotion=_promotion(),
            before=_before(),
        )


def test_zero_actuation_requires_exact_mutable_state_stability() -> None:
    before = _before()
    assert validate_zero_actuation(before, dict(before)) == {
        "incident_unchanged": True,
        "agent_unchanged": True,
        "runtime_control_transition_count_unchanged": True,
    }

    changed = dict(before)
    changed["kill_switch_engaged"] = True
    with pytest.raises(VerificationError, match="unexpected actuation"):
        validate_zero_actuation(before, changed)


def test_report_safety_rejects_business_or_secret_content() -> None:
    safe = {
        "result": "passed",
        "recommendation": {
            "actions": ["consider_kill_switch"],
            "advisory_only": True,
        },
    }
    assert_safe_report(safe, secret="machine-secret-value")

    unsafe_business = json.loads(json.dumps(safe))
    unsafe_business["annual_revenue"] = 1
    with pytest.raises(VerificationError, match="forbidden content"):
        assert_safe_report(unsafe_business, secret="machine-secret-value")

    unsafe_secret = json.loads(json.dumps(safe))
    unsafe_secret["value"] = "machine-secret-value"
    with pytest.raises(VerificationError, match="secret"):
        assert_safe_report(unsafe_secret, secret="machine-secret-value")
