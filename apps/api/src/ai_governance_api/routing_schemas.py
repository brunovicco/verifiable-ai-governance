"""HTTP contracts for governed model-routing decisions."""

from datetime import datetime
from decimal import Decimal

from governance_schemas import RuntimeViolationEnvelope
from pydantic import BaseModel, ConfigDict, Field

from ai_governance_api.domain.model_routing import (
    ModelRoutingCommand,
    RouterDecisionOutcome,
    RoutingDecisionSource,
    RoutingEnforcementOutcome,
    RoutingWorkload,
)


class ModelRoutingDecisionRequest(BaseModel):
    """Operational constraints supplied before a model invocation."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1, max_length=200)
    task_id: str = Field(min_length=1, max_length=200)
    workload: RoutingWorkload
    context_tokens_estimated: int = Field(ge=0, le=10_000_000)
    max_output_tokens_estimated: int = Field(ge=0, le=10_000_000)
    structured_output_required: bool
    max_latency_ms: int = Field(gt=0, le=3_600_000)
    max_cost_usd: Decimal = Field(gt=0, max_digits=18, decimal_places=8)

    def to_command(self) -> ModelRoutingCommand:
        """Map untrusted transport input into the pure application command."""
        return ModelRoutingCommand(
            workflow_id=self.workflow_id,
            task_id=self.task_id,
            workload=self.workload,
            context_tokens_estimated=self.context_tokens_estimated,
            max_output_tokens_estimated=self.max_output_tokens_estimated,
            structured_output_required=self.structured_output_required,
            max_latency_ms=self.max_latency_ms,
            max_cost_usd=self.max_cost_usd,
        )


class RejectedRoutingCandidateRead(BaseModel):
    """Serialized logical model group rejected by policy."""

    model_config = ConfigDict(from_attributes=True)

    model_group: str
    reason: str
    reason_code: str
    observed_value: str
    required_value: str


class ModelRoutingDecisionRead(BaseModel):
    """Serialized durable routing evidence and provider provenance."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    ai_system_id: str
    initiative_id: str
    agent_id: str
    requested_by: str
    requested_at: datetime
    scope_digest: str
    workflow_id: str
    task_id: str
    workload: RoutingWorkload
    risk_level: str
    data_classification: str
    context_tokens_estimated: int
    max_output_tokens_estimated: int
    structured_output_required: bool
    max_latency_ms: int
    max_cost_usd: Decimal
    outcome: RoutingEnforcementOutcome
    decision_source: RoutingDecisionSource | None
    router_decision_id: str | None
    router_outcome: RouterDecisionOutcome | None
    decided_at: datetime | None
    selected_model_group: str | None
    rejected_model_group: str | None
    reason: str | None
    reason_code: str | None
    observed_value: str | None
    required_value: str | None
    rejected_candidates: list[RejectedRoutingCandidateRead]
    policy_id: str | None
    policy_version: str | None
    policy_digest: str | None
    service_version: str | None
    environment: str | None
    runtime_violation: RuntimeViolationEnvelope | None = None
    version: int
    created_at: datetime
    updated_at: datetime
