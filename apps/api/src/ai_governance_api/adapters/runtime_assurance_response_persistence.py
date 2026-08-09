"""SQLAlchemy persistence for deterministic runtime-response recommendations."""

from __future__ import annotations

from datetime import UTC, datetime

from governance_schemas import RiskTier
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.application.runtime_assurance_responses import (
    RuntimeAssuranceResponseRepositoryPort,
)
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance import RuntimeAssuranceBreachReason
from ai_governance_api.domain.runtime_assurance_responses import (
    RuntimeAssuranceResponseAction,
    RuntimeAssuranceResponseContext,
    RuntimeAssuranceResponseRationale,
    RuntimeAssuranceResponseRecommendation,
)
from ai_governance_api.models import (
    Agent,
    AISystem,
    Incident,
    RuntimeAssuranceEvaluationEntry,
    RuntimeAssuranceIncidentPromotionEntry,
    RuntimeAssuranceResponseRecommendationEntry,
)


class SqlAlchemyRuntimeAssuranceResponseRepository(RuntimeAssuranceResponseRepositoryPort):
    """Read trusted source state and persist immutable recommendation evidence."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with the request-scoped transaction."""
        self._session = session

    async def get_context(
        self,
        promotion_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceResponseContext | None:
        """Return promotion/evaluation/incident/Agent facts under one system boundary."""
        statement = (
            select(
                RuntimeAssuranceIncidentPromotionEntry,
                RuntimeAssuranceEvaluationEntry,
                Incident,
                Agent,
                AISystem,
            )
            .join(
                RuntimeAssuranceEvaluationEntry,
                RuntimeAssuranceEvaluationEntry.id
                == RuntimeAssuranceIncidentPromotionEntry.evaluation_id,
            )
            .join(
                Incident,
                Incident.id == RuntimeAssuranceIncidentPromotionEntry.incident_id,
            )
            .join(
                Agent,
                Agent.id == RuntimeAssuranceIncidentPromotionEntry.agent_id,
            )
            .join(
                AISystem,
                AISystem.id == RuntimeAssuranceIncidentPromotionEntry.ai_system_id,
            )
            .where(RuntimeAssuranceIncidentPromotionEntry.id == promotion_id)
        )
        if for_update:
            statement = statement.with_for_update(of=AISystem)

        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        promotion, evaluation, incident, agent, ai_system = row
        if (
            promotion.evaluation_id != evaluation.id
            or promotion.agent_id != evaluation.agent_id
            or promotion.ai_system_id != evaluation.ai_system_id
            or promotion.incident_id != incident.id
            or agent.ai_system_id != ai_system.id
            or incident.ai_system_id != ai_system.id
            or promotion.evidence_digest != evaluation.evidence_digest
        ):
            raise ValueError("Runtime Assurance response source binding is inconsistent")

        return RuntimeAssuranceResponseContext(
            promotion_id=promotion.id,
            evaluation_id=evaluation.id,
            agent_id=agent.id,
            ai_system_id=ai_system.id,
            incident_id=incident.id,
            breach_fingerprint=promotion.breach_fingerprint,
            source_evidence_digest=evaluation.evidence_digest,
            breach_reasons=tuple(
                RuntimeAssuranceBreachReason(value) for value in evaluation.breach_reasons
            ),
            incident_status=incident.status,
            incident_severity=incident.severity,
            incident_version=incident.version,
            ai_system_owner_id=ai_system.owner_id,
            kill_switch_enabled=agent.kill_switch_enabled,
            kill_switch_engaged=agent.kill_switch_engaged,
        )

    async def get_recommendation_by_promotion(
        self,
        promotion_id: str,
    ) -> RuntimeAssuranceResponseRecommendation | None:
        """Return the immutable recommendation previously generated for a promotion."""
        entity = await self._session.scalar(
            select(RuntimeAssuranceResponseRecommendationEntry).where(
                RuntimeAssuranceResponseRecommendationEntry.promotion_id == promotion_id
            )
        )
        return _to_domain(entity) if entity is not None else None

    async def save_recommendation(
        self,
        recommendation: RuntimeAssuranceResponseRecommendation,
    ) -> RuntimeAssuranceResponseRecommendation:
        """Persist one append-only recommendation without committing."""
        self._session.add(
            RuntimeAssuranceResponseRecommendationEntry(
                id=recommendation.id,
                promotion_id=recommendation.promotion_id,
                evaluation_id=recommendation.evaluation_id,
                agent_id=recommendation.agent_id,
                ai_system_id=recommendation.ai_system_id,
                incident_id=recommendation.incident_id,
                breach_fingerprint=recommendation.breach_fingerprint,
                source_evidence_digest=recommendation.source_evidence_digest,
                policy_id=recommendation.policy_id,
                policy_version=recommendation.policy_version,
                policy_digest=recommendation.policy_digest,
                incident_status=recommendation.incident_status.value,
                incident_severity=recommendation.incident_severity.value,
                incident_version=recommendation.incident_version,
                kill_switch_enabled=recommendation.kill_switch_enabled,
                kill_switch_engaged=recommendation.kill_switch_engaged,
                actions=[action.value for action in recommendation.actions],
                rationale_codes=[rationale.value for rationale in recommendation.rationale_codes],
                advisory_only=recommendation.advisory_only,
                generated_by=recommendation.generated_by,
                generated_at=recommendation.generated_at,
                recommendation_digest=recommendation.recommendation_digest,
                version=recommendation.version,
            )
        )
        await self._session.flush()
        return recommendation


def _to_domain(
    entity: RuntimeAssuranceResponseRecommendationEntry,
) -> RuntimeAssuranceResponseRecommendation:
    return RuntimeAssuranceResponseRecommendation(
        id=entity.id,
        promotion_id=entity.promotion_id,
        evaluation_id=entity.evaluation_id,
        agent_id=entity.agent_id,
        ai_system_id=entity.ai_system_id,
        incident_id=entity.incident_id,
        breach_fingerprint=entity.breach_fingerprint,
        source_evidence_digest=entity.source_evidence_digest,
        policy_id=entity.policy_id,
        policy_version=entity.policy_version,
        policy_digest=entity.policy_digest,
        incident_status=IncidentStatus(entity.incident_status),
        incident_severity=RiskTier(entity.incident_severity),
        incident_version=entity.incident_version,
        kill_switch_enabled=entity.kill_switch_enabled,
        kill_switch_engaged=entity.kill_switch_engaged,
        actions=tuple(RuntimeAssuranceResponseAction(value) for value in entity.actions),
        rationale_codes=tuple(
            RuntimeAssuranceResponseRationale(value) for value in entity.rationale_codes
        ),
        advisory_only=entity.advisory_only,
        generated_by=entity.generated_by,
        generated_at=_as_utc(entity.generated_at),
        recommendation_digest=entity.recommendation_digest,
        version=entity.version,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
