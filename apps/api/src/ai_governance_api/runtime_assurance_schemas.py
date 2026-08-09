"""HTTP schemas for governed runtime-assurance policies and evidence."""

from datetime import datetime

from governance_schemas import RiskTier
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance import (
    RuntimeAssuranceBreachReason,
    RuntimeAssuranceEvaluation,
    RuntimeAssuranceOutcome,
    RuntimeAssurancePolicy,
)
from ai_governance_api.domain.runtime_assurance_incidents import (
    RuntimeAssuranceIncidentDisposition,
    RuntimeAssuranceIncidentPromotionResult,
)
from ai_governance_api.domain.runtime_assurance_responses import (
    RuntimeAssuranceResponseAction,
    RuntimeAssuranceResponseRationale,
    RuntimeAssuranceResponseRecommendation,
)


class RuntimeAssurancePolicyUpsertRequest(BaseModel):
    """Closed policy contract for one governed Agent."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    lookback_seconds: int = Field(ge=60, le=86_400)
    evaluation_sample_size: int = Field(ge=1, le=1000)
    minimum_samples: int = Field(ge=1, le=1000)
    max_failure_rate: float = Field(ge=0, le=1)
    max_p95_duration_ms: float | None = Field(default=None, gt=0, le=3_600_000)
    max_consecutive_failures: int | None = Field(default=None, ge=1, le=1000)
    breach_severity: RiskTier
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_sample_bounds(self) -> "RuntimeAssurancePolicyUpsertRequest":
        if self.minimum_samples > self.evaluation_sample_size:
            raise ValueError("minimum_samples cannot exceed evaluation_sample_size")
        if (
            self.max_consecutive_failures is not None
            and self.max_consecutive_failures > self.evaluation_sample_size
        ):
            raise ValueError("max_consecutive_failures cannot exceed evaluation_sample_size")
        return self


class RuntimeAssurancePolicyRead(BaseModel):
    """Serialized current runtime-assurance policy."""

    agent_id: str
    ai_system_id: str
    enabled: bool
    lookback_seconds: int
    evaluation_sample_size: int
    minimum_samples: int
    max_failure_rate: float
    max_p95_duration_ms: float | None
    max_consecutive_failures: int | None
    breach_severity: RiskTier
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, policy: RuntimeAssurancePolicy) -> "RuntimeAssurancePolicyRead":
        """Map the pure policy record into its public transport contract."""
        return cls(
            agent_id=policy.agent_id,
            ai_system_id=policy.ai_system_id,
            enabled=policy.enabled,
            lookback_seconds=policy.lookback_seconds,
            evaluation_sample_size=policy.evaluation_sample_size,
            minimum_samples=policy.minimum_samples,
            max_failure_rate=policy.max_failure_rate,
            max_p95_duration_ms=policy.max_p95_duration_ms,
            max_consecutive_failures=policy.max_consecutive_failures,
            breach_severity=policy.breach_severity,
            version=policy.version,
            created_at=policy.created_at,
            updated_at=policy.updated_at,
        )


class RuntimeAssuranceEvaluationRead(BaseModel):
    """Serialized append-only deterministic assurance evidence."""

    id: str
    agent_id: str
    ai_system_id: str
    initiative_id: str
    policy_version: int
    evaluated_at: datetime
    window_started_at: datetime
    window_ended_at: datetime
    sample_count: int
    duration_sample_count: int
    failure_count: int
    failure_rate: float
    p95_duration_ms: float | None
    max_consecutive_failures: int
    outcome: RuntimeAssuranceOutcome
    breach_reasons: list[RuntimeAssuranceBreachReason]
    severity: RiskTier | None
    source_event_ids: list[str]
    evidence_digest: str
    version: int

    @classmethod
    def from_domain(
        cls, evaluation: RuntimeAssuranceEvaluation
    ) -> "RuntimeAssuranceEvaluationRead":
        """Map pure deterministic assurance evidence into its public transport contract."""
        return cls(
            id=evaluation.id,
            agent_id=evaluation.agent_id,
            ai_system_id=evaluation.ai_system_id,
            initiative_id=evaluation.initiative_id,
            policy_version=evaluation.policy_version,
            evaluated_at=evaluation.evaluated_at,
            window_started_at=evaluation.window_started_at,
            window_ended_at=evaluation.window_ended_at,
            sample_count=evaluation.sample_count,
            duration_sample_count=evaluation.duration_sample_count,
            failure_count=evaluation.failure_count,
            failure_rate=evaluation.failure_rate,
            p95_duration_ms=evaluation.p95_duration_ms,
            max_consecutive_failures=evaluation.max_consecutive_failures,
            outcome=evaluation.outcome,
            breach_reasons=list(evaluation.breach_reasons),
            severity=evaluation.severity,
            source_event_ids=list(evaluation.source_event_ids),
            evidence_digest=evaluation.evidence_digest,
            version=evaluation.version,
        )


class RuntimeAssuranceIncidentPromotionRequest(BaseModel):
    """Explicit empty command that rejects arbitrary actuator fields."""

    model_config = ConfigDict(extra="forbid")


class RuntimeAssuranceIncidentPromotionRead(BaseModel):
    """Content-minimized evaluation-to-incident linkage and incident state."""

    promotion_id: str
    evaluation_id: str
    agent_id: str
    ai_system_id: str
    incident_id: str
    breach_fingerprint: str
    disposition: RuntimeAssuranceIncidentDisposition
    promoted_by: str
    promoted_at: datetime
    evidence_digest: str
    incident_status: IncidentStatus
    incident_severity: RiskTier
    incident_version: int

    @classmethod
    def from_domain(
        cls,
        result: RuntimeAssuranceIncidentPromotionResult,
    ) -> "RuntimeAssuranceIncidentPromotionRead":
        """Map pure promotion evidence into a minimized transport contract."""
        promotion = result.promotion
        incident = result.incident
        return cls(
            promotion_id=promotion.id,
            evaluation_id=promotion.evaluation_id,
            agent_id=promotion.agent_id,
            ai_system_id=promotion.ai_system_id,
            incident_id=promotion.incident_id,
            breach_fingerprint=promotion.breach_fingerprint,
            disposition=promotion.disposition,
            promoted_by=promotion.promoted_by,
            promoted_at=promotion.promoted_at,
            evidence_digest=promotion.evidence_digest,
            incident_status=incident.status,
            incident_severity=incident.severity,
            incident_version=incident.version,
        )


class RuntimeAssuranceResponseRecommendationRequest(BaseModel):
    """Explicit empty command that rejects arbitrary runtime actuator fields."""

    model_config = ConfigDict(extra="forbid")


class RuntimeAssuranceResponseRecommendationRead(BaseModel):
    """Serialized immutable advisory response evidence."""

    id: str
    promotion_id: str
    evaluation_id: str
    agent_id: str
    ai_system_id: str
    incident_id: str
    breach_fingerprint: str
    source_evidence_digest: str
    policy_id: str
    policy_version: str
    policy_digest: str
    incident_status: IncidentStatus
    incident_severity: RiskTier
    incident_version: int
    kill_switch_enabled: bool
    kill_switch_engaged: bool
    actions: list[RuntimeAssuranceResponseAction]
    rationale_codes: list[RuntimeAssuranceResponseRationale]
    advisory_only: bool
    generated_by: str
    generated_at: datetime
    recommendation_digest: str
    version: int

    @classmethod
    def from_domain(
        cls,
        recommendation: RuntimeAssuranceResponseRecommendation,
    ) -> "RuntimeAssuranceResponseRecommendationRead":
        """Map pure advisory evidence into its minimized transport contract."""
        return cls(
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
            incident_status=recommendation.incident_status,
            incident_severity=recommendation.incident_severity,
            incident_version=recommendation.incident_version,
            kill_switch_enabled=recommendation.kill_switch_enabled,
            kill_switch_engaged=recommendation.kill_switch_engaged,
            actions=list(recommendation.actions),
            rationale_codes=list(recommendation.rationale_codes),
            advisory_only=recommendation.advisory_only,
            generated_by=recommendation.generated_by,
            generated_at=recommendation.generated_at,
            recommendation_digest=recommendation.recommendation_digest,
            version=recommendation.version,
        )
