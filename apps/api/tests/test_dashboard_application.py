"""Application tests for the portfolio-wide dashboard aggregation."""

from datetime import UTC, datetime, timedelta

from ai_governance_api.application.dashboard import (
    AssessmentCoverageRow,
    AssetReviewRow,
    BuildDashboardSnapshot,
    CycleTimeSamples,
    ExceptionRow,
    IncidentCounts,
    RoutingOutcomeCounts,
)
from ai_governance_api.domain.asset_registry import AssetReviewState
from ai_governance_api.domain.incidents import ExceptionState, ExceptionStatus
from governance_schemas import RiskTier

NOW = datetime(2026, 8, 2, 15, 0, tzinfo=UTC)


class FakeStore:
    """Return configured raw rows without touching a database."""

    def __init__(
        self,
        *,
        routing_outcomes: RoutingOutcomeCounts,
        review_rows: list[AssetReviewRow],
        incident_counts: IncidentCounts,
        exception_rows: list[ExceptionRow],
        residual_risk_values: list[RiskTier] | None = None,
        coverage_rows: list[AssessmentCoverageRow] | None = None,
        cycle_time_samples: CycleTimeSamples | None = None,
    ) -> None:
        self.routing_outcomes = routing_outcomes
        self.review_rows = review_rows
        self.incident_counts = incident_counts
        self.exception_rows = exception_rows
        self.residual_risk_values = residual_risk_values or []
        self.coverage_rows = coverage_rows or []
        self.cycle_time_samples = cycle_time_samples or CycleTimeSamples(
            review_round_hours=(), incident_remediation_hours=()
        )

    async def get_routing_outcome_counts(self) -> RoutingOutcomeCounts:
        return self.routing_outcomes

    async def list_asset_review_rows(self) -> list[AssetReviewRow]:
        return self.review_rows

    async def get_incident_counts(self, *, now: datetime) -> IncidentCounts:
        assert now == NOW
        return self.incident_counts

    async def list_exception_rows(self) -> list[ExceptionRow]:
        return self.exception_rows

    async def list_residual_risk_values(self) -> list[RiskTier]:
        return self.residual_risk_values

    async def list_assessment_coverage_rows(self) -> list[AssessmentCoverageRow]:
        return self.coverage_rows

    async def list_cycle_time_samples(self) -> CycleTimeSamples:
        return self.cycle_time_samples


def routing_outcomes() -> RoutingOutcomeCounts:
    return RoutingOutcomeCounts(
        allowed=10,
        blocked=3,
        dependency_unavailable=1,
        top_blocked_reason_codes=(("cost_limit_exceeded", 2), ("router_rejected", 1)),
        cost_limit_exceeded=2,
    )


def incident_counts() -> IncidentCounts:
    return IncidentCounts(open=1, contained=1, remediating=1, closed=2, overdue_remediation=1)


async def test_review_status_is_computed_from_the_shared_domain_function() -> None:
    store = FakeStore(
        routing_outcomes=routing_outcomes(),
        review_rows=[
            AssetReviewRow(
                risk_tier=RiskTier.HIGH,
                approved_scope_digest="a" * 64,
                next_review_at=NOW + timedelta(days=1),
            ),
            AssetReviewRow(
                risk_tier=RiskTier.HIGH,
                approved_scope_digest="b" * 64,
                next_review_at=NOW - timedelta(days=1),
            ),
            AssetReviewRow(risk_tier=RiskTier.LOW, approved_scope_digest=None, next_review_at=None),
        ],
        incident_counts=incident_counts(),
        exception_rows=[],
    )
    use_case = BuildDashboardSnapshot(store, clock=lambda: NOW)

    snapshot = await use_case.execute()

    assert snapshot.review_status_by_risk_tier[RiskTier.HIGH][AssetReviewState.CURRENT] == 1
    assert snapshot.review_status_by_risk_tier[RiskTier.HIGH][AssetReviewState.EXPIRED] == 1
    assert snapshot.review_status_by_risk_tier[RiskTier.LOW][AssetReviewState.NOT_REVIEWED] == 1
    assert snapshot.review_status_by_risk_tier[RiskTier.MEDIUM][AssetReviewState.CURRENT] == 0


async def test_exception_state_is_computed_from_the_shared_domain_function() -> None:
    store = FakeStore(
        routing_outcomes=routing_outcomes(),
        review_rows=[],
        incident_counts=incident_counts(),
        exception_rows=[
            ExceptionRow(status=ExceptionStatus.PENDING, expires_at=NOW + timedelta(days=1)),
            ExceptionRow(status=ExceptionStatus.APPROVED, expires_at=NOW + timedelta(days=1)),
            ExceptionRow(status=ExceptionStatus.APPROVED, expires_at=NOW - timedelta(days=1)),
            ExceptionRow(status=ExceptionStatus.REVOKED, expires_at=NOW + timedelta(days=1)),
        ],
    )
    use_case = BuildDashboardSnapshot(store, clock=lambda: NOW)

    snapshot = await use_case.execute()

    assert snapshot.exceptions_by_state[ExceptionState.PENDING] == 1
    assert snapshot.exceptions_by_state[ExceptionState.ACTIVE] == 1
    assert snapshot.exceptions_by_state[ExceptionState.EXPIRED] == 1
    assert snapshot.exceptions_by_state[ExceptionState.REVOKED] == 1
    assert snapshot.exceptions_by_state[ExceptionState.REJECTED] == 0


async def test_routing_and_incident_counts_pass_through_and_drift_is_unavailable() -> None:
    store = FakeStore(
        routing_outcomes=routing_outcomes(),
        review_rows=[],
        incident_counts=incident_counts(),
        exception_rows=[],
    )
    use_case = BuildDashboardSnapshot(store, clock=lambda: NOW)

    snapshot = await use_case.execute()

    assert snapshot.generated_at == NOW
    assert snapshot.routing_outcomes == routing_outcomes()
    assert snapshot.incidents == incident_counts()
    assert snapshot.drift_available is False
    assert snapshot.control_effectiveness_available is False


async def test_residual_risk_is_aggregated_by_tier() -> None:
    store = FakeStore(
        routing_outcomes=routing_outcomes(),
        review_rows=[],
        incident_counts=incident_counts(),
        exception_rows=[],
        residual_risk_values=[RiskTier.HIGH, RiskTier.HIGH, RiskTier.LOW],
    )
    use_case = BuildDashboardSnapshot(store, clock=lambda: NOW)

    snapshot = await use_case.execute()

    assert snapshot.residual_risk_by_tier[RiskTier.HIGH] == 2
    assert snapshot.residual_risk_by_tier[RiskTier.LOW] == 1
    assert snapshot.residual_risk_by_tier[RiskTier.MEDIUM] == 0


async def test_assessment_coverage_counts_only_structured_assessment_kinds() -> None:
    store = FakeStore(
        routing_outcomes=routing_outcomes(),
        review_rows=[],
        incident_counts=incident_counts(),
        exception_rows=[],
        coverage_rows=[
            AssessmentCoverageRow(
                required_documents=("ai-impact-assessment", "ripd", "ai-system-card"),
                submitted_kinds=frozenset({"ai-impact-assessment"}),
            ),
            AssessmentCoverageRow(
                required_documents=("ripd",),
                submitted_kinds=frozenset({"ripd"}),
            ),
        ],
    )
    use_case = BuildDashboardSnapshot(store, clock=lambda: NOW)

    snapshot = await use_case.execute()

    # "ai-system-card" is evidence-based, not a structured assessment kind, so it's
    # excluded from both the required and submitted counts.
    assert snapshot.assessment_coverage.required == 3
    assert snapshot.assessment_coverage.submitted == 2
    assert snapshot.assessment_coverage.ratio == 2 / 3


async def test_assessment_coverage_ratio_is_none_without_any_requirement() -> None:
    store = FakeStore(
        routing_outcomes=routing_outcomes(),
        review_rows=[],
        incident_counts=incident_counts(),
        exception_rows=[],
        coverage_rows=[],
    )
    use_case = BuildDashboardSnapshot(store, clock=lambda: NOW)

    snapshot = await use_case.execute()

    assert snapshot.assessment_coverage.required == 0
    assert snapshot.assessment_coverage.ratio is None


async def test_cycle_times_average_samples_and_report_none_when_empty() -> None:
    store = FakeStore(
        routing_outcomes=routing_outcomes(),
        review_rows=[],
        incident_counts=incident_counts(),
        exception_rows=[],
        cycle_time_samples=CycleTimeSamples(
            review_round_hours=(10.0, 20.0),
            incident_remediation_hours=(),
        ),
    )
    use_case = BuildDashboardSnapshot(store, clock=lambda: NOW)

    snapshot = await use_case.execute()

    assert snapshot.cycle_times.review_round_avg_hours == 15.0
    assert snapshot.cycle_times.review_round_samples == 2
    assert snapshot.cycle_times.incident_remediation_avg_hours is None
    assert snapshot.cycle_times.incident_remediation_samples == 0
