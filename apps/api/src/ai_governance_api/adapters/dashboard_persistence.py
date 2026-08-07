"""SQLAlchemy adapter aggregating governance facts for the portfolio dashboard."""

from collections import defaultdict
from datetime import UTC, datetime

from governance_schemas import EntityStatus, RiskTier
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.application.dashboard import (
    AssessmentCoverageRow,
    AssetReviewRow,
    CycleTimeSamples,
    ExceptionRow,
    IncidentCounts,
    RoutingOutcomeCounts,
)
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.model_routing import RoutingBlockCode, RoutingEnforcementOutcome
from ai_governance_api.models import (
    Agent,
    AISystem,
    Assessment,
    Incident,
    Initiative,
    ModelAsset,
    ModelRoutingDecisionEntry,
    PolicyException,
    ReviewSubmission,
)

_TOP_BLOCKED_REASON_LIMIT = 5


class SqlAlchemyDashboardStore:
    """Read raw governance facts across systems, incidents, and exceptions."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the store with the request-scoped database session."""
        self._session = session

    async def get_routing_outcome_counts(self) -> RoutingOutcomeCounts:
        """Return aggregated routing-decision outcome counts and top block reasons."""
        outcome_rows = await self._session.execute(
            select(ModelRoutingDecisionEntry.outcome, func.count()).group_by(
                ModelRoutingDecisionEntry.outcome
            )
        )
        outcome_counts = {outcome: count for outcome, count in outcome_rows}

        reason_rows = await self._session.execute(
            select(ModelRoutingDecisionEntry.reason_code, func.count())
            .where(ModelRoutingDecisionEntry.outcome == RoutingEnforcementOutcome.BLOCKED.value)
            .group_by(ModelRoutingDecisionEntry.reason_code)
            .order_by(func.count().desc())
            .limit(_TOP_BLOCKED_REASON_LIMIT)
        )
        top_blocked_reason_codes = tuple(
            (reason_code, count) for reason_code, count in reason_rows if reason_code is not None
        )
        cost_limit_exceeded = next(
            (
                count
                for reason_code, count in top_blocked_reason_codes
                if reason_code == RoutingBlockCode.COST_LIMIT_EXCEEDED.value
            ),
            0,
        )

        return RoutingOutcomeCounts(
            allowed=outcome_counts.get(RoutingEnforcementOutcome.ALLOWED.value, 0),
            blocked=outcome_counts.get(RoutingEnforcementOutcome.BLOCKED.value, 0),
            dependency_unavailable=outcome_counts.get(
                RoutingEnforcementOutcome.DEPENDENCY_UNAVAILABLE.value, 0
            ),
            top_blocked_reason_codes=top_blocked_reason_codes,
            cost_limit_exceeded=cost_limit_exceeded,
        )

    async def list_asset_review_rows(self) -> list[AssetReviewRow]:
        """Return review facts for every model and agent, joined to their system."""
        model_rows = await self._session.execute(
            select(
                AISystem.risk_tier,
                ModelAsset.approved_scope_digest,
                ModelAsset.next_review_at,
            ).join(AISystem, ModelAsset.ai_system_id == AISystem.id)
        )
        agent_rows = await self._session.execute(
            select(
                AISystem.risk_tier,
                Agent.approved_scope_digest,
                Agent.next_review_at,
            ).join(AISystem, Agent.ai_system_id == AISystem.id)
        )
        return [
            AssetReviewRow(
                risk_tier=risk_tier,
                approved_scope_digest=digest,
                next_review_at=_optional_utc(next_review_at),
            )
            for risk_tier, digest, next_review_at in (*model_rows, *agent_rows)
        ]

    async def get_incident_counts(self, *, now: datetime) -> IncidentCounts:
        """Return incident counts by status and how many miss their remediation deadline."""
        status_rows = await self._session.execute(
            select(Incident.status, func.count()).group_by(Incident.status)
        )
        status_counts = {status: count for status, count in status_rows}

        open_rows = await self._session.execute(
            select(Incident.remediation_due_at).where(Incident.status != IncidentStatus.CLOSED)
        )
        overdue_remediation = sum(
            1 for (due_at,) in open_rows.tuples() if due_at is not None and _as_utc(due_at) < now
        )

        return IncidentCounts(
            open=status_counts.get(IncidentStatus.OPEN, 0),
            contained=status_counts.get(IncidentStatus.CONTAINED, 0),
            remediating=status_counts.get(IncidentStatus.REMEDIATING, 0),
            closed=status_counts.get(IncidentStatus.CLOSED, 0),
            overdue_remediation=overdue_remediation,
        )

    async def list_exception_rows(self) -> list[ExceptionRow]:
        """Return status and expiry facts for every policy exception."""
        rows = await self._session.execute(
            select(PolicyException.status, PolicyException.expires_at)
        )
        return [
            ExceptionRow(status=status, expires_at=_as_utc(expires_at))
            for status, expires_at in rows
        ]

    async def list_residual_risk_values(self) -> list[RiskTier]:
        """Return one residual-risk tier per submitted structured assessment."""
        rows = await self._session.execute(
            select(Assessment.risk_tier).where(
                Assessment.status != EntityStatus.DRAFT,
                Assessment.risk_tier.is_not(None),
            )
        )
        return [tier for (tier,) in rows if tier is not None]

    async def list_assessment_coverage_rows(self) -> list[AssessmentCoverageRow]:
        """Return required documents and submitted kinds for every triaged initiative."""
        initiative_rows = await self._session.execute(
            select(Initiative.id, Initiative.required_documents).where(
                Initiative.status != EntityStatus.DRAFT
            )
        )
        required_by_initiative = {
            initiative_id: tuple(documents) for initiative_id, documents in initiative_rows
        }

        submitted_rows = await self._session.execute(
            select(Assessment.initiative_id, Assessment.assessment_type).where(
                Assessment.status != EntityStatus.DRAFT
            )
        )
        submitted_by_initiative: dict[str, set[str]] = defaultdict(set)
        for initiative_id, assessment_type in submitted_rows:
            submitted_by_initiative[initiative_id].add(assessment_type)

        return [
            AssessmentCoverageRow(
                required_documents=required_documents,
                submitted_kinds=frozenset(submitted_by_initiative.get(initiative_id, set())),
            )
            for initiative_id, required_documents in required_by_initiative.items()
        ]

    async def list_cycle_time_samples(self) -> CycleTimeSamples:
        """Return raw observed review-round and incident-remediation durations."""
        review_rows = await self._session.execute(
            select(ReviewSubmission.submitted_at, ReviewSubmission.resolved_at).where(
                ReviewSubmission.resolved_at.is_not(None)
            )
        )
        review_round_hours = tuple(
            _hours_between(_as_utc(submitted_at), _as_utc(resolved_at))
            for submitted_at, resolved_at in review_rows
            if resolved_at is not None
        )

        incident_rows = await self._session.execute(
            select(Incident.detected_at, Incident.resolved_at).where(
                Incident.resolved_at.is_not(None)
            )
        )
        incident_remediation_hours = tuple(
            _hours_between(_as_utc(detected_at), _as_utc(resolved_at))
            for detected_at, resolved_at in incident_rows
            if resolved_at is not None
        )

        return CycleTimeSamples(
            review_round_hours=review_round_hours,
            incident_remediation_hours=incident_remediation_hours,
        )


def _optional_utc(value: datetime | None) -> datetime | None:
    """Normalize an optional database timestamp to UTC."""
    return _as_utc(value) if value is not None else None


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive and PostgreSQL-aware timestamps to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _hours_between(start: datetime, end: datetime) -> float:
    """Return the elapsed time between two UTC timestamps, in hours."""
    return (end - start).total_seconds() / 3600
