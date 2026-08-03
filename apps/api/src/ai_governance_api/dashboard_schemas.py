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


class AssessmentCoverageRead(BaseModel):
    """Serialized coverage of required structured assessments across the portfolio."""

    required: int
    submitted: int
    ratio: float | None


class CycleTimesRead(BaseModel):
    """Serialized observed average cycle times and their sample sizes."""

    review_round_avg_hours: float | None
    review_round_samples: int
    incident_remediation_avg_hours: float | None
    incident_remediation_samples: int


class DashboardRead(BaseModel):
    """Serialized portfolio-wide governance monitoring snapshot."""

    generated_at: datetime
    routing_outcomes: RoutingOutcomeRead
    review_status_by_risk_tier: dict[RiskTier, dict[AssetReviewState, int]]
    incidents: IncidentCountsRead
    exceptions_by_state: dict[ExceptionState, int]
    residual_risk_by_tier: dict[RiskTier, int]
    assessment_coverage: AssessmentCoverageRead
    cycle_times: CycleTimesRead
    drift_available: bool
    control_effectiveness_available: bool

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
            residual_risk_by_tier=snapshot.residual_risk_by_tier,
            assessment_coverage=AssessmentCoverageRead(
                required=snapshot.assessment_coverage.required,
                submitted=snapshot.assessment_coverage.submitted,
                ratio=snapshot.assessment_coverage.ratio,
            ),
            cycle_times=CycleTimesRead(
                review_round_avg_hours=snapshot.cycle_times.review_round_avg_hours,
                review_round_samples=snapshot.cycle_times.review_round_samples,
                incident_remediation_avg_hours=(
                    snapshot.cycle_times.incident_remediation_avg_hours
                ),
                incident_remediation_samples=snapshot.cycle_times.incident_remediation_samples,
            ),
            drift_available=snapshot.drift_available,
            control_effectiveness_available=snapshot.control_effectiveness_available,
        )
