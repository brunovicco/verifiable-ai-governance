"""Application tests for the portfolio-wide dashboard aggregation."""

from datetime import UTC, datetime, timedelta

from ai_governance_api.application.dashboard import (
    AssetReviewRow,
    BuildDashboardSnapshot,
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
    ) -> None:
        self.routing_outcomes = routing_outcomes
        self.review_rows = review_rows
        self.incident_counts = incident_counts
        self.exception_rows = exception_rows

    async def get_routing_outcome_counts(self) -> RoutingOutcomeCounts:
        return self.routing_outcomes

    async def list_asset_review_rows(self) -> list[AssetReviewRow]:
        return self.review_rows

    async def get_incident_counts(self, *, now: datetime) -> IncidentCounts:
        assert now == NOW
        return self.incident_counts

    async def list_exception_rows(self) -> list[ExceptionRow]:
        return self.exception_rows


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
