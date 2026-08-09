"""SQLAlchemy persistence for governed Runtime Assurance actuation decisions."""

from __future__ import annotations

from datetime import UTC, datetime

from governance_schemas import ApprovalArea
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.adapters.runtime_assurance_actuation_persistence import (
    SqlAlchemyRuntimeAssuranceActuationRequestRepository,
)
from ai_governance_api.application.runtime_assurance_actuation_decisions import (
    RuntimeAssuranceActuationDecisionRepositoryPort,
)
from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationRequestState,
    derive_actuation_action,
    validate_actuation_request_binding,
)
from ai_governance_api.domain.runtime_assurance_actuation_decisions import (
    RuntimeAssuranceActuationDecision,
    RuntimeAssuranceActuationDecisionContext,
    RuntimeAssuranceActuationDecisionOutcome,
)
from ai_governance_api.models import (
    RuntimeAssuranceActuationDecisionEntry,
    RuntimeAssuranceActuationRequestEntry,
)


class SqlAlchemyRuntimeAssuranceActuationDecisionRepository(
    RuntimeAssuranceActuationDecisionRepositoryPort
):
    """Validate immutable request lineage and persist one terminal human decision."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with one shared transaction-scoped session."""
        self._session = session
        self._request_repository = SqlAlchemyRuntimeAssuranceActuationRequestRepository(session)

    async def get_context(
        self,
        request_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceActuationDecisionContext | None:
        """Load and validate one request, locking its genesis row when requested."""
        statement = select(RuntimeAssuranceActuationRequestEntry).where(
            RuntimeAssuranceActuationRequestEntry.id == request_id
        )
        if for_update:
            statement = statement.with_for_update(of=RuntimeAssuranceActuationRequestEntry)
        entity = await self._session.scalar(statement)
        if entity is None:
            return None

        request = _request_to_domain(entity)
        source = await self._request_repository.get_context(request.recommendation_id)
        if source is None:
            raise ValueError("Runtime Assurance actuation recommendation no longer exists")
        try:
            action = derive_actuation_action(source)
            validate_actuation_request_binding(request, source, action)
        except ValueError as exc:
            raise ValueError("Runtime Assurance actuation request binding is inconsistent") from exc
        return RuntimeAssuranceActuationDecisionContext(
            request=request,
            source=source,
        )

    async def get_decision_by_request_id(
        self,
        request_id: str,
    ) -> RuntimeAssuranceActuationDecision | None:
        """Return one terminal decision by its unique request binding."""
        entity = await self._session.scalar(
            select(RuntimeAssuranceActuationDecisionEntry).where(
                RuntimeAssuranceActuationDecisionEntry.request_id == request_id
            )
        )
        return _decision_to_domain(entity) if entity is not None else None

    async def save_decision(
        self,
        decision: RuntimeAssuranceActuationDecision,
    ) -> RuntimeAssuranceActuationDecision:
        """Persist one append-only human decision without committing."""
        self._session.add(
            RuntimeAssuranceActuationDecisionEntry(
                id=decision.id,
                schema_version=decision.schema_version,
                request_id=decision.request_id,
                request_digest=decision.request_digest,
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


def _request_to_domain(
    entity: RuntimeAssuranceActuationRequestEntry,
) -> RuntimeAssuranceActuationRequest:
    return RuntimeAssuranceActuationRequest(
        id=entity.id,
        schema_version=entity.schema_version,
        recommendation_id=entity.recommendation_id,
        recommendation_digest=entity.recommendation_digest,
        promotion_id=entity.promotion_id,
        evaluation_id=entity.evaluation_id,
        incident_id=entity.incident_id,
        agent_id=entity.agent_id,
        ai_system_id=entity.ai_system_id,
        action=RuntimeAssuranceActuationAction(entity.action),
        state=RuntimeAssuranceActuationRequestState(entity.state),
        requested_by=entity.requested_by,
        requested_at=_as_utc(entity.requested_at),
        request_digest=entity.request_digest,
        version=entity.version,
    )


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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
