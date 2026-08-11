"""SQLAlchemy persistence for the governed Runtime Assurance restore workflow."""

from __future__ import annotations

from datetime import UTC, datetime

from governance_schemas import ApprovalArea
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.adapters.runtime_assurance_actuation_execution_persistence import (
    SqlAlchemyRuntimeAssuranceActuationExecutionRepository,
)
from ai_governance_api.application.runtime_assurance_restore import (
    RuntimeAssuranceRestoreRepositoryPort,
)
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import RuntimeAssuranceActuationAction
from ai_governance_api.domain.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecution,
    validate_actuation_execution_binding,
)
from ai_governance_api.domain.runtime_assurance_restore import (
    RuntimeAssuranceRestoreAction,
    RuntimeAssuranceRestoreDecision,
    RuntimeAssuranceRestoreDecisionOutcome,
    RuntimeAssuranceRestoreExecution,
    RuntimeAssuranceRestoreExecutionContext,
    RuntimeAssuranceRestoreRequest,
    RuntimeAssuranceRestoreRequestState,
    RuntimeAssuranceRestoreSourceContext,
    restore_decision_evidence_reference,
    validate_restore_decision_binding,
    validate_restore_request_binding,
)
from ai_governance_api.domain.runtime_control import (
    RuntimeControlState,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
)
from ai_governance_api.models import (
    Agent,
    AISystem,
    Incident,
    RuntimeAssuranceActuationExecutionEntry,
    RuntimeAssuranceRestoreDecisionEntry,
    RuntimeAssuranceRestoreExecutionEntry,
    RuntimeAssuranceRestoreRequestEntry,
    RuntimeControlTransitionEntry,
)


class SqlAlchemyRuntimeAssuranceRestoreRepository(RuntimeAssuranceRestoreRepositoryPort):
    """Validate source engagement and persist append-only restore evidence."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with one request-scoped session."""
        self._session = session
        self._actuation_execution_repository = (
            SqlAlchemyRuntimeAssuranceActuationExecutionRepository(session)
        )

    async def get_source_context(
        self,
        source_execution_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceRestoreSourceContext | None:
        """Return a validated engage receipt with fresh incident, Agent, and transition facts."""
        entity = await self._session.get(
            RuntimeAssuranceActuationExecutionEntry,
            source_execution_id,
            populate_existing=True,
        )
        if entity is None:
            return None
        source_execution = _actuation_execution_to_domain(entity)
        if for_update:
            ai_system = await self._session.scalar(
                select(AISystem)
                .where(AISystem.id == source_execution.ai_system_id)
                .with_for_update(of=AISystem)
            )
            if ai_system is None:
                raise ValueError("Restore AI System no longer exists")
        execution_context = await self._actuation_execution_repository.get_context(
            source_execution.decision_id
        )
        if execution_context is None:
            raise ValueError("Source actuation decision no longer exists")
        verified = await self._actuation_execution_repository.get_execution_by_decision_id(
            source_execution.decision_id
        )
        if verified is None or verified.id != source_execution_id or verified != source_execution:
            raise ValueError("Source actuation execution identity is inconsistent")
        try:
            validate_actuation_execution_binding(verified, execution_context)
        except ValueError as exc:
            raise ValueError("Source actuation execution binding is inconsistent") from exc

        agent = await self._session.get(Agent, source_execution.agent_id, populate_existing=True)
        incident = await self._session.get(
            Incident,
            source_execution.incident_id,
            populate_existing=True,
        )
        if (
            agent is None
            or incident is None
            or agent.ai_system_id != source_execution.ai_system_id
            or incident.ai_system_id != source_execution.ai_system_id
        ):
            raise ValueError("Restore Agent or incident binding is inconsistent")

        latest_entity = await self._session.scalar(
            select(RuntimeControlTransitionEntry)
            .where(RuntimeControlTransitionEntry.agent_id == source_execution.agent_id)
            .order_by(RuntimeControlTransitionEntry.control_epoch.desc())
            .limit(1)
        )
        latest = _transition_to_domain(latest_entity) if latest_entity is not None else None
        return RuntimeAssuranceRestoreSourceContext(
            source_execution=source_execution,
            ai_system_owner_id=execution_context.source.ai_system_owner_id,
            agent_version=agent.version,
            kill_switch_enabled=agent.kill_switch_enabled,
            kill_switch_engaged=agent.kill_switch_engaged,
            incident_status=incident.status,
            incident_version=incident.version,
            remediation_owner_id=incident.remediation_owner_id,
            remediation_description=incident.remediation_description,
            remediation_due_at=_optional_utc(incident.remediation_due_at),
            resolved_at=_optional_utc(incident.resolved_at),
            latest_transition=latest,
        )

    async def get_request_by_execution_remediation(
        self,
        source_execution_id: str,
        remediation_digest: str,
    ) -> RuntimeAssuranceRestoreRequest | None:
        """Return the unique request for one source execution/remediation snapshot."""
        entity = await self._session.scalar(
            select(RuntimeAssuranceRestoreRequestEntry).where(
                RuntimeAssuranceRestoreRequestEntry.source_execution_id == source_execution_id,
                RuntimeAssuranceRestoreRequestEntry.remediation_digest == remediation_digest,
            )
        )
        return _request_to_domain(entity) if entity is not None else None

    async def get_request_context(
        self,
        request_id: str,
        *,
        for_update: bool = False,
    ) -> tuple[RuntimeAssuranceRestoreRequest, RuntimeAssuranceRestoreSourceContext] | None:
        """Return one immutable request and its current validated source context."""
        entity = await self._session.get(
            RuntimeAssuranceRestoreRequestEntry,
            request_id,
            populate_existing=True,
        )
        if entity is None:
            return None
        request = _request_to_domain(entity)
        source = await self.get_source_context(
            request.source_execution_id,
            for_update=for_update,
        )
        if for_update:
            locked = await self._session.scalar(
                select(RuntimeAssuranceRestoreRequestEntry)
                .where(RuntimeAssuranceRestoreRequestEntry.id == request_id)
                .with_for_update(of=RuntimeAssuranceRestoreRequestEntry)
            )
            if locked is None:
                raise ValueError("Restore request disappeared while acquiring its lock")
            request = _request_to_domain(locked)
        if source is None:
            raise ValueError("Restore source actuation execution no longer exists")
        try:
            validate_restore_request_binding(request, source.source_execution)
        except ValueError as exc:
            raise ValueError("Restore request binding is inconsistent") from exc
        return request, source

    async def save_request(
        self,
        request: RuntimeAssuranceRestoreRequest,
    ) -> RuntimeAssuranceRestoreRequest:
        """Persist immutable restore-request genesis evidence without committing."""
        self._session.add(
            RuntimeAssuranceRestoreRequestEntry(
                id=request.id,
                schema_version=request.schema_version,
                source_execution_id=request.source_execution_id,
                source_execution_digest=request.source_execution_digest,
                agent_id=request.agent_id,
                ai_system_id=request.ai_system_id,
                incident_id=request.incident_id,
                action=request.action.value,
                state=request.state.value,
                remediation_digest=request.remediation_digest,
                incident_status=request.incident_status.value,
                incident_version=request.incident_version,
                requested_by=request.requested_by,
                requested_at=request.requested_at,
                request_digest=request.request_digest,
                version=request.version,
            )
        )
        await self._session.flush()
        return request

    async def get_decision_by_request_id(
        self,
        request_id: str,
    ) -> RuntimeAssuranceRestoreDecision | None:
        """Return the unique terminal decision for one restore request."""
        entity = await self._session.scalar(
            select(RuntimeAssuranceRestoreDecisionEntry).where(
                RuntimeAssuranceRestoreDecisionEntry.request_id == request_id
            )
        )
        return _decision_to_domain(entity) if entity is not None else None

    async def get_decision_context(
        self,
        decision_id: str,
    ) -> RuntimeAssuranceRestoreExecutionContext | None:
        """Return validated restore decision lineage with fresh Runtime Control evidence."""
        entity = await self._session.get(
            RuntimeAssuranceRestoreDecisionEntry,
            decision_id,
            populate_existing=True,
        )
        if entity is None:
            return None
        decision = _decision_to_domain(entity)
        loaded = await self.get_request_context(decision.request_id)
        if loaded is None:
            raise ValueError("Restore request no longer exists")
        request, source = loaded
        try:
            validate_restore_decision_binding(decision, request)
        except ValueError as exc:
            raise ValueError("Restore decision binding is inconsistent") from exc

        matching_transition = None
        if decision.decision is RuntimeAssuranceRestoreDecisionOutcome.APPROVED:
            reference = restore_decision_evidence_reference(decision)
            transitions = list(
                (
                    await self._session.scalars(
                        select(RuntimeControlTransitionEntry)
                        .where(
                            RuntimeControlTransitionEntry.agent_id == request.agent_id,
                            RuntimeControlTransitionEntry.evidence_reference == reference,
                        )
                        .order_by(RuntimeControlTransitionEntry.control_epoch.desc())
                        .limit(2)
                    )
                ).all()
            )
            if len(transitions) > 1:
                raise ValueError("Multiple Runtime Control transitions reuse one restore decision")
            matching_transition = _transition_to_domain(transitions[0]) if transitions else None
        return RuntimeAssuranceRestoreExecutionContext(
            decision=decision,
            request=request,
            source=source,
            matching_transition=matching_transition,
        )

    async def save_decision(
        self,
        decision: RuntimeAssuranceRestoreDecision,
    ) -> RuntimeAssuranceRestoreDecision:
        """Persist one append-only terminal restore decision without committing."""
        self._session.add(
            RuntimeAssuranceRestoreDecisionEntry(
                id=decision.id,
                schema_version=decision.schema_version,
                request_id=decision.request_id,
                request_digest=decision.request_digest,
                source_execution_id=decision.source_execution_id,
                source_execution_digest=decision.source_execution_digest,
                action=decision.action.value,
                decision=decision.decision.value,
                approval_area=decision.approval_area.value,
                decided_by=decision.decided_by,
                decided_at=decision.decided_at,
                reason=decision.reason,
                decision_digest=decision.decision_digest,
                version=decision.version,
            )
        )
        await self._session.flush()
        return decision

    async def get_execution_by_decision_id(
        self,
        decision_id: str,
    ) -> RuntimeAssuranceRestoreExecution | None:
        """Return the unique immutable restore execution receipt for one decision."""
        entity = await self._session.scalar(
            select(RuntimeAssuranceRestoreExecutionEntry).where(
                RuntimeAssuranceRestoreExecutionEntry.decision_id == decision_id
            )
        )
        return _restore_execution_to_domain(entity) if entity is not None else None

    async def save_execution(
        self,
        execution: RuntimeAssuranceRestoreExecution,
    ) -> RuntimeAssuranceRestoreExecution:
        """Persist one applied restore execution receipt without committing."""
        self._session.add(
            RuntimeAssuranceRestoreExecutionEntry(
                id=execution.id,
                schema_version=execution.schema_version,
                decision_id=execution.decision_id,
                decision_digest=execution.decision_digest,
                request_id=execution.request_id,
                request_digest=execution.request_digest,
                source_execution_id=execution.source_execution_id,
                source_execution_digest=execution.source_execution_digest,
                action=execution.action.value,
                agent_id=execution.agent_id,
                ai_system_id=execution.ai_system_id,
                incident_id=execution.incident_id,
                runtime_transition_id=execution.runtime_transition_id,
                control_epoch=execution.control_epoch,
                previous_state=execution.previous_state.value,
                target_state=execution.target_state.value,
                revoked_through_agent_version=execution.revoked_through_agent_version,
                resulting_agent_version=execution.resulting_agent_version,
                executed_by=execution.executed_by,
                executed_at=execution.executed_at,
                execution_digest=execution.execution_digest,
                version=execution.version,
            )
        )
        await self._session.flush()
        return execution


def _actuation_execution_to_domain(
    entity: RuntimeAssuranceActuationExecutionEntry,
) -> RuntimeAssuranceActuationExecution:
    return RuntimeAssuranceActuationExecution(
        id=entity.id,
        schema_version=entity.schema_version,
        decision_id=entity.decision_id,
        decision_digest=entity.decision_digest,
        request_id=entity.request_id,
        request_digest=entity.request_digest,
        action=RuntimeAssuranceActuationAction(entity.action),
        agent_id=entity.agent_id,
        ai_system_id=entity.ai_system_id,
        incident_id=entity.incident_id,
        runtime_transition_id=entity.runtime_transition_id,
        control_epoch=entity.control_epoch,
        previous_state=RuntimeControlState(entity.previous_state),
        target_state=RuntimeControlState(entity.target_state),
        revoked_through_agent_version=entity.revoked_through_agent_version,
        resulting_agent_version=entity.resulting_agent_version,
        executed_by=entity.executed_by,
        executed_at=_as_utc(entity.executed_at),
        execution_digest=entity.execution_digest,
        version=entity.version,
    )


def _request_to_domain(
    entity: RuntimeAssuranceRestoreRequestEntry,
) -> RuntimeAssuranceRestoreRequest:
    return RuntimeAssuranceRestoreRequest(
        id=entity.id,
        schema_version=entity.schema_version,
        source_execution_id=entity.source_execution_id,
        source_execution_digest=entity.source_execution_digest,
        agent_id=entity.agent_id,
        ai_system_id=entity.ai_system_id,
        incident_id=entity.incident_id,
        action=RuntimeAssuranceRestoreAction(entity.action),
        state=RuntimeAssuranceRestoreRequestState(entity.state),
        remediation_digest=entity.remediation_digest,
        incident_status=IncidentStatus(entity.incident_status),
        incident_version=entity.incident_version,
        requested_by=entity.requested_by,
        requested_at=_as_utc(entity.requested_at),
        request_digest=entity.request_digest,
        version=entity.version,
    )


def _decision_to_domain(
    entity: RuntimeAssuranceRestoreDecisionEntry,
) -> RuntimeAssuranceRestoreDecision:
    return RuntimeAssuranceRestoreDecision(
        id=entity.id,
        schema_version=entity.schema_version,
        request_id=entity.request_id,
        request_digest=entity.request_digest,
        source_execution_id=entity.source_execution_id,
        source_execution_digest=entity.source_execution_digest,
        action=RuntimeAssuranceRestoreAction(entity.action),
        decision=RuntimeAssuranceRestoreDecisionOutcome(entity.decision),
        approval_area=ApprovalArea(entity.approval_area),
        decided_by=entity.decided_by,
        decided_at=_as_utc(entity.decided_at),
        reason=entity.reason,
        decision_digest=entity.decision_digest,
        version=entity.version,
    )


def _restore_execution_to_domain(
    entity: RuntimeAssuranceRestoreExecutionEntry,
) -> RuntimeAssuranceRestoreExecution:
    return RuntimeAssuranceRestoreExecution(
        id=entity.id,
        schema_version=entity.schema_version,
        decision_id=entity.decision_id,
        decision_digest=entity.decision_digest,
        request_id=entity.request_id,
        request_digest=entity.request_digest,
        source_execution_id=entity.source_execution_id,
        source_execution_digest=entity.source_execution_digest,
        action=RuntimeAssuranceRestoreAction(entity.action),
        agent_id=entity.agent_id,
        ai_system_id=entity.ai_system_id,
        incident_id=entity.incident_id,
        runtime_transition_id=entity.runtime_transition_id,
        control_epoch=entity.control_epoch,
        previous_state=RuntimeControlState(entity.previous_state),
        target_state=RuntimeControlState(entity.target_state),
        revoked_through_agent_version=entity.revoked_through_agent_version,
        resulting_agent_version=entity.resulting_agent_version,
        executed_by=entity.executed_by,
        executed_at=_as_utc(entity.executed_at),
        execution_digest=entity.execution_digest,
        version=entity.version,
    )


def _transition_to_domain(entity: RuntimeControlTransitionEntry) -> RuntimeControlTransitionRecord:
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


def _optional_utc(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
