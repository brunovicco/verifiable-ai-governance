"""HTTP adapter for sanitized runtime telemetry ingestion and queries."""

import secrets

from fastapi import APIRouter, Header, HTTPException, status

from ai_governance_api.config import Settings
from ai_governance_api.dependencies import (
    CurrentPrincipal,
    IngestRuntimeTelemetryDependency,
    ListRuntimeTelemetryEventsDependency,
    SettingsDependency,
)
from ai_governance_api.domain.runtime_telemetry import RuntimeTelemetryRecord
from ai_governance_api.runtime_telemetry_schemas import (
    RuntimeTelemetryEventRead,
    RuntimeTelemetryEventRequest,
)

router = APIRouter(prefix="/api/v1", tags=["runtime-telemetry"])


@router.post(
    "/agents/{agent_id}/runtime-telemetry",
    response_model=RuntimeTelemetryEventRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_runtime_telemetry(
    agent_id: str,
    request: RuntimeTelemetryEventRequest,
    use_case: IngestRuntimeTelemetryDependency,
    settings: SettingsDependency,
    x_telemetry_api_key: str | None = Header(
        default=None,
        alias="X-Telemetry-Api-Key",
        max_length=1024,
    ),
) -> RuntimeTelemetryEventRead:
    """Persist one content-free event after per-agent machine authentication."""
    _authenticate(settings, agent_id=agent_id, api_key=x_telemetry_api_key)
    record = await use_case.execute(agent_id=agent_id, command=request.to_command())
    return _to_read(record)


@router.get(
    "/agents/{agent_id}/runtime-telemetry",
    response_model=list[RuntimeTelemetryEventRead],
)
async def list_runtime_telemetry(
    agent_id: str,
    use_case: ListRuntimeTelemetryEventsDependency,
    principal: CurrentPrincipal,
) -> list[RuntimeTelemetryEventRead]:
    """List sanitized runtime telemetry for authorized agent stakeholders."""
    records = await use_case.execute(agent_id=agent_id, principal=principal)
    return [_to_read(record) for record in records]


def _authenticate(settings: Settings, *, agent_id: str, api_key: str | None) -> None:
    if not settings.runtime_telemetry_ingest_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime telemetry ingestion is disabled",
        )
    configured = settings.runtime_telemetry_api_key_map.get(agent_id)
    if configured is None or api_key is None or not secrets.compare_digest(configured, api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing or invalid runtime telemetry credential",
        )


def _to_read(record: RuntimeTelemetryRecord) -> RuntimeTelemetryEventRead:
    command = record.command
    return RuntimeTelemetryEventRead.model_validate(
        {
            "event_id": record.event_id,
            "agent_id": record.agent_id,
            "ai_system_id": record.ai_system_id,
            "initiative_id": record.initiative_id,
            "source_schema_version": command.source_schema_version,
            "observed_at": command.observed_at,
            "ingested_at": record.ingested_at,
            "event_name": command.event_name,
            "event_outcome": command.event_outcome,
            "service": command.service,
            "environment": command.environment,
            "version": command.version,
            "trace_id": command.trace_id,
            "span_id": command.span_id,
            "component": command.component,
            "operation": command.operation,
            "correlation_id": command.correlation_id,
            "request_id": command.request_id,
            "retry_count": command.retry_count,
            "duration_ms": command.duration_ms,
            "http_method": command.http_method,
            "http_status_code": command.http_status_code,
            "error_type": command.error_type,
            "payload_digest": record.payload_digest,
            "record_version": record.version,
        }
    )
