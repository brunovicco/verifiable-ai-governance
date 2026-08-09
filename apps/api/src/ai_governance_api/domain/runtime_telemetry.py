"""Pure runtime-telemetry evidence types."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum

_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^[0-9a-f]{16}$")


class RuntimeTelemetryOutcome(StrEnum):
    """Closed outcome vocabulary mirrored from a2a-otel-kit structured events."""

    STARTED = "started"
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RuntimeTelemetryCommand:
    """Content-free telemetry event accepted at the Governance boundary."""

    source_schema_version: int
    event_id: str
    observed_at: datetime
    event_name: str
    event_outcome: RuntimeTelemetryOutcome
    service: str
    environment: str
    version: str
    trace_id: str | None = None
    span_id: str | None = None
    component: str | None = None
    operation: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    retry_count: int | None = None
    duration_ms: float | None = None
    http_method: str | None = None
    http_status_code: int | None = None
    error_type: str | None = None

    def __post_init__(self) -> None:
        """Enforce invariants independent of the HTTP schema."""
        if self.source_schema_version != 1:
            raise ValueError("unsupported runtime telemetry source schema")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.observed_at.utcoffset() != UTC.utcoffset(self.observed_at):
            raise ValueError("observed_at must be expressed in UTC")
        if not self.event_name.strip():
            raise ValueError("event_name must be non-empty")
        if self.trace_id is not None and not _TRACE_ID.fullmatch(self.trace_id):
            raise ValueError("trace_id must be 32 lowercase hexadecimal characters")
        if self.span_id is not None and not _SPAN_ID.fullmatch(self.span_id):
            raise ValueError("span_id must be 16 lowercase hexadecimal characters")
        if self.retry_count is not None and self.retry_count < 0:
            raise ValueError("retry_count cannot be negative")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")


@dataclass(frozen=True, slots=True)
class RuntimeTelemetryAgentScope:
    """Minimal governed ownership facts used by telemetry ingestion and queries."""

    agent_id: str
    ai_system_id: str
    initiative_id: str
    agent_owner_id: str
    ai_system_owner_id: str


@dataclass(frozen=True, slots=True)
class RuntimeTelemetryRecord:
    """Durable sanitized telemetry evidence."""

    event_id: str
    agent_id: str
    ai_system_id: str
    initiative_id: str
    command: RuntimeTelemetryCommand
    ingested_at: datetime
    payload_digest: str
    version: int = 1


def runtime_telemetry_digest(command: RuntimeTelemetryCommand) -> str:
    """Return SHA-256 over canonical, content-free telemetry fields."""
    payload = asdict(command)
    payload["observed_at"] = command.observed_at.isoformat()
    payload["event_outcome"] = command.event_outcome.value
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
