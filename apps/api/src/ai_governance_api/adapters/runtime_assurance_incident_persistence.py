"""SQLAlchemy persistence for Runtime Assurance incident promotion evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from governance_schemas import RiskTier
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.application.runtime_assurance import RuntimeAssuranceScope
from ai_governance_api.application.runtime_assurance_incidents import (
    RuntimeAssuranceIncidentPromotionRepositoryPort,
)
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance import (
    RuntimeAssuranceBreachReason,
    RuntimeAssuranceEvaluation,
    RuntimeAssuranceOutcome,
)
from ai_governance_api.domain.runtime_assurance_incidents import (
    RuntimeAssuranceIncidentDisposition,
    RuntimeAssuranceIncidentPromotion,
)
from ai_governance_api.models import (
    Agent,
    AISystem,
    Incident,
    RuntimeAssuranceEvaluationEntry,
    RuntimeAssuranceIncidentPromotionEntry,
)


class SqlAlchemyRuntimeAssuranceIncidentPromotionRepository(
    RuntimeAssuranceIncidentPromotionRepositoryPort
):
    """Persist explicit evaluation-to-incident lineage under an AI System lock."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with the request-scoped transaction."""
        self._session = session

    async def get_evaluation(
        self,
        evaluation_id: str,
    ) -> RuntimeAssuranceEvaluation | None:
        """Return one immutable Runtime Assurance evaluation."""
        entry = await self._session.get(
            RuntimeAssuranceEvaluationEntry,
            evaluation_id,
        )
        return _evaluation_to_domain(entry) if entry is not None else None

    async def get_scope(
        self,
        agent_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceScope | None:
        """Return trusted scope, locking the AI System only for promotion writes."""
        statement = (
            select(Agent, AISystem)
            .join(AISystem, Agent.ai_system_id == AISystem.id)
            .where(Agent.id == agent_id)
        )
        if for_update:
            statement = statement.with_for_update(of=AISystem)
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        agent, system = row
        return RuntimeAssuranceScope(
            agent_id=agent.id,
            ai_system_id=system.id,
            initiative_id=system.initiative_id,
            agent_owner_id=agent.owner_id,
            ai_system_owner_id=system.owner_id,
        )

    async def get_promotion_by_evaluation(
        self,
        evaluation_id: str,
    ) -> RuntimeAssuranceIncidentPromotion | None:
        """Return the immutable promotion binding for one evaluation."""
        entry = await self._session.scalar(
            select(RuntimeAssuranceIncidentPromotionEntry).where(
                RuntimeAssuranceIncidentPromotionEntry.evaluation_id == evaluation_id
            )
        )
        return _promotion_to_domain(entry) if entry is not None else None

    async def list_active_incident_ids_for_fingerprint(
        self,
        *,
        agent_id: str,
        breach_fingerprint: str,
        limit: int,
    ) -> list[str]:
        """Return distinct active incidents previously linked to one breach family."""
        values = (
            await self._session.scalars(
                select(RuntimeAssuranceIncidentPromotionEntry.incident_id)
                .join(
                    Incident,
                    Incident.id == RuntimeAssuranceIncidentPromotionEntry.incident_id,
                )
                .where(
                    RuntimeAssuranceIncidentPromotionEntry.agent_id == agent_id,
                    RuntimeAssuranceIncidentPromotionEntry.breach_fingerprint == breach_fingerprint,
                    Incident.status.in_(
                        (
                            IncidentStatus.OPEN,
                            IncidentStatus.CONTAINED,
                            IncidentStatus.REMEDIATING,
                        )
                    ),
                )
                .distinct()
                .order_by(RuntimeAssuranceIncidentPromotionEntry.incident_id)
                .limit(limit)
            )
        ).all()
        return list(values)

    async def save_promotion(
        self,
        promotion: RuntimeAssuranceIncidentPromotion,
    ) -> RuntimeAssuranceIncidentPromotion:
        """Persist one append-only promotion binding without committing."""
        self._session.add(
            RuntimeAssuranceIncidentPromotionEntry(
                id=promotion.id,
                evaluation_id=promotion.evaluation_id,
                agent_id=promotion.agent_id,
                ai_system_id=promotion.ai_system_id,
                incident_id=promotion.incident_id,
                breach_fingerprint=promotion.breach_fingerprint,
                disposition=promotion.disposition.value,
                promoted_by=promotion.promoted_by,
                promoted_at=promotion.promoted_at,
                evidence_digest=promotion.evidence_digest,
                version=promotion.version,
            )
        )
        await self._session.flush()
        return promotion


def _evaluation_to_domain(
    entry: RuntimeAssuranceEvaluationEntry,
) -> RuntimeAssuranceEvaluation:
    return RuntimeAssuranceEvaluation(
        id=entry.id,
        agent_id=entry.agent_id,
        ai_system_id=entry.ai_system_id,
        initiative_id=entry.initiative_id,
        policy_version=entry.policy_version,
        evaluated_at=_as_utc(entry.evaluated_at),
        window_started_at=_as_utc(entry.window_started_at),
        window_ended_at=_as_utc(entry.window_ended_at),
        sample_count=entry.sample_count,
        duration_sample_count=entry.duration_sample_count,
        failure_count=entry.failure_count,
        failure_rate=entry.failure_rate,
        p95_duration_ms=entry.p95_duration_ms,
        max_consecutive_failures=entry.max_consecutive_failures,
        outcome=RuntimeAssuranceOutcome(entry.outcome),
        breach_reasons=tuple(RuntimeAssuranceBreachReason(value) for value in entry.breach_reasons),
        severity=RiskTier(entry.severity) if entry.severity is not None else None,
        source_event_ids=tuple(entry.source_event_ids),
        evidence_digest=entry.evidence_digest,
        version=entry.version,
    )


def _promotion_to_domain(
    entry: RuntimeAssuranceIncidentPromotionEntry,
) -> RuntimeAssuranceIncidentPromotion:
    return RuntimeAssuranceIncidentPromotion(
        id=entry.id,
        evaluation_id=entry.evaluation_id,
        agent_id=entry.agent_id,
        ai_system_id=entry.ai_system_id,
        incident_id=entry.incident_id,
        breach_fingerprint=entry.breach_fingerprint,
        disposition=RuntimeAssuranceIncidentDisposition(entry.disposition),
        promoted_by=entry.promoted_by,
        promoted_at=_as_utc(entry.promoted_at),
        evidence_digest=entry.evidence_digest,
        version=entry.version,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
