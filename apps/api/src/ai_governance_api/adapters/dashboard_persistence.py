"""SQLAlchemy adapter aggregating governance facts for the portfolio dashboard."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.application.dashboard import (
    AssetReviewRow,
    ExceptionRow,
    IncidentCounts,
    RoutingOutcomeCounts,
)
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.model_routing import RoutingBlockCode, RoutingEnforcementOutcome
from ai_governance_api.models import (
    Agent,
    AISystem,
    Incident,
    ModelAsset,
    ModelRoutingDecisionEntry,
    PolicyException,
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
            select(ModelRoutingDecisionEntry.outcome, func.count())
            .group_by(ModelRoutingDecisionEntry.outcome)
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
            (count for reason_code, count in top_blocked_reason_codes
             if reason_code == RoutingBlockCode.COST_LIMIT_EXCEEDED.value),
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
            1
            for (due_at,) in open_rows.tuples()
            if due_at is not None and _as_utc(due_at) < now
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


def _optional_utc(value: datetime | None) -> datetime | None:
    """Normalize an optional database timestamp to UTC."""
    return _as_utc(value) if value is not None else None


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive and PostgreSQL-aware timestamps to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
