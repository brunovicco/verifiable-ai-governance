"""SQLAlchemy persistence for governed Runtime Assurance actuation requests."""

from __future__ import annotations

from datetime import UTC, datetime

from governance_schemas import RiskTier
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.application.runtime_assurance_actuation import (
    RuntimeAssuranceActuationRequestRepositoryPort,
)
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance import RuntimeAssuranceBreachReason
from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationRequestState,
    RuntimeAssuranceActuationSourceContext,
)
from ai_governance_api.domain.runtime_assurance_responses import (
    RuntimeAssuranceResponseAction,
    RuntimeAssuranceResponseContext,
    RuntimeAssuranceResponseRationale,
    derive_runtime_assurance_response_plan,
)
from ai_governance_api.models import (
    Agent,
    AISystem,
    Incident,
    RuntimeAssuranceActuationRequestEntry,
    RuntimeAssuranceEvaluationEntry,
    RuntimeAssuranceIncidentPromotionEntry,
    RuntimeAssuranceResponseRecommendationEntry,
)


class SqlAlchemyRuntimeAssuranceActuationRequestRepository(
    RuntimeAssuranceActuationRequestRepositoryPort
):
    """Read trusted lineage and persist immutable actuation-request genesis evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_context(
        self,
        recommendation_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceActuationSourceContext | None:
        """Return recommendation lineage under the AI System serialization boundary."""
        statement = (
            select(
                RuntimeAssuranceResponseRecommendationEntry,
                RuntimeAssuranceIncidentPromotionEntry,
                RuntimeAssuranceEvaluationEntry,
                Incident,
                Agent,
                AISystem,
            )
            .join(
                RuntimeAssuranceIncidentPromotionEntry,
                RuntimeAssuranceIncidentPromotionEntry.id
                == RuntimeAssuranceResponseRecommendationEntry.promotion_id,
            )
            .join(
                RuntimeAssuranceEvaluationEntry,
                RuntimeAssuranceEvaluationEntry.id
                == RuntimeAssuranceResponseRecommendationEntry.evaluation_id,
            )
            .join(
                Incident,
                Incident.id == RuntimeAssuranceResponseRecommendationEntry.incident_id,
            )
            .join(
                Agent,
                Agent.id == RuntimeAssuranceResponseRecommendationEntry.agent_id,
            )
            .join(
                AISystem,
                AISystem.id == RuntimeAssuranceResponseRecommendationEntry.ai_system_id,
            )
            .where(RuntimeAssuranceResponseRecommendationEntry.id == recommendation_id)
        )
        if for_update:
            statement = statement.with_for_update(of=AISystem)

        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        recommendation, promotion, evaluation, incident, agent, ai_system = row

        if (
            recommendation.promotion_id != promotion.id
            or recommendation.evaluation_id != evaluation.id
            or recommendation.agent_id != agent.id
            or recommendation.ai_system_id != ai_system.id
            or recommendation.incident_id != incident.id
            or promotion.evaluation_id != evaluation.id
            or promotion.agent_id != agent.id
            or promotion.ai_system_id != ai_system.id
            or promotion.incident_id != incident.id
            or promotion.evidence_digest != evaluation.evidence_digest
            or recommendation.source_evidence_digest != evaluation.evidence_digest
            or recommendation.breach_fingerprint != promotion.breach_fingerprint
            or agent.ai_system_id != ai_system.id
            or incident.ai_system_id != ai_system.id
            or recommendation.advisory_only is not True
            or len(recommendation.recommendation_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in recommendation.recommendation_digest
            )
        ):
            raise ValueError("Runtime Assurance actuation source binding is inconsistent")

        try:
            actions = tuple(
                RuntimeAssuranceResponseAction(value) for value in recommendation.actions
            )
            rationale_codes = tuple(
                RuntimeAssuranceResponseRationale(value) for value in recommendation.rationale_codes
            )
            recommendation_context = RuntimeAssuranceResponseContext(
                promotion_id=recommendation.promotion_id,
                evaluation_id=recommendation.evaluation_id,
                agent_id=recommendation.agent_id,
                ai_system_id=recommendation.ai_system_id,
                incident_id=recommendation.incident_id,
                breach_fingerprint=recommendation.breach_fingerprint,
                source_evidence_digest=recommendation.source_evidence_digest,
                breach_reasons=tuple(
                    RuntimeAssuranceBreachReason(value) for value in evaluation.breach_reasons
                ),
                incident_status=IncidentStatus(recommendation.incident_status),
                incident_severity=RiskTier(recommendation.incident_severity),
                incident_version=recommendation.incident_version,
                ai_system_owner_id=ai_system.owner_id,
                kill_switch_enabled=recommendation.kill_switch_enabled,
                kill_switch_engaged=recommendation.kill_switch_engaged,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Runtime Assurance recommendation evidence is invalid") from exc

        expected_plan = derive_runtime_assurance_response_plan(recommendation_context)
        if (
            recommendation.policy_id != expected_plan.policy_id
            or recommendation.policy_version != expected_plan.policy_version
            or recommendation.policy_digest != expected_plan.policy_digest
            or recommendation.recommendation_digest != expected_plan.recommendation_digest
            or actions != expected_plan.actions
            or rationale_codes != expected_plan.rationale_codes
        ):
            raise ValueError("Runtime Assurance recommendation digest is inconsistent")

        return RuntimeAssuranceActuationSourceContext(
            recommendation_id=recommendation.id,
            recommendation_digest=recommendation.recommendation_digest,
            promotion_id=promotion.id,
            evaluation_id=evaluation.id,
            incident_id=incident.id,
            agent_id=agent.id,
            ai_system_id=ai_system.id,
            ai_system_owner_id=ai_system.owner_id,
            advisory_only=recommendation.advisory_only,
            recommendation_actions=actions,
            current_incident_status=incident.status,
        )

    async def get_request_by_recommendation_action(
        self,
        recommendation_id: str,
        action: RuntimeAssuranceActuationAction,
    ) -> RuntimeAssuranceActuationRequest | None:
        """Return one idempotent immutable request by its natural key."""
        entity = await self._session.scalar(
            select(RuntimeAssuranceActuationRequestEntry).where(
                RuntimeAssuranceActuationRequestEntry.recommendation_id == recommendation_id,
                RuntimeAssuranceActuationRequestEntry.action == action.value,
            )
        )
        return _to_domain(entity) if entity is not None else None

    async def save_request(
        self,
        request: RuntimeAssuranceActuationRequest,
    ) -> RuntimeAssuranceActuationRequest:
        """Persist one append-only request without committing."""
        self._session.add(
            RuntimeAssuranceActuationRequestEntry(
                id=request.id,
                schema_version=request.schema_version,
                recommendation_id=request.recommendation_id,
                recommendation_digest=request.recommendation_digest,
                promotion_id=request.promotion_id,
                evaluation_id=request.evaluation_id,
                incident_id=request.incident_id,
                agent_id=request.agent_id,
                ai_system_id=request.ai_system_id,
                action=request.action.value,
                state=request.state.value,
                requested_by=request.requested_by,
                requested_at=request.requested_at,
                request_digest=request.request_digest,
                version=request.version,
            )
        )
        await self._session.flush()
        return request


def _to_domain(entity: RuntimeAssuranceActuationRequestEntry) -> RuntimeAssuranceActuationRequest:
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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
