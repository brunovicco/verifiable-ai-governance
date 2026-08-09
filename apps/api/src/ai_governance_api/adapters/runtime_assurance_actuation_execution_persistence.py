"""SQLAlchemy persistence for governed Runtime Assurance actuation executions."""

from __future__ import annotations

from datetime import UTC, datetime

from governance_schemas import ApprovalArea
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.adapters.runtime_assurance_actuation_decision_persistence import (
    SqlAlchemyRuntimeAssuranceActuationDecisionRepository,
)
from ai_governance_api.application.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecutionRepositoryPort,
)
from ai_governance_api.domain.runtime_assurance_actuation import RuntimeAssuranceActuationAction
from ai_governance_api.domain.runtime_assurance_actuation_decisions import (
    RuntimeAssuranceActuationDecision,
    RuntimeAssuranceActuationDecisionOutcome,
    validate_actuation_decision_binding,
)
from ai_governance_api.domain.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecution,
    RuntimeAssuranceActuationExecutionContext,
    runtime_actuation_decision_evidence_reference,
)
from ai_governance_api.domain.runtime_control import (
    RuntimeControlState,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
)
from ai_governance_api.models import (
    Agent,
    RuntimeAssuranceActuationDecisionEntry,
    RuntimeAssuranceActuationExecutionEntry,
    RuntimeControlTransitionEntry,
)


class SqlAlchemyRuntimeAssuranceActuationExecutionRepository(
    RuntimeAssuranceActuationExecutionRepositoryPort
):
    """Validate the approved chain and persist immutable applied execution receipts."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with one request-scoped SQLAlchemy session."""
        self._session = session
        self._decision_repository = SqlAlchemyRuntimeAssuranceActuationDecisionRepository(session)

    async def get_context(
        self,
        decision_id: str,
    ) -> RuntimeAssuranceActuationExecutionContext | None:
        """Return approved lineage, fresh Agent facts, and matching Runtime Control evidence."""
        decision_entity = await self._session.get(
            RuntimeAssuranceActuationDecisionEntry,
            decision_id,
            populate_existing=True,
        )
        if decision_entity is None:
            return None
        decision = _decision_to_domain(decision_entity)
        decision_context = await self._decision_repository.get_context(decision.request_id)
        if decision_context is None:
            raise ValueError("Runtime Assurance actuation request no longer exists")
        try:
            validate_actuation_decision_binding(decision, decision_context)
        except ValueError as exc:
            raise ValueError(
                "Runtime Assurance actuation decision binding is inconsistent"
            ) from exc

        request = decision_context.request
        agent = await self._session.get(Agent, request.agent_id, populate_existing=True)
        if agent is None or agent.ai_system_id != request.ai_system_id:
            raise ValueError("Runtime Assurance execution Agent binding is inconsistent")

        matching_transition = None
        if decision.decision is RuntimeAssuranceActuationDecisionOutcome.APPROVED:
            evidence_reference = runtime_actuation_decision_evidence_reference(decision)
            transitions = list(
                (
                    await self._session.scalars(
                        select(RuntimeControlTransitionEntry)
                        .where(
                            RuntimeControlTransitionEntry.agent_id == request.agent_id,
                            RuntimeControlTransitionEntry.evidence_reference == evidence_reference,
                        )
                        .order_by(RuntimeControlTransitionEntry.control_epoch.desc())
                        .limit(2)
                    )
                ).all()
            )
            if len(transitions) > 1:
                raise ValueError("Multiple Runtime Control transitions reuse one decision digest")
            matching_transition = _transition_to_domain(transitions[0]) if transitions else None

        source = decision_context.source
        return RuntimeAssuranceActuationExecutionContext(
            decision=decision,
            request=request,
            source=source,
            agent_version=agent.version,
            kill_switch_enabled=agent.kill_switch_enabled,
            kill_switch_engaged=agent.kill_switch_engaged,
            incident_status=source.current_incident_status,
            matching_transition=matching_transition,
        )

    async def get_execution_by_decision_id(
        self,
        decision_id: str,
    ) -> RuntimeAssuranceActuationExecution | None:
        """Return the unique immutable execution receipt for one approved decision."""
        entity = await self._session.scalar(
            select(RuntimeAssuranceActuationExecutionEntry).where(
                RuntimeAssuranceActuationExecutionEntry.decision_id == decision_id
            )
        )
        return _execution_to_domain(entity) if entity is not None else None

    async def save_execution(
        self,
        execution: RuntimeAssuranceActuationExecution,
    ) -> RuntimeAssuranceActuationExecution:
        """Persist one applied execution receipt without committing."""
        self._session.add(
            RuntimeAssuranceActuationExecutionEntry(
                id=execution.id,
                schema_version=execution.schema_version,
                decision_id=execution.decision_id,
                decision_digest=execution.decision_digest,
                request_id=execution.request_id,
                request_digest=execution.request_digest,
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


def _decision_to_domain(
    entity: RuntimeAssuranceActuationDecisionEntry,
) -> RuntimeAssuranceActuationDecision:
    return RuntimeAssuranceActuationDecision(
        id=entity.id,
        schema_version=entity.schema_version,
        request_id=entity.request_id,
        request_digest=entity.request_digest,
        action=RuntimeAssuranceActuationAction(entity.action),
        decision=RuntimeAssuranceActuationDecisionOutcome(entity.decision),
        approval_area=ApprovalArea(entity.approval_area),
        decided_by=entity.decided_by,
        decided_at=_as_utc(entity.decided_at),
        reason=entity.reason,
        decision_digest=entity.decision_digest,
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


def _execution_to_domain(
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


def _optional_utc(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
