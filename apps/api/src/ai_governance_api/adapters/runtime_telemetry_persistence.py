"""SQLAlchemy adapters for sanitized runtime telemetry evidence."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_governance_api.application.runtime_telemetry import (
    RuntimeTelemetryAuditPort,
    RuntimeTelemetryScopeReaderPort,
    RuntimeTelemetryStorePort,
)
from ai_governance_api.audit import append_audit_event
from ai_governance_api.domain.runtime_telemetry import (
    RuntimeTelemetryAgentScope,
    RuntimeTelemetryCommand,
    RuntimeTelemetryOutcome,
    RuntimeTelemetryRecord,
)
from ai_governance_api.models import Agent, AISystem, RuntimeTelemetryEventEntry


class SqlAlchemyRuntimeTelemetryScopeReader(RuntimeTelemetryScopeReaderPort):
    """Read minimal governed agent ownership facts using short-lived sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, agent_id: str) -> RuntimeTelemetryAgentScope | None:
        """Return minimal governed ownership facts for one agent."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Agent, AISystem)
                    .join(AISystem, Agent.ai_system_id == AISystem.id)
                    .where(Agent.id == agent_id)
                )
            ).one_or_none()
        if row is None:
            return None
        agent, system = row
        return RuntimeTelemetryAgentScope(
            agent_id=agent.id,
            ai_system_id=system.id,
            initiative_id=system.initiative_id,
            agent_owner_id=agent.owner_id,
            ai_system_owner_id=system.owner_id,
        )


class SqlAlchemyRuntimeTelemetryStore(RuntimeTelemetryStorePort):
    """Persist and query the normalized telemetry table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, event_id: str) -> RuntimeTelemetryRecord | None:
        """Return a previously persisted telemetry event by external ID."""
        entry = await self._session.get(RuntimeTelemetryEventEntry, event_id)
        return _to_domain(entry) if entry is not None else None

    async def save(self, record: RuntimeTelemetryRecord) -> RuntimeTelemetryRecord:
        """Persist one normalized runtime telemetry event without committing."""
        self._session.add(_to_entry(record))
        await self._session.flush()
        return record

    async def list_for_agent(
        self,
        agent_id: str,
        *,
        limit: int,
    ) -> list[RuntimeTelemetryRecord]:
        """Return recent normalized telemetry events for one agent."""
        entries = (
            await self._session.scalars(
                select(RuntimeTelemetryEventEntry)
                .where(RuntimeTelemetryEventEntry.agent_id == agent_id)
                .order_by(
                    RuntimeTelemetryEventEntry.observed_at.desc(),
                    RuntimeTelemetryEventEntry.event_id.desc(),
                )
                .limit(limit)
            )
        ).all()
        return [_to_domain(entry) for entry in entries]


class SqlAlchemyRuntimeTelemetryAudit(RuntimeTelemetryAuditPort):
    """Append minimized ingestion facts to the tamper-evident audit chain."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, record: RuntimeTelemetryRecord) -> None:
        """Append minimized telemetry ingestion evidence to the audit chain."""
        await append_audit_event(
            self._session,
            actor_id=f"runtime-telemetry:{record.agent_id}",
            action="runtime_telemetry.ingested",
            entity_type="runtime_telemetry_event",
            entity_id=record.event_id,
            entity_version=record.version,
            payload={
                "agent_id": record.agent_id,
                "ai_system_id": record.ai_system_id,
                "event_name": record.command.event_name,
                "event_outcome": record.command.event_outcome.value,
                "service": record.command.service,
                "payload_digest": record.payload_digest,
            },
        )


def _to_entry(record: RuntimeTelemetryRecord) -> RuntimeTelemetryEventEntry:
    command = record.command
    return RuntimeTelemetryEventEntry(
        event_id=record.event_id,
        agent_id=record.agent_id,
        ai_system_id=record.ai_system_id,
        initiative_id=record.initiative_id,
        source_schema_version=command.source_schema_version,
        observed_at=command.observed_at,
        ingested_at=record.ingested_at,
        event_name=command.event_name,
        event_outcome=command.event_outcome.value,
        service=command.service,
        environment=command.environment,
        service_version=command.version,
        trace_id=command.trace_id,
        span_id=command.span_id,
        component=command.component,
        operation=command.operation,
        correlation_id=command.correlation_id,
        request_id=command.request_id,
        retry_count=command.retry_count,
        duration_ms=command.duration_ms,
        http_method=command.http_method,
        http_status_code=command.http_status_code,
        error_type=command.error_type,
        payload_digest=record.payload_digest,
        version=record.version,
    )


def _to_domain(entry: RuntimeTelemetryEventEntry) -> RuntimeTelemetryRecord:
    return RuntimeTelemetryRecord(
        event_id=entry.event_id,
        agent_id=entry.agent_id,
        ai_system_id=entry.ai_system_id,
        initiative_id=entry.initiative_id,
        command=RuntimeTelemetryCommand(
            source_schema_version=entry.source_schema_version,
            event_id=entry.event_id,
            observed_at=entry.observed_at,
            event_name=entry.event_name,
            event_outcome=RuntimeTelemetryOutcome(entry.event_outcome),
            service=entry.service,
            environment=entry.environment,
            version=entry.service_version,
            trace_id=entry.trace_id,
            span_id=entry.span_id,
            component=entry.component,
            operation=entry.operation,
            correlation_id=entry.correlation_id,
            request_id=entry.request_id,
            retry_count=entry.retry_count,
            duration_ms=entry.duration_ms,
            http_method=entry.http_method,
            http_status_code=entry.http_status_code,
            error_type=entry.error_type,
        ),
        ingested_at=entry.ingested_at,
        payload_digest=entry.payload_digest,
        version=entry.version,
    )
