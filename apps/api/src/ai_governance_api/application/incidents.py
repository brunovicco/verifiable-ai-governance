"""Incident, kill-switch, and temporary-exception use cases and their ports."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from governance_schemas import RiskTier

from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import (
    AgentKillSwitchState,
    ExceptionState,
    ExceptionStatus,
    IncidentDomainError,
    IncidentForbidden,
    IncidentRecord,
    IncidentStatus,
    IncidentSystemContext,
    PolicyExceptionRecord,
    evaluate_exception_state,
    require_remediation_plan_before_close,
    resulting_status_after_remediation_plan,
    transition_incident_status,
    validate_exception_decision,
    validate_exception_revocation,
    validate_kill_switch_engage,
    validate_kill_switch_restore,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


class IncidentRepositoryPort(Protocol):
    """Read and mutate incident, agent, and policy-exception aggregates."""

    async def get_system_context(self, ai_system_id: str) -> IncidentSystemContext | None:
        """Return AI system ownership facts without locking."""
        ...

    async def get_system_context_for_update(
        self, ai_system_id: str
    ) -> IncidentSystemContext | None:
        """Return AI system ownership facts under the aggregate-root lock."""
        ...

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        """Return one incident without locking."""
        ...

    async def get_incident_for_update(
        self, incident_id: str
    ) -> tuple[IncidentSystemContext, IncidentRecord] | None:
        """Return one incident and its system context under the aggregate-root lock."""
        ...

    async def save_incident(self, record: IncidentRecord) -> IncidentRecord:
        """Insert or update one incident without committing."""
        ...

    async def list_incidents_for_system(self, ai_system_id: str) -> list[IncidentRecord]:
        """Return incidents for one AI system in reverse chronological order."""
        ...

    async def get_agent_for_kill_switch(
        self, incident_id: str, agent_id: str
    ) -> tuple[IncidentSystemContext, IncidentRecord, AgentKillSwitchState] | None:
        """Return the incident, its system context, and the agent under lock."""
        ...

    async def save_agent_kill_switch(
        self, state: AgentKillSwitchState
    ) -> AgentKillSwitchState:
        """Persist one agent's kill-switch state without committing."""
        ...

    async def get_exception_for_update(
        self, exception_id: str
    ) -> tuple[IncidentSystemContext, PolicyExceptionRecord] | None:
        """Return one policy exception and its system context under lock."""
        ...

    async def save_exception(self, record: PolicyExceptionRecord) -> PolicyExceptionRecord:
        """Insert or update one policy exception without committing."""
        ...

    async def list_exceptions_for_incident(
        self, incident_id: str
    ) -> list[PolicyExceptionRecord]:
        """Return policy exceptions for one incident in reverse chronological order."""
        ...


class IncidentAuditPort(Protocol):
    """Append content-minimized incident lifecycle events to the audit chain."""

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
        """Append one lifecycle event in the surrounding transaction."""
        ...


class IncidentTransactionPort(Protocol):
    """Transaction boundary shared by incident, agent, and exception writes."""

    async def commit(self) -> None:
        """Commit pending evidence and audit changes atomically."""
        ...

    async def rollback(self) -> None:
        """Discard pending changes after a persistence failure."""
        ...


class IncidentService:
    """Enforce incident lifecycle, kill-switch, and exception governance rules."""

    def __init__(
        self,
        repository: IncidentRepositoryPort,
        audit: IncidentAuditPort,
        transaction: IncidentTransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize the service with explicit I/O boundaries and test seams."""
        self._repository = repository
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def report_incident(
        self,
        *,
        ai_system_id: str,
        title: str,
        severity: RiskTier,
        description: str,
        detected_at: datetime,
        principal: Principal,
    ) -> IncidentRecord:
        """Open a new incident owned by the AI system's accountable owner."""
        context = await self._repository.get_system_context_for_update(ai_system_id)
        if context is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "AI system not found")
        self._require_owner_or_admin(context, principal)
        now = self._clock()
        record = IncidentRecord(
            id=self._id_factory(),
            ai_system_id=context.ai_system_id,
            title=title,
            severity=severity,
            status=IncidentStatus.OPEN,
            description=description,
            detected_at=detected_at,
            owner_id=context.ai_system_owner_id,
            containment=None,
            remediation_owner_id=None,
            remediation_description=None,
            remediation_due_at=None,
            resolved_at=None,
            version=1,
            created_at=now,
            updated_at=now,
        )
        return await self._persist_incident(
            record,
            principal=principal,
            action="incident.reported",
            extra={"severity": severity.value},
        )

    async def contain_incident(
        self,
        *,
        incident_id: str,
        containment: str,
        expected_version: int,
        principal: Principal,
    ) -> IncidentRecord:
        """Record containment measures and move the incident to contained."""
        context, incident = await self._require_incident_for_update(incident_id)
        self._require_owner_or_admin(context, principal)
        self._require_version(incident.version, expected_version)
        self._require_domain(
            lambda: transition_incident_status(incident.status, IncidentStatus.CONTAINED)
        )
        updated = self._bump(
            incident,
            status=IncidentStatus.CONTAINED,
            containment=containment,
        )
        return await self._persist_incident(
            updated,
            principal=principal,
            action="incident.contained",
            extra={},
        )

    async def set_remediation_plan(
        self,
        *,
        incident_id: str,
        remediation_owner_id: str,
        remediation_description: str,
        remediation_due_at: datetime,
        expected_version: int,
        principal: Principal,
    ) -> IncidentRecord:
        """Record a remediation plan, moving an open or contained incident forward."""
        context, incident = await self._require_incident_for_update(incident_id)
        self._require_owner_or_admin(context, principal)
        self._require_version(incident.version, expected_version)
        new_status = self._require_domain(
            lambda: resulting_status_after_remediation_plan(incident.status)
        )
        updated = self._bump(
            incident,
            status=new_status,
            remediation_owner_id=remediation_owner_id,
            remediation_description=remediation_description,
            remediation_due_at=remediation_due_at,
        )
        return await self._persist_incident(
            updated,
            principal=principal,
            action="incident.remediation_plan_set",
            extra={"remediation_owner_id": remediation_owner_id},
        )

    async def close_incident(
        self,
        *,
        incident_id: str,
        expected_version: int,
        principal: Principal,
    ) -> IncidentRecord:
        """Close an incident once its remediation plan is on record."""
        context, incident = await self._require_incident_for_update(incident_id)
        self._require_owner_or_admin(context, principal)
        self._require_version(incident.version, expected_version)
        self._require_domain(
            lambda: transition_incident_status(incident.status, IncidentStatus.CLOSED)
        )
        self._require_domain(
            lambda: require_remediation_plan_before_close(
                remediation_owner_id=incident.remediation_owner_id,
                remediation_due_at=incident.remediation_due_at,
                remediation_description=incident.remediation_description,
            )
        )
        now = self._clock()
        updated = self._bump(incident, status=IncidentStatus.CLOSED, resolved_at=now)
        return await self._persist_incident(
            updated,
            principal=principal,
            action="incident.closed",
            extra={},
        )

    async def engage_kill_switch(
        self,
        *,
        incident_id: str,
        agent_id: str,
        expected_version: int,
        principal: Principal,
    ) -> AgentKillSwitchState:
        """Trip an agent's declared kill switch during incident response."""
        context, incident, agent = await self._require_agent_for_kill_switch(
            incident_id, agent_id
        )
        self._require_owner_or_admin(context, principal)
        self._require_version(agent.version, expected_version)
        self._require_domain(
            lambda: validate_kill_switch_engage(
                kill_switch_enabled=agent.kill_switch_enabled,
                already_engaged=agent.kill_switch_engaged,
                status=incident.status,
            )
        )
        updated = AgentKillSwitchState(
            id=agent.id,
            ai_system_id=agent.ai_system_id,
            kill_switch_enabled=agent.kill_switch_enabled,
            kill_switch_engaged=True,
            version=agent.version + 1,
        )
        return await self._persist_kill_switch(
            updated,
            principal=principal,
            action="incident.kill_switch_engaged",
            incident_id=incident_id,
        )

    async def restore_kill_switch(
        self,
        *,
        incident_id: str,
        agent_id: str,
        expected_version: int,
        principal: Principal,
    ) -> AgentKillSwitchState:
        """Restore a previously engaged kill switch."""
        context, _incident, agent = await self._require_agent_for_kill_switch(
            incident_id, agent_id
        )
        self._require_owner_or_admin(context, principal)
        self._require_version(agent.version, expected_version)
        self._require_domain(
            lambda: validate_kill_switch_restore(already_engaged=agent.kill_switch_engaged)
        )
        updated = AgentKillSwitchState(
            id=agent.id,
            ai_system_id=agent.ai_system_id,
            kill_switch_enabled=agent.kill_switch_enabled,
            kill_switch_engaged=False,
            version=agent.version + 1,
        )
        return await self._persist_kill_switch(
            updated,
            principal=principal,
            action="incident.kill_switch_restored",
            incident_id=incident_id,
        )

    async def request_exception(
        self,
        *,
        incident_id: str,
        purpose: str,
        scope_description: str,
        compensating_controls: str,
        expires_at: datetime,
        principal: Principal,
    ) -> PolicyExceptionRecord:
        """Request a temporary, expiring exception while an incident is active."""
        context, incident = await self._require_incident_for_update(incident_id)
        self._require_owner_or_admin(context, principal)
        if incident.status is IncidentStatus.CLOSED:
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Cannot request an exception on a closed incident",
            )
        now = self._clock()
        record = PolicyExceptionRecord(
            id=self._id_factory(),
            incident_id=incident.id,
            ai_system_id=context.ai_system_id,
            requested_by=principal.user_id,
            requested_at=now,
            purpose=purpose,
            scope_description=scope_description,
            compensating_controls=compensating_controls,
            expires_at=expires_at,
            status=ExceptionStatus.PENDING,
            decided_by=None,
            decided_at=None,
            decision_reason=None,
            version=1,
            created_at=now,
            updated_at=now,
        )
        return await self._persist_exception(
            record,
            principal=principal,
            action="incident.exception_requested",
        )

    async def decide_exception(
        self,
        *,
        exception_id: str,
        approved: bool,
        decision_reason: str | None,
        expected_version: int,
        principal: Principal,
    ) -> PolicyExceptionRecord:
        """Approve or reject a pending exception, enforcing segregation of duties."""
        _context, exception = await self._require_exception_for_update(exception_id)
        if not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only an administrator can decide a temporary exception",
            )
        self._require_version(exception.version, expected_version)
        self._require_domain(
            lambda: validate_exception_decision(
                requested_by=exception.requested_by,
                decided_by=principal.user_id,
                current_status=exception.status,
            )
        )
        now = self._clock()
        updated = self._bump_exception(
            exception,
            status=ExceptionStatus.APPROVED if approved else ExceptionStatus.REJECTED,
            decided_by=principal.user_id,
            decided_at=now,
            decision_reason=decision_reason,
        )
        return await self._persist_exception(
            updated,
            principal=principal,
            action="incident.exception_decided",
        )

    async def revoke_exception(
        self,
        *,
        exception_id: str,
        decision_reason: str | None,
        expected_version: int,
        principal: Principal,
    ) -> PolicyExceptionRecord:
        """Revoke a pending or approved exception ahead of its natural expiry."""
        _context, exception = await self._require_exception_for_update(exception_id)
        if not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only an administrator can revoke a temporary exception",
            )
        self._require_version(exception.version, expected_version)
        self._require_domain(
            lambda: validate_exception_revocation(current_status=exception.status)
        )
        now = self._clock()
        updated = self._bump_exception(
            exception,
            status=ExceptionStatus.REVOKED,
            decided_by=principal.user_id,
            decided_at=now,
            decision_reason=decision_reason,
        )
        return await self._persist_exception(
            updated,
            principal=principal,
            action="incident.exception_revoked",
        )

    async def list_incidents(
        self,
        *,
        ai_system_id: str,
        principal: Principal,
    ) -> list[IncidentRecord]:
        """Return incidents visible to the AI system's owner or an administrator."""
        context = await self._repository.get_system_context(ai_system_id)
        if context is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "AI system not found")
        self._require_owner_or_admin(context, principal)
        return await self._repository.list_incidents_for_system(ai_system_id)

    async def get_incident(
        self,
        *,
        incident_id: str,
        principal: Principal,
    ) -> IncidentRecord:
        """Return one incident visible to its AI system's owner or an admin."""
        incident, context = await self._require_incident_and_context(incident_id)
        self._require_owner_or_admin(context, principal)
        return incident

    async def list_exceptions(
        self,
        *,
        incident_id: str,
        principal: Principal,
    ) -> list[PolicyExceptionRecord]:
        """Return exceptions visible to the incident's system owner or an admin."""
        _incident, context = await self._require_incident_and_context(incident_id)
        self._require_owner_or_admin(context, principal)
        return await self._repository.list_exceptions_for_incident(incident_id)

    async def _require_incident_and_context(
        self, incident_id: str
    ) -> tuple[IncidentRecord, IncidentSystemContext]:
        """Return one incident and its AI system context, or raise not-found."""
        incident = await self._repository.get_incident(incident_id)
        if incident is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Incident not found")
        context = await self._repository.get_system_context(incident.ai_system_id)
        if context is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "AI system not found")
        return incident, context

    def exception_state(self, exception: PolicyExceptionRecord) -> ExceptionState:
        """Classify an exception's current validity at read time."""
        return evaluate_exception_state(
            status=exception.status,
            expires_at=exception.expires_at,
            now=self._clock(),
        )

    async def _require_incident_for_update(
        self, incident_id: str
    ) -> tuple[IncidentSystemContext, IncidentRecord]:
        """Return an incident and its system context, or raise not-found."""
        found = await self._repository.get_incident_for_update(incident_id)
        if found is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Incident not found")
        return found

    async def _require_agent_for_kill_switch(
        self, incident_id: str, agent_id: str
    ) -> tuple[IncidentSystemContext, IncidentRecord, AgentKillSwitchState]:
        """Return an incident, its system context, and one of its agents."""
        found = await self._repository.get_agent_for_kill_switch(incident_id, agent_id)
        if found is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Incident or agent not found")
        return found

    async def _require_exception_for_update(
        self, exception_id: str
    ) -> tuple[IncidentSystemContext, PolicyExceptionRecord]:
        """Return a policy exception and its system context, or raise not-found."""
        found = await self._repository.get_exception_for_update(exception_id)
        if found is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Exception not found")
        return found

    def _require_owner_or_admin(
        self, context: IncidentSystemContext, principal: Principal
    ) -> None:
        """Restrict incident commands to the AI system owner or an administrator."""
        if context.ai_system_owner_id != principal.user_id and not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the AI system owner or an administrator can manage this incident",
            )

    def _require_version(self, current: int, expected: int) -> None:
        """Enforce optimistic concurrency on the mutated aggregate."""
        if current != expected:
            raise ApplicationError(ErrorKind.CONFLICT, "Version conflict")

    def _require_domain[T](self, call: Callable[[], T]) -> T:
        """Translate a domain validation failure into a stable application error."""
        try:
            return call()
        except IncidentForbidden as exc:
            raise ApplicationError(ErrorKind.FORBIDDEN, str(exc)) from exc
        except IncidentDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc

    def _bump(self, incident: IncidentRecord, **changes: object) -> IncidentRecord:
        """Apply changes to an incident and advance its optimistic version."""
        return replace(
            incident,
            version=incident.version + 1,
            updated_at=self._clock(),
            **changes,  # type: ignore[arg-type]
        )

    def _bump_exception(
        self, exception: PolicyExceptionRecord, **changes: object
    ) -> PolicyExceptionRecord:
        """Apply changes to a policy exception and advance its optimistic version."""
        return replace(
            exception,
            version=exception.version + 1,
            updated_at=self._clock(),
            **changes,  # type: ignore[arg-type]
        )

    async def _persist_incident(
        self,
        record: IncidentRecord,
        *,
        principal: Principal,
        action: str,
        extra: dict[str, object],
    ) -> IncidentRecord:
        """Persist an incident and its audit event atomically."""
        try:
            saved = await self._repository.save_incident(record)
            await self._audit.append(
                actor_id=principal.user_id,
                action=action,
                entity_type="incident",
                entity_id=saved.id,
                entity_version=saved.version,
                payload={
                    "ai_system_id": saved.ai_system_id,
                    "status": saved.status.value,
                    **extra,
                },
            )
            await self._transaction.commit()
            return saved
        except Exception:
            await self._transaction.rollback()
            raise

    async def _persist_kill_switch(
        self,
        state: AgentKillSwitchState,
        *,
        principal: Principal,
        action: str,
        incident_id: str,
    ) -> AgentKillSwitchState:
        """Persist an agent's kill-switch state and its audit event atomically."""
        try:
            saved = await self._repository.save_agent_kill_switch(state)
            await self._audit.append(
                actor_id=principal.user_id,
                action=action,
                entity_type="agent",
                entity_id=saved.id,
                entity_version=saved.version,
                payload={
                    "incident_id": incident_id,
                    "ai_system_id": saved.ai_system_id,
                    "kill_switch_engaged": saved.kill_switch_engaged,
                },
            )
            await self._transaction.commit()
            return saved
        except Exception:
            await self._transaction.rollback()
            raise

    async def _persist_exception(
        self,
        record: PolicyExceptionRecord,
        *,
        principal: Principal,
        action: str,
    ) -> PolicyExceptionRecord:
        """Persist a policy exception and its audit event atomically."""
        try:
            saved = await self._repository.save_exception(record)
            await self._audit.append(
                actor_id=principal.user_id,
                action=action,
                entity_type="policy_exception",
                entity_id=saved.id,
                entity_version=saved.version,
                payload={
                    "incident_id": saved.incident_id,
                    "ai_system_id": saved.ai_system_id,
                    "status": saved.status.value,
                },
            )
            await self._transaction.commit()
            return saved
        except Exception:
            await self._transaction.rollback()
            raise
