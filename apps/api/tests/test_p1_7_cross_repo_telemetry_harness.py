"""Pure tests for the P1.7d live cross-repository telemetry verification harness."""

import json

import pytest

from scripts.verify_p1_7_cross_repo_telemetry_e2e import (
    VerificationError,
    _event_report,
    _parse_probe,
    audit_event_hash,
    validate_runtime_event,
)

_AGENT_ID = "11111111-1111-4111-8111-111111111111"
_EVENT_ID = "22222222-2222-4222-8222-222222222222"
_SECRET = "local-machine-credential-value"


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "event_id": _EVENT_ID,
        "agent_id": _AGENT_ID,
        "ai_system_id": "33333333-3333-4333-8333-333333333333",
        "initiative_id": "44444444-4444-4444-8444-444444444444",
        "source_schema_version": 1,
        "observed_at": "2026-08-09T16:00:00+00:00",
        "ingested_at": "2026-08-09T16:00:01+00:00",
        "event_name": "decisao_agent.evaluation.completed",
        "event_outcome": "success",
        "service": "decisao-agent",
        "environment": "p1.7-live-e2e",
        "version": "0.1.0",
        "trace_id": "1" * 32,
        "span_id": "2" * 16,
        "component": "a2a_executor",
        "operation": "credit_evaluation",
        "correlation_id": "context-1",
        "request_id": "task-1",
        "retry_count": None,
        "duration_ms": 12.5,
        "http_method": None,
        "http_status_code": None,
        "error_type": None,
        "payload_digest": "3" * 64,
        "record_version": 1,
    }
    record.update(overrides)
    return record


def test_validate_runtime_event_accepts_closed_structural_evidence() -> None:
    validate_runtime_event(
        _record(),
        agent_id=_AGENT_ID,
        correlation_id="context-1",
        request_id="task-1",
        event_name="decisao_agent.evaluation.completed",
        event_outcome="success",
        error_type=None,
        api_key=_SECRET,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trace_id", None),
        ("trace_id", "not-a-trace"),
        ("span_id", "not-a-span"),
        ("payload_digest", "not-a-digest"),
        ("duration_ms", -1),
        ("source_schema_version", 2),
    ],
)
def test_validate_runtime_event_fails_closed_for_invalid_structural_evidence(
    field: str,
    value: object,
) -> None:
    with pytest.raises(VerificationError):
        validate_runtime_event(
            _record(**{field: value}),
            agent_id=_AGENT_ID,
            correlation_id="context-1",
            request_id="task-1",
            event_name="decisao_agent.evaluation.completed",
            event_outcome="success",
            error_type=None,
            api_key=_SECRET,
        )


def test_validate_runtime_event_rejects_sensitive_or_business_content() -> None:
    with pytest.raises(VerificationError):
        validate_runtime_event(
            _record(prompt="must-not-exist"),
            agent_id=_AGENT_ID,
            correlation_id="context-1",
            request_id="task-1",
            event_name="decisao_agent.evaluation.completed",
            event_outcome="success",
            error_type=None,
            api_key=_SECRET,
        )


def test_parse_probe_keeps_only_structural_task_identifiers() -> None:
    payload = json.dumps(
        {
            "success": {
                "context_id": "ctx-success",
                "task_id": "task-success",
                "state": "completed",
                "decision": "APPROVAL_RECOMMENDED",
            },
            "failure": {
                "context_id": "ctx-failure",
                "task_id": "task-failure",
                "state": "failed",
                "error_code": "INVALID_INPUT",
            },
        }
    )
    assert _parse_probe(payload) == {
        "success": {
            "context_id": "ctx-success",
            "task_id": "task-success",
            "state": "completed",
        },
        "failure": {
            "context_id": "ctx-failure",
            "task_id": "task-failure",
            "state": "failed",
        },
    }


def test_audit_event_hash_matches_canonical_governance_formula() -> None:
    payload = {
        "agent_id": _AGENT_ID,
        "event_name": "decisao_agent.evaluation.completed",
    }
    left = audit_event_hash(
        salt="test-salt",
        actor_id=f"runtime-telemetry:{_AGENT_ID}",
        action="runtime_telemetry.ingested",
        entity_type="runtime_telemetry_event",
        entity_id=_EVENT_ID,
        entity_version=1,
        payload=payload,
        previous_hash="4" * 64,
    )
    right = audit_event_hash(
        salt="test-salt",
        actor_id=f"runtime-telemetry:{_AGENT_ID}",
        action="runtime_telemetry.ingested",
        entity_type="runtime_telemetry_event",
        entity_id=_EVENT_ID,
        entity_version=1,
        payload=payload,
        previous_hash="4" * 64,
    )
    assert left == right
    assert len(left) == 64


def test_event_report_is_content_minimized() -> None:
    report = _event_report(
        _record(),
        {
            "audit_event_id": "audit-1",
            "event_hash": "4" * 64,
            "previous_hash": "5" * 64,
            "predecessor_resolved": True,
        },
    )
    serialized = json.dumps(report)
    assert "annual_revenue" not in serialized
    assert "initiative_id" not in serialized
    assert "ai_system_id" not in serialized
    assert _SECRET not in serialized
