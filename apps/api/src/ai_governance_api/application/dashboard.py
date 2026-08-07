"""Portfolio-wide dashboard aggregation combining several governance data sources."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from governance_schemas import RiskTier

from ai_governance_api.domain.assessments import AssessmentKind
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
class AssessmentCoverageRow:
    """One non-draft initiative's required documents and submitted assessment kinds."""

    required_documents: tuple[str, ...]
    submitted_kinds: frozenset[str]


@dataclass(frozen=True, slots=True)
class AssessmentCoverage:
    """Aggregated coverage of structured assessments across the portfolio."""

    required: int
    submitted: int
    ratio: float | None


@dataclass(frozen=True, slots=True)
class CycleTimeSamples:
    """Raw observed durations, in hours, for review rounds and incident remediation."""

    review_round_hours: tuple[float, ...]
    incident_remediation_hours: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class CycleTimes:
    """Aggregated average cycle times and how many observations back each average."""

    review_round_avg_hours: float | None
    review_round_samples: int
    incident_remediation_avg_hours: float | None
    incident_remediation_samples: int


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    """Portfolio-wide governance monitoring snapshot."""

    generated_at: datetime
    routing_outcomes: RoutingOutcomeCounts
    review_status_by_risk_tier: dict[RiskTier, dict[AssetReviewState, int]]
    incidents: IncidentCounts
    exceptions_by_state: dict[ExceptionState, int]
    residual_risk_by_tier: dict[RiskTier, int]
    assessment_coverage: AssessmentCoverage
    cycle_times: CycleTimes
    drift_available: bool
    control_effectiveness_available: bool


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

    async def list_residual_risk_values(self) -> list[RiskTier]:
        """Return one residual-risk tier per submitted structured assessment."""
        ...

    async def list_assessment_coverage_rows(self) -> list[AssessmentCoverageRow]:
        """Return required and submitted assessment facts for every triaged initiative."""
        ...

    async def list_cycle_time_samples(self) -> CycleTimeSamples:
        """Return raw observed review-round and incident-remediation durations."""
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

        residual_risk_values = await self._store.list_residual_risk_values()
        residual_risk_by_tier: dict[RiskTier, int] = dict.fromkeys(RiskTier, 0)
        for tier in residual_risk_values:
            residual_risk_by_tier[tier] += 1

        coverage_rows = await self._store.list_assessment_coverage_rows()
        structured_kinds = frozenset(kind.value for kind in AssessmentKind)
        required_total = 0
        submitted_total = 0
        for coverage_row in coverage_rows:
            required_kinds = set(coverage_row.required_documents) & structured_kinds
            required_total += len(required_kinds)
            submitted_total += len(required_kinds & coverage_row.submitted_kinds)
        assessment_coverage = AssessmentCoverage(
            required=required_total,
            submitted=submitted_total,
            ratio=(submitted_total / required_total) if required_total else None,
        )

        cycle_time_samples = await self._store.list_cycle_time_samples()
        cycle_times = CycleTimes(
            review_round_avg_hours=_average(cycle_time_samples.review_round_hours),
            review_round_samples=len(cycle_time_samples.review_round_hours),
            incident_remediation_avg_hours=_average(cycle_time_samples.incident_remediation_hours),
            incident_remediation_samples=len(cycle_time_samples.incident_remediation_hours),
        )

        return DashboardSnapshot(
            generated_at=now,
            routing_outcomes=routing_outcomes,
            review_status_by_risk_tier=review_status,
            incidents=incidents,
            exceptions_by_state=exceptions_by_state,
            residual_risk_by_tier=residual_risk_by_tier,
            assessment_coverage=assessment_coverage,
            cycle_times=cycle_times,
            drift_available=False,
            control_effectiveness_available=False,
        )


def _average(values: tuple[float, ...]) -> float | None:
    """Return the arithmetic mean, or None when there is no observation yet."""
    return sum(values) / len(values) if values else None
