"""Sanitized runtime-telemetry ingestion and query use cases."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.runtime_telemetry import (
    RuntimeTelemetryAgentScope,
    RuntimeTelemetryCommand,
    RuntimeTelemetryRecord,
    runtime_telemetry_digest,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]


class RuntimeTelemetryScopeReaderPort(Protocol):
    """Read the governed agent binding used by telemetry ingestion."""

    async def get(self, agent_id: str) -> RuntimeTelemetryAgentScope | None:
        """Return the governed scope or None when the agent is unknown."""
        ...


class RuntimeTelemetryStorePort(Protocol):
    """Persist and query sanitized runtime telemetry."""

    async def get(self, event_id: str) -> RuntimeTelemetryRecord | None:
        """Return a previously ingested event by external event ID."""
        ...

    async def save(self, record: RuntimeTelemetryRecord) -> RuntimeTelemetryRecord:
        """Persist one new event without committing."""
        ...

    async def list_for_agent(
        self,
        agent_id: str,
        *,
        limit: int,
    ) -> list[RuntimeTelemetryRecord]:
        """Return recent events for one agent."""
        ...


class RuntimeTelemetryAuditPort(Protocol):
    """Append content-minimized telemetry ingestion evidence to the audit chain."""

    async def append(self, record: RuntimeTelemetryRecord) -> None:
        """Append the ingestion audit event in the surrounding transaction."""
        ...


class RuntimeTelemetryTransactionPort(Protocol):
    """Transaction boundary for telemetry evidence and audit events."""

    async def commit(self) -> None:
        """Commit pending persistence changes."""
        ...

    async def rollback(self) -> None:
        """Roll back pending persistence changes."""
        ...


class IngestRuntimeTelemetry:
    """Persist one sanitized event with idempotent event-ID semantics."""

    def __init__(
        self,
        scope_reader: RuntimeTelemetryScopeReaderPort,
        store: RuntimeTelemetryStorePort,
        audit: RuntimeTelemetryAuditPort,
        transaction: RuntimeTelemetryTransactionPort,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._scope_reader = scope_reader
        self._store = store
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))

    async def execute(
        self,
        *,
        agent_id: str,
        command: RuntimeTelemetryCommand,
    ) -> RuntimeTelemetryRecord:
        """Validate agent binding and persist sanitized telemetry exactly once."""
        scope = await self._scope_reader.get(agent_id)
        if scope is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Agent not found")

        digest = runtime_telemetry_digest(command)
        existing = await self._store.get(command.event_id)
        if existing is not None:
            if existing.agent_id != agent_id or existing.payload_digest != digest:
                raise ApplicationError(
                    ErrorKind.CONFLICT,
                    "Runtime telemetry event ID is already bound to different evidence",
                )
            return existing

        record = RuntimeTelemetryRecord(
            event_id=command.event_id,
            agent_id=scope.agent_id,
            ai_system_id=scope.ai_system_id,
            initiative_id=scope.initiative_id,
            command=command,
            ingested_at=self._clock(),
            payload_digest=digest,
        )
        try:
            stored = await self._store.save(record)
            await self._audit.append(stored)
            await self._transaction.commit()
            return stored
        except Exception:
            await self._transaction.rollback()
            raise


class ListRuntimeTelemetryEvents:
    """List recent telemetry after enforcing governed ownership."""

    def __init__(
        self,
        scope_reader: RuntimeTelemetryScopeReaderPort,
        store: RuntimeTelemetryStorePort,
        *,
        limit: int = 100,
    ) -> None:
        self._scope_reader = scope_reader
        self._store = store
        self._limit = limit

    async def execute(
        self,
        *,
        agent_id: str,
        principal: Principal,
    ) -> list[RuntimeTelemetryRecord]:
        """Return telemetry visible to the system owner, agent owner, or admin."""
        scope = await self._scope_reader.get(agent_id)
        if scope is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Agent not found")
        if (
            principal.user_id not in {scope.agent_owner_id, scope.ai_system_owner_id}
            and not principal.is_admin
        ):
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the system owner, agent owner, or an administrator "
                "can view runtime telemetry",
            )
        return await self._store.list_for_agent(agent_id, limit=self._limit)
