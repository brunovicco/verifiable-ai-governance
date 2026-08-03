"""HTTP schema for the portfolio-wide governance dashboard."""

from datetime import datetime

from governance_schemas import RiskTier
from pydantic import BaseModel

from ai_governance_api.application.dashboard import DashboardSnapshot
from ai_governance_api.domain.asset_registry import AssetReviewState
from ai_governance_api.domain.incidents import ExceptionState


class RoutingOutcomeRead(BaseModel):
    """Serialized routing-decision outcome counts and top block reasons."""

    allowed: int
    blocked: int
    dependency_unavailable: int
    top_blocked_reason_codes: list[tuple[str, int]]
    cost_limit_exceeded: int


class IncidentCountsRead(BaseModel):
    """Serialized incident counts by status and overdue remediation."""

    open: int
    contained: int
    remediating: int
    closed: int
    overdue_remediation: int


class DashboardRead(BaseModel):
    """Serialized portfolio-wide governance monitoring snapshot."""

    generated_at: datetime
    routing_outcomes: RoutingOutcomeRead
    review_status_by_risk_tier: dict[RiskTier, dict[AssetReviewState, int]]
    incidents: IncidentCountsRead
    exceptions_by_state: dict[ExceptionState, int]
    drift_available: bool

    @classmethod
    def from_domain(cls, snapshot: DashboardSnapshot) -> "DashboardRead":
        """Map the pure dashboard snapshot into its public transport contract."""
        return cls(
            generated_at=snapshot.generated_at,
            routing_outcomes=RoutingOutcomeRead(
                allowed=snapshot.routing_outcomes.allowed,
                blocked=snapshot.routing_outcomes.blocked,
                dependency_unavailable=snapshot.routing_outcomes.dependency_unavailable,
                top_blocked_reason_codes=list(snapshot.routing_outcomes.top_blocked_reason_codes),
                cost_limit_exceeded=snapshot.routing_outcomes.cost_limit_exceeded,
            ),
            review_status_by_risk_tier=snapshot.review_status_by_risk_tier,
            incidents=IncidentCountsRead(
                open=snapshot.incidents.open,
                contained=snapshot.incidents.contained,
                remediating=snapshot.incidents.remediating,
                closed=snapshot.incidents.closed,
                overdue_remediation=snapshot.incidents.overdue_remediation,
            ),
            exceptions_by_state=snapshot.exceptions_by_state,
            drift_available=snapshot.drift_available,
        )
