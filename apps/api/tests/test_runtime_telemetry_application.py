import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ai_governance_api.application.runtime_telemetry import (
    IngestRuntimeTelemetry,
    ListRuntimeTelemetryEvents,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.runtime_telemetry import (
    RuntimeTelemetryAgentScope,
    RuntimeTelemetryCommand,
    RuntimeTelemetryOutcome,
    RuntimeTelemetryRecord,
)
from ai_governance_api.errors import ApplicationError

NOW = datetime(2026, 8, 8, 22, 0, tzinfo=UTC)


class ScopeReader:
    async def get(self, agent_id: str):
        if agent_id != "agent-1":
            return None
        return RuntimeTelemetryAgentScope(
            agent_id="agent-1",
            ai_system_id="system-1",
            initiative_id="initiative-1",
            agent_owner_id="agent-owner",
            ai_system_owner_id="system-owner",
        )


class Store:
    def __init__(self) -> None:
        self.records: dict[str, RuntimeTelemetryRecord] = {}

    async def get(self, event_id: str):
        return self.records.get(event_id)

    async def save(self, record: RuntimeTelemetryRecord):
        self.records[record.event_id] = record
        return record

    async def list_for_agent(self, agent_id: str, *, limit: int):
        return [record for record in self.records.values() if record.agent_id == agent_id][:limit]


class Audit:
    def __init__(self) -> None:
        self.count = 0

    async def append(self, record: RuntimeTelemetryRecord) -> None:
        self.count += 1


class Transaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def command() -> RuntimeTelemetryCommand:
    return RuntimeTelemetryCommand(
        source_schema_version=1,
        event_id="11111111-1111-4111-8111-111111111111",
        observed_at=NOW,
        event_name="a2a.client.send_message.completed",
        event_outcome=RuntimeTelemetryOutcome.SUCCESS,
        service="decisao-agent",
        environment="local",
        version="0.1.0",
        trace_id="a" * 32,
        span_id="b" * 16,
        operation="send_message",
    )


def test_ingestion_is_idempotent_but_rejects_event_id_rebinding() -> None:
    async def scenario() -> None:
        store = Store()
        audit = Audit()
        transaction = Transaction()
        use_case = IngestRuntimeTelemetry(
            ScopeReader(), store, audit, transaction, clock=lambda: NOW
        )

        first = await use_case.execute(agent_id="agent-1", command=command())
        second = await use_case.execute(agent_id="agent-1", command=command())
        assert first == second
        assert audit.count == 1
        assert transaction.commits == 1

        divergent = replace(command(), service="other-service")
        with pytest.raises(ApplicationError, match="different evidence"):
            await use_case.execute(agent_id="agent-1", command=divergent)

    asyncio.run(scenario())


def test_listing_enforces_agent_ownership() -> None:
    async def scenario() -> None:
        store = Store()
        ingestion = IngestRuntimeTelemetry(
            ScopeReader(), store, Audit(), Transaction(), clock=lambda: NOW
        )
        await ingestion.execute(agent_id="agent-1", command=command())
        query = ListRuntimeTelemetryEvents(ScopeReader(), store)

        owner = Principal(user_id="agent-owner", approval_areas=frozenset(), is_admin=False)
        records = await query.execute(agent_id="agent-1", principal=owner)
        assert len(records) == 1

        outsider = Principal(user_id="outsider", approval_areas=frozenset(), is_admin=False)
        with pytest.raises(ApplicationError, match="Only the system owner"):
            await query.execute(agent_id="agent-1", principal=outsider)

    asyncio.run(scenario())
