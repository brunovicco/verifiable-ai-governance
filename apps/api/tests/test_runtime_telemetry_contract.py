from datetime import UTC, datetime
from uuid import UUID

import pytest
from ai_governance_api.domain.runtime_telemetry import RuntimeTelemetryOutcome
from ai_governance_api.runtime_telemetry_schemas import RuntimeTelemetryEventRequest
from pydantic import ValidationError


def payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "source_schema_version": 1,
        "event_id": "11111111-1111-4111-8111-111111111111",
        "observed_at": "2026-08-08T22:00:00Z",
        "event_name": "a2a.client.send_message.completed",
        "event_outcome": "success",
        "service": "decisao-agent",
        "environment": "local",
        "version": "0.1.0",
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "operation": "send_message",
        "correlation_id": "routing-123",
        "duration_ms": 12.5,
    }


def test_contract_maps_content_free_event() -> None:
    request = RuntimeTelemetryEventRequest.model_validate(payload())
    command = request.to_command()

    assert command.event_id == str(UUID("11111111-1111-4111-8111-111111111111"))
    assert command.observed_at == datetime(2026, 8, 8, 22, tzinfo=UTC)
    assert command.event_outcome is RuntimeTelemetryOutcome.SUCCESS
    assert command.trace_id == "a" * 32


def test_contract_forbids_content_extension_fields() -> None:
    raw = payload()
    raw["prompt"] = "must never cross telemetry boundary"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RuntimeTelemetryEventRequest.model_validate(raw)


def test_contract_rejects_bad_trace_id_and_non_utc_time() -> None:
    raw = payload()
    raw["trace_id"] = "not-a-trace"
    with pytest.raises(ValidationError):
        RuntimeTelemetryEventRequest.model_validate(raw)

    raw = payload()
    raw["observed_at"] = "2026-08-08T19:00:00-03:00"
    with pytest.raises(ValidationError, match="expressed in UTC"):
        RuntimeTelemetryEventRequest.model_validate(raw)
