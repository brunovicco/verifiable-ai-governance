"""SQLAlchemy adapters for incident, kill-switch, and policy-exception governance."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.audit import append_audit_event
from ai_governance_api.domain.incidents import (
    AgentKillSwitchState,
    IncidentRecord,
    IncidentSystemContext,
    PolicyExceptionRecord,
)
from ai_governance_api.models import Agent, AISystem, Incident, PolicyException


class SqlAlchemyIncidentRepository:
    """Read and mutate incident aggregates through a request-scoped session."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with the application session."""
        self._session = session

    async def get_system_context(self, ai_system_id: str) -> IncidentSystemContext | None:
        """Return AI system ownership facts without locking."""
        ai_system = await self._session.get(AISystem, ai_system_id)
        return _system_context(ai_system) if ai_system is not None else None

    async def get_system_context_for_update(
        self, ai_system_id: str
    ) -> IncidentSystemContext | None:
        """Lock the AI system row before a new incident is reported against it."""
        ai_system = await self._session.scalar(
            select(AISystem).where(AISystem.id == ai_system_id).with_for_update(of=AISystem)
        )
        return _system_context(ai_system) if ai_system is not None else None

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        """Return one incident without locking."""
        incident = await self._session.get(Incident, incident_id)
        return _to_incident_record(incident) if incident is not None else None

    async def get_incident_for_update(
        self, incident_id: str
    ) -> tuple[IncidentSystemContext, IncidentRecord] | None:
        """Lock the incident's AI system row, then return fresh incident facts."""
        ai_system = await self._session.scalar(
            select(AISystem)
            .join(Incident, Incident.ai_system_id == AISystem.id)
            .where(Incident.id == incident_id)
            .with_for_update(of=AISystem)
        )
        if ai_system is None:
            return None
        incident = await self._session.get(Incident, incident_id, populate_existing=True)
        if incident is None:
            return None
        return _system_context(ai_system), _to_incident_record(incident)

    async def save_incident(self, record: IncidentRecord) -> IncidentRecord:
        """Insert a new incident or apply changes to an existing one."""
        entity = await self._session.get(Incident, record.id)
        if entity is None:
            entity = Incident(id=record.id, **_incident_values(record), version=record.version)
            self._session.add(entity)
        else:
            if record.version != entity.version + 1:
                raise ValueError("Incident version conflict")
            for field, value in _incident_values(record).items():
                setattr(entity, field, value)
            entity.version = record.version
        await self._session.flush()
        return _to_incident_record(entity)

    async def list_incidents_for_system(self, ai_system_id: str) -> list[IncidentRecord]:
        """Return incidents for one AI system, newest first."""
        entities = await self._session.scalars(
            select(Incident)
            .where(Incident.ai_system_id == ai_system_id)
            .order_by(Incident.detected_at.desc(), Incident.id.desc())
        )
        return [_to_incident_record(entity) for entity in entities]

    async def get_agent_for_kill_switch(
        self, incident_id: str, agent_id: str
    ) -> tuple[IncidentSystemContext, IncidentRecord, AgentKillSwitchState] | None:
        """Lock the shared AI system row, then return fresh incident and agent facts."""
        ai_system = await self._session.scalar(
            select(AISystem)
            .join(Incident, Incident.ai_system_id == AISystem.id)
            .where(Incident.id == incident_id)
            .with_for_update(of=AISystem)
        )
        if ai_system is None:
            return None
        incident = await self._session.get(Incident, incident_id, populate_existing=True)
        agent = await self._session.get(Agent, agent_id, populate_existing=True)
        if incident is None or agent is None or agent.ai_system_id != ai_system.id:
            return None
        return (
            _system_context(ai_system),
            _to_incident_record(incident),
            _to_kill_switch_state(agent),
        )

    async def save_agent_kill_switch(self, state: AgentKillSwitchState) -> AgentKillSwitchState:
        """Apply a kill-switch state change to an existing agent."""
        agent = await self._session.get(Agent, state.id)
        if agent is None:
            raise ValueError("Agent not found")
        if state.version != agent.version + 1:
            raise ValueError("Agent version conflict")
        agent.kill_switch_engaged = state.kill_switch_engaged
        agent.version = state.version
        await self._session.flush()
        return _to_kill_switch_state(agent)

    async def get_exception_for_update(
        self, exception_id: str
    ) -> tuple[IncidentSystemContext, PolicyExceptionRecord] | None:
        """Lock the exception's AI system row, then return fresh exception facts."""
        ai_system = await self._session.scalar(
            select(AISystem)
            .join(Incident, Incident.ai_system_id == AISystem.id)
            .join(PolicyException, PolicyException.incident_id == Incident.id)
            .where(PolicyException.id == exception_id)
            .with_for_update(of=AISystem)
        )
        if ai_system is None:
            return None
        exception = await self._session.get(PolicyException, exception_id, populate_existing=True)
        if exception is None:
            return None
        return _system_context(ai_system), _to_exception_record(exception)

    async def save_exception(self, record: PolicyExceptionRecord) -> PolicyExceptionRecord:
        """Insert a new exception or apply changes to an existing one."""
        entity = await self._session.get(PolicyException, record.id)
        if entity is None:
            entity = PolicyException(
                id=record.id, **_exception_values(record), version=record.version
            )
            self._session.add(entity)
        else:
            if record.version != entity.version + 1:
                raise ValueError("Exception version conflict")
            for field, value in _exception_values(record).items():
                setattr(entity, field, value)
            entity.version = record.version
        await self._session.flush()
        return _to_exception_record(entity)

    async def list_exceptions_for_incident(self, incident_id: str) -> list[PolicyExceptionRecord]:
        """Return exceptions for one incident, newest first."""
        entities = await self._session.scalars(
            select(PolicyException)
            .where(PolicyException.incident_id == incident_id)
            .order_by(PolicyException.requested_at.desc(), PolicyException.id.desc())
        )
        return [_to_exception_record(entity) for entity in entities]


class SqlAlchemyIncidentAudit:
    """Append incident, kill-switch, and exception events to the shared audit chain."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with the request-scoped transaction."""
        self._session = session

    async def append(
        self,
        *,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        entity_version: int,
        payload: dict[str, object],
    ) -> None:
        """Delegate directly to the shared hash-chained audit writer."""
        await append_audit_event(
            self._session,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_version=entity_version,
            payload=payload,
        )


def _system_context(ai_system: AISystem) -> IncidentSystemContext:
    """Map an AI system row into its trusted incident-authorization facts."""
    return IncidentSystemContext(
        ai_system_id=ai_system.id,
        ai_system_owner_id=ai_system.owner_id,
    )


def _to_incident_record(incident: Incident) -> IncidentRecord:
    """Map one incident row into the pure domain projection."""
    return IncidentRecord(
        id=incident.id,
        ai_system_id=incident.ai_system_id,
        title=incident.title,
        severity=incident.severity,
        status=incident.status,
        description=incident.description,
        detected_at=_as_utc(incident.detected_at),
        owner_id=incident.owner_id,
        containment=incident.containment,
        remediation_owner_id=incident.remediation_owner_id,
        remediation_description=incident.remediation_description,
        remediation_due_at=_optional_utc(incident.remediation_due_at),
        resolved_at=_optional_utc(incident.resolved_at),
        version=incident.version,
        created_at=_as_utc(incident.created_at),
        updated_at=_as_utc(incident.updated_at),
    )


def _incident_values(record: IncidentRecord) -> dict[str, object]:
    """Map a pure incident record into persistence column values."""
    return {
        "ai_system_id": record.ai_system_id,
        "title": record.title,
        "severity": record.severity,
        "status": record.status,
        "description": record.description,
        "detected_at": record.detected_at,
        "owner_id": record.owner_id,
        "containment": record.containment,
        "remediation_owner_id": record.remediation_owner_id,
        "remediation_description": record.remediation_description,
        "remediation_due_at": record.remediation_due_at,
        "resolved_at": record.resolved_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _to_kill_switch_state(agent: Agent) -> AgentKillSwitchState:
    """Map an agent row into its pure kill-switch projection."""
    return AgentKillSwitchState(
        id=agent.id,
        ai_system_id=agent.ai_system_id,
        kill_switch_enabled=agent.kill_switch_enabled,
        kill_switch_engaged=agent.kill_switch_engaged,
        version=agent.version,
    )


def _to_exception_record(exception: PolicyException) -> PolicyExceptionRecord:
    """Map one policy-exception row into the pure domain projection."""
    return PolicyExceptionRecord(
        id=exception.id,
        incident_id=exception.incident_id,
        ai_system_id=exception.ai_system_id,
        requested_by=exception.requested_by,
        requested_at=_as_utc(exception.requested_at),
        purpose=exception.purpose,
        scope_description=exception.scope_description,
        compensating_controls=exception.compensating_controls,
        expires_at=_as_utc(exception.expires_at),
        status=exception.status,
        decided_by=exception.decided_by,
        decided_at=_optional_utc(exception.decided_at),
        decision_reason=exception.decision_reason,
        version=exception.version,
        created_at=_as_utc(exception.created_at),
        updated_at=_as_utc(exception.updated_at),
    )


def _exception_values(record: PolicyExceptionRecord) -> dict[str, object]:
    """Map a pure policy-exception record into persistence column values."""
    return {
        "incident_id": record.incident_id,
        "ai_system_id": record.ai_system_id,
        "requested_by": record.requested_by,
        "requested_at": record.requested_at,
        "purpose": record.purpose,
        "scope_description": record.scope_description,
        "compensating_controls": record.compensating_controls,
        "expires_at": record.expires_at,
        "status": record.status,
        "decided_by": record.decided_by,
        "decided_at": record.decided_at,
        "decision_reason": record.decision_reason,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _optional_utc(value: datetime | None) -> datetime | None:
    """Normalize an optional database timestamp to UTC."""
    return _as_utc(value) if value is not None else None


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive and PostgreSQL-aware timestamps to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
