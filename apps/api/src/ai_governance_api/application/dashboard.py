"""Portfolio-wide dashboard aggregation combining several governance data sources."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from governance_schemas import RiskTier

from ai_governance_api.domain.asset_registry import AssetReviewState, asset_review_state
from ai_governance_api.domain.incidents import (
    ExceptionState,
    ExceptionStatus,
    evaluate_exception_state,
)

type Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class AssetReviewRow:
    """Minimal reviewable-asset facts needed to compute review validity."""

    risk_tier: RiskTier
    approved_scope_digest: str | None
    next_review_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExceptionRow:
    """Minimal exception facts needed to compute its current validity."""

    status: ExceptionStatus
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RoutingOutcomeCounts:
    """Aggregated routing-decision counts by outcome and top block reasons."""

    allowed: int
    blocked: int
    dependency_unavailable: int
    top_blocked_reason_codes: tuple[tuple[str, int], ...]
    cost_limit_exceeded: int


@dataclass(frozen=True, slots=True)
class IncidentCounts:
    """Aggregated incident counts by status and overdue remediation."""

    open: int
    contained: int
    remediating: int
    closed: int
    overdue_remediation: int


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    """Portfolio-wide governance monitoring snapshot."""

    generated_at: datetime
    routing_outcomes: RoutingOutcomeCounts
    review_status_by_risk_tier: dict[RiskTier, dict[AssetReviewState, int]]
    incidents: IncidentCounts
    exceptions_by_state: dict[ExceptionState, int]
    drift_available: bool


class DashboardStore(Protocol):
    """Read raw governance facts required to build the dashboard snapshot."""

    async def get_routing_outcome_counts(self) -> RoutingOutcomeCounts:
        """Return aggregated routing-decision outcome counts."""
        ...

    async def list_asset_review_rows(self) -> list[AssetReviewRow]:
        """Return every reviewable model and agent's review facts."""
        ...

    async def get_incident_counts(self, *, now: datetime) -> IncidentCounts:
        """Return aggregated incident counts, including overdue remediation."""
        ...

    async def list_exception_rows(self) -> list[ExceptionRow]:
        """Return every policy exception's status and expiry."""
        ...


class BuildDashboardSnapshot:
    """Compose a portfolio-wide monitoring snapshot from several data sources."""

    def __init__(self, store: DashboardStore, *, clock: Clock | None = None) -> None:
        """Initialize the use case with its store port and an injectable clock."""
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))

    async def execute(self) -> DashboardSnapshot:
        """Fetch raw facts and compute review/exception validity from one source."""
        now = self._clock()
        routing_outcomes = await self._store.get_routing_outcome_counts()
        review_rows = await self._store.list_asset_review_rows()
        incidents = await self._store.get_incident_counts(now=now)
        exception_rows = await self._store.list_exception_rows()

        review_status: dict[RiskTier, dict[AssetReviewState, int]] = {
            tier: dict.fromkeys(AssetReviewState, 0) for tier in RiskTier
        }
        for row in review_rows:
            state = asset_review_state(
                approved_scope_digest=row.approved_scope_digest,
                next_review_at=row.next_review_at,
                now=now,
            )
            review_status[row.risk_tier][state] += 1

        exceptions_by_state: dict[ExceptionState, int] = dict.fromkeys(ExceptionState, 0)
        for exception_row in exception_rows:
            exception_state = evaluate_exception_state(
                status=exception_row.status,
                expires_at=exception_row.expires_at,
                now=now,
            )
            exceptions_by_state[exception_state] += 1

        return DashboardSnapshot(
            generated_at=now,
            routing_outcomes=routing_outcomes,
            review_status_by_risk_tier=review_status,
            incidents=incidents,
            exceptions_by_state=exceptions_by_state,
            drift_available=False,
        )
