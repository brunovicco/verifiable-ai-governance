"""SQLAlchemy persistence for monotonic emergency runtime-control transitions."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from ai_governance_api.audit import append_audit_event
from ai_governance_api.domain.runtime_control import (
    RuntimeControlAgentContext,
    RuntimeControlDurableState,
    RuntimeControlIncidentContext,
    RuntimeControlSnapshot,
    RuntimeControlState,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
)
from ai_governance_api.models import Agent, Incident, RuntimeControlTransitionEntry


class SqlAlchemyRuntimeControlRepository:
    """Write runtime-control state through a request-scoped session."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with the caller-owned session."""
        self._session = session

    async def get_agent_for_update(
        self,
        agent_id: str,
        *,
        incident_id: str | None,
    ) -> tuple[RuntimeControlAgentContext, RuntimeControlIncidentContext | None] | None:
        """Lock one agent and optionally validate an incident in its AI system."""
        agent = await self._session.scalar(
            select(Agent)
            .where(Agent.id == agent_id)
            .options(joinedload(Agent.ai_system))
            .with_for_update(of=Agent)
        )
        if agent is None:
            return None
        incident_context: RuntimeControlIncidentContext | None = None
        if incident_id is not None:
            incident = await self._session.get(Incident, incident_id)
            if incident is None or incident.ai_system_id != agent.ai_system_id:
                return None
            incident_context = RuntimeControlIncidentContext(
                incident_id=incident.id,
                status=incident.status,
            )
        return _agent_context(agent), incident_context

    async def get_latest_transition_for_update(
        self,
        agent_id: str,
    ) -> RuntimeControlTransitionRecord | None:
        """Return the newest transition under the serialized agent command path."""
        entity = await self._session.scalar(
            select(RuntimeControlTransitionEntry)
            .where(RuntimeControlTransitionEntry.agent_id == agent_id)
            .order_by(RuntimeControlTransitionEntry.control_epoch.desc())
            .limit(1)
            .with_for_update()
        )
        return _transition_record(entity) if entity is not None else None

    async def get_transition(
        self,
        transition_id: str,
    ) -> RuntimeControlTransitionRecord | None:
        """Read one transition before entering the canonical Agent-first lock order."""
        entity = await self._session.get(RuntimeControlTransitionEntry, transition_id)
        return _transition_record(entity) if entity is not None else None

    async def get_transition_for_update(
        self,
        transition_id: str,
    ) -> RuntimeControlTransitionRecord | None:
        """Lock and return one transition after the Agent command lock is held."""
        entity = await self._session.scalar(
            select(RuntimeControlTransitionEntry)
            .where(RuntimeControlTransitionEntry.id == transition_id)
            .with_for_update()
        )
        return _transition_record(entity) if entity is not None else None

    async def save_transition(
        self,
        transition: RuntimeControlTransitionRecord,
    ) -> RuntimeControlTransitionRecord:
        """Insert one pending transition or advance it exactly once to applied."""
        entity = await self._session.get(RuntimeControlTransitionEntry, transition.id)
        values = _transition_values(transition)
        if entity is None:
            entity = RuntimeControlTransitionEntry(id=transition.id, **values)
            self._session.add(entity)
        else:
            if transition.version != entity.version + 1:
                raise ValueError("Runtime-control transition version conflict")
            for field, value in values.items():
                setattr(entity, field, value)
        await self._session.flush()
        return _transition_record(entity)

    async def apply_agent_state(
        self,
        context: RuntimeControlAgentContext,
        *,
        engaged: bool,
        actor_id: str,
        changed_at: datetime,
    ) -> RuntimeControlAgentContext:
        """Apply the effective state only if the optimistic agent version still matches."""
        agent = await self._session.get(Agent, context.agent_id, populate_existing=True)
        if agent is None:
            raise ValueError("Agent not found")
        if agent.version != context.agent_version:
            raise ValueError("Agent version conflict")
        agent.kill_switch_engaged = engaged
        agent.kill_switch_engaged_at = changed_at if engaged else None
        agent.kill_switch_engaged_by = actor_id if engaged else None
        agent.version += 1
        await self._session.flush()
        # The AI system relationship may not be loaded on this refreshed instance; preserve
        # ownership facts from the context that was already locked and trusted.
        return RuntimeControlAgentContext(
            agent_id=agent.id,
            ai_system_id=agent.ai_system_id,
            ai_system_owner_id=context.ai_system_owner_id,
            agent_owner_id=agent.owner_id,
            kill_switch_enabled=agent.kill_switch_enabled,
            kill_switch_engaged=agent.kill_switch_engaged,
            agent_version=agent.version,
        )

    async def list_pending(self, *, limit: int) -> list[RuntimeControlTransitionRecord]:
        """Return a bounded batch of pending transitions oldest first."""
        entities = await self._session.scalars(
            select(RuntimeControlTransitionEntry)
            .where(
                RuntimeControlTransitionEntry.status
                == RuntimeControlTransitionStatus.PENDING.value
            )
            .order_by(
                RuntimeControlTransitionEntry.requested_at.asc(),
                RuntimeControlTransitionEntry.id.asc(),
            )
            .limit(limit)
        )
        return [_transition_record(entity) for entity in entities]


class SqlAlchemyRuntimeControlStateReader:
    """Read durable control state using short-lived transactions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the reader with the application session factory."""
        self._session_factory = session_factory

    async def get_durable_state(self, agent_id: str) -> RuntimeControlDurableState | None:
        """Return the exact snapshot Governance expects to exist in runtime storage."""
        async with self._session_factory() as session:
            agent = await session.scalar(
                select(Agent)
                .where(Agent.id == agent_id)
                .options(joinedload(Agent.ai_system))
                .execution_options(populate_existing=True)
            )
            if agent is None:
                return None
            latest = await session.scalar(
                select(RuntimeControlTransitionEntry)
                .where(RuntimeControlTransitionEntry.agent_id == agent_id)
                .order_by(RuntimeControlTransitionEntry.control_epoch.desc())
                .limit(1)
            )
            state = (
                RuntimeControlState.ACTIVE
                if agent.kill_switch_engaged
                else RuntimeControlState.INACTIVE
            )
            if latest is None:
                snapshot = RuntimeControlSnapshot(
                    agent_id=agent.id,
                    control_epoch=0,
                    state=state,
                    revoked_through_agent_version=(
                        agent.version if agent.kill_switch_engaged else 0
                    ),
                    transition_id=None,
                )
                return RuntimeControlDurableState(
                    snapshot=snapshot,
                    pending_transition_id=None,
                    durable_consistent=True,
                )

            transition = _transition_record(latest)
            snapshot = RuntimeControlSnapshot(
                agent_id=agent.id,
                control_epoch=transition.control_epoch,
                state=state,
                revoked_through_agent_version=transition.revoked_through_agent_version,
                transition_id=transition.id,
            )
            consistent = (
                transition.status is RuntimeControlTransitionStatus.PENDING
                or transition.target_state is state
            )
            return RuntimeControlDurableState(
                snapshot=snapshot,
                pending_transition_id=(
                    transition.id
                    if transition.status is RuntimeControlTransitionStatus.PENDING
                    else None
                ),
                durable_consistent=consistent,
            )


class SqlAlchemyRuntimeControlAudit:
    """Append minimized runtime-control transitions to the shared hash chain."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with the caller-owned session."""
        self._session = session

    async def append(
        self,
        *,
        actor_id: str,
        action: str,
        transition: RuntimeControlTransitionRecord,
    ) -> None:
        """Persist structural control evidence without prompts, outputs, or credentials."""
        payload: dict[str, object] = {
            "agent_id": transition.agent_id,
            "ai_system_id": transition.ai_system_id,
            "transition_id": transition.id,
            "previous_state": transition.previous_state.value,
            "target_state": transition.target_state.value,
            "status": transition.status.value,
            "control_epoch": transition.control_epoch,
            "revoked_through_agent_version": transition.revoked_through_agent_version,
            "reason": transition.reason,
        }
        if transition.incident_id is not None:
            payload["incident_id"] = transition.incident_id
        if transition.evidence_reference is not None:
            payload["evidence_reference"] = transition.evidence_reference
        await append_audit_event(
            self._session,
            actor_id=actor_id,
            action=action,
            entity_type="runtime_control_transition",
            entity_id=transition.id,
            entity_version=transition.version,
            payload=payload,
        )


def _agent_context(agent: Agent) -> RuntimeControlAgentContext:
    return RuntimeControlAgentContext(
        agent_id=agent.id,
        ai_system_id=agent.ai_system_id,
        ai_system_owner_id=agent.ai_system.owner_id,
        agent_owner_id=agent.owner_id,
        kill_switch_enabled=agent.kill_switch_enabled,
        kill_switch_engaged=agent.kill_switch_engaged,
        agent_version=agent.version,
    )


def _transition_record(entity: RuntimeControlTransitionEntry) -> RuntimeControlTransitionRecord:
    return RuntimeControlTransitionRecord(
        id=entity.id,
        agent_id=entity.agent_id,
        ai_system_id=entity.ai_system_id,
        control_epoch=entity.control_epoch,
        previous_state=RuntimeControlState(entity.previous_state),
        target_state=RuntimeControlState(entity.target_state),
        status=RuntimeControlTransitionStatus(entity.status),
        revoked_through_agent_version=entity.revoked_through_agent_version,
        reason=entity.reason,
        requested_by=entity.requested_by,
        requested_at=_as_utc(entity.requested_at),
        applied_at=_optional_utc(entity.applied_at),
        incident_id=entity.incident_id,
        evidence_reference=entity.evidence_reference,
        version=entity.version,
    )


def _transition_values(record: RuntimeControlTransitionRecord) -> dict[str, object]:
    return {
        "agent_id": record.agent_id,
        "ai_system_id": record.ai_system_id,
        "control_epoch": record.control_epoch,
        "previous_state": record.previous_state.value,
        "target_state": record.target_state.value,
        "status": record.status.value,
        "revoked_through_agent_version": record.revoked_through_agent_version,
        "reason": record.reason,
        "requested_by": record.requested_by,
        "requested_at": record.requested_at,
        "applied_at": record.applied_at,
        "incident_id": record.incident_id,
        "evidence_reference": record.evidence_reference,
        "version": record.version,
    }


def _optional_utc(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
