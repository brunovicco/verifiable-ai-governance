"""HTTP contracts for content-free runtime telemetry evidence."""

from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from ai_governance_api.domain.runtime_telemetry import (
    RuntimeTelemetryCommand,
    RuntimeTelemetryOutcome,
)

_Bounded = Annotated[str, StringConstraints(min_length=1, max_length=256)]
_EventName = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
_TraceId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
_SpanId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16}$")]


def _require_utc(value: datetime) -> datetime:
    """Reject naive or non-UTC timestamps."""
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware and expressed in UTC")
    return value


UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]


class RuntimeTelemetryEventRequest(BaseModel):
    """Versioned, closed ingestion contract. No content-bearing extension bag exists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    source_schema_version: Literal[1]
    event_id: UUID
    observed_at: UtcDatetime
    event_name: _EventName
    event_outcome: RuntimeTelemetryOutcome
    service: _Bounded
    environment: _Bounded
    version: _Bounded
    trace_id: _TraceId | None = None
    span_id: _SpanId | None = None
    component: _Bounded | None = None
    operation: _Bounded | None = None
    correlation_id: _Bounded | None = None
    request_id: _Bounded | None = None
    retry_count: int | None = Field(default=None, ge=0, le=1000)
    duration_ms: float | None = Field(default=None, ge=0, le=86_400_000)
    http_method: Annotated[str, StringConstraints(min_length=1, max_length=16)] | None = None
    http_status_code: int | None = Field(default=None, ge=100, le=599)
    error_type: _Bounded | None = None

    def to_command(self) -> RuntimeTelemetryCommand:
        """Map the transport schema into the framework-free command."""
        return RuntimeTelemetryCommand(
            source_schema_version=self.source_schema_version,
            event_id=str(self.event_id),
            observed_at=self.observed_at,
            event_name=self.event_name,
            event_outcome=self.event_outcome,
            service=self.service,
            environment=self.environment,
            version=self.version,
            trace_id=self.trace_id,
            span_id=self.span_id,
            component=self.component,
            operation=self.operation,
            correlation_id=self.correlation_id,
            request_id=self.request_id,
            retry_count=self.retry_count,
            duration_ms=self.duration_ms,
            http_method=self.http_method,
            http_status_code=self.http_status_code,
            error_type=self.error_type,
        )


class RuntimeTelemetryEventRead(BaseModel):
    """Public persisted telemetry evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    event_id: UUID
    agent_id: UUID
    ai_system_id: UUID
    initiative_id: UUID
    source_schema_version: Literal[1]
    observed_at: UtcDatetime
    ingested_at: UtcDatetime
    event_name: _EventName
    event_outcome: RuntimeTelemetryOutcome
    service: _Bounded
    environment: _Bounded
    version: _Bounded
    trace_id: _TraceId | None = None
    span_id: _SpanId | None = None
    component: _Bounded | None = None
    operation: _Bounded | None = None
    correlation_id: _Bounded | None = None
    request_id: _Bounded | None = None
    retry_count: int | None = None
    duration_ms: float | None = None
    http_method: str | None = None
    http_status_code: int | None = None
    error_type: _Bounded | None = None
    payload_digest: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    record_version: int = Field(ge=1)
