"""Pure policies and records for governed model-routing decisions."""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from governance_schemas import (
    AutonomyLevel,
    DataClassification,
    EntityStatus,
    RiskTier,
    RuntimeViolationEnvelope,
    SignedRuntimeAuthorization,
)

from ai_governance_api.domain.asset_registry import review_is_current

P1_3_SIGNED_RUNTIME_AUTHORIZATION = True
P1_4_DURABLE_RUNTIME_VIOLATIONS = True


class RoutingWorkload(StrEnum):
    """Workloads supported by the current policy-model-router contract."""

    DOCUMENT_EXTRACTION = "document_extraction"
    CASHFLOW_ANALYSIS = "cashflow_analysis"
    FINDINGS_CORRELATION = "findings_correlation"
    OPINION_DRAFTING = "opinion_drafting"
    JSON_REPAIR = "json_repair"


class RouterDecisionOutcome(StrEnum):
    """Outcomes returned by the external policy decision point."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RoutingEnforcementOutcome(StrEnum):
    """Local enforcement state for one routing attempt."""

    PENDING = "pending"
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"


class RoutingDecisionSource(StrEnum):
    """Authority responsible for the final enforcement outcome."""

    GOVERNANCE_REGISTRY = "governance_registry"
    POLICY_MODEL_ROUTER = "policy_model_router"


class RoutingBlockCode(StrEnum):
    """Stable local reason codes used without parsing human-readable text."""

    SYSTEM_NOT_OPERATIONAL = "system_not_operational"
    AGENT_NOT_APPROVED = "agent_not_approved"
    AGENT_REVIEW_NOT_CURRENT = "agent_review_not_current"
    AGENT_SCOPE_DRIFTED = "agent_scope_drifted"
    APPROVED_MODEL_UNAVAILABLE = "approved_model_unavailable"
    MODEL_SCOPE_DRIFTED = "model_scope_drifted"
    DATA_CLASSIFICATION_NOT_APPROVED = "data_classification_not_approved"
    COST_LIMIT_EXCEEDED = "cost_limit_exceeded"
    REGISTRY_SCOPE_CHANGED = "registry_scope_changed"
    SELECTED_MODEL_GROUP_NOT_APPROVED = "selected_model_group_not_approved"
    ROUTER_REJECTED = "router_rejected"
    ROUTER_UNAVAILABLE = "router_unavailable"
    RUNTIME_AUTHORIZATION_UNAVAILABLE = "runtime_authorization_unavailable"
    KILL_SWITCH_ENGAGED = "kill_switch_engaged"
    RUNTIME_CONTROL_UNAVAILABLE = "runtime_control_unavailable"


@dataclass(frozen=True, slots=True)
class ModelRoutingCommand:
    """Caller-supplied operational constraints without trusted governance facts."""

    workflow_id: str
    task_id: str
    workload: RoutingWorkload
    context_tokens_estimated: int
    max_output_tokens_estimated: int
    structured_output_required: bool
    max_latency_ms: int
    max_cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class GovernedRoutingModel:
    """Reviewed model facts relevant to runtime routing enforcement."""

    id: str
    version: int
    status: EntityStatus
    routing_group: str
    allowed_data_classes: tuple[str, ...]
    approved_scope_digest: str | None
    next_review_at: datetime | None
    scope_digest_matches: bool = True
    model_version: str = "unversioned"


@dataclass(frozen=True, slots=True)
class GovernedRoutingScope:
    """Trusted registry projection used before and after the external decision."""

    ai_system_id: str
    ai_system_version: int
    ai_system_owner_id: str
    ai_system_status: EntityStatus
    risk_tier: RiskTier
    data_classification: DataClassification
    initiative_id: str
    agent_id: str
    agent_version: int
    agent_name: str
    agent_owner_id: str
    agent_status: EntityStatus
    agent_approved_scope_digest: str | None
    agent_next_review_at: datetime | None
    agent_allowed_model_ids: tuple[str, ...]
    agent_max_cost: Decimal | None
    models: tuple[GovernedRoutingModel, ...]
    agent_scope_digest_matches: bool = True
    agent_autonomy_level: AutonomyLevel = AutonomyLevel.A0_INFORMATION
    agent_tools: tuple[str, ...] = ()
    agent_permissions: tuple[str, ...] = ()
    agent_max_runtime_seconds: int | None = None
    agent_human_approval_points: tuple[str, ...] = ()
    agent_kill_switch_enabled: bool = False

    @property
    def digest(self) -> str:
        """Return a canonical digest of every material runtime authorization fact."""
        canonical = json.dumps(
            {
                "ai_system_id": self.ai_system_id,
                "ai_system_version": self.ai_system_version,
                "ai_system_status": self.ai_system_status.value,
                "risk_tier": self.risk_tier.value,
                "data_classification": self.data_classification.value,
                "agent_id": self.agent_id,
                "agent_version": self.agent_version,
                "agent_name": self.agent_name,
                "agent_status": self.agent_status.value,
                "agent_approved_scope_digest": self.agent_approved_scope_digest,
                "agent_scope_digest_matches": self.agent_scope_digest_matches,
                "agent_next_review_at": _datetime_text(self.agent_next_review_at),
                "agent_allowed_model_ids": sorted(self.agent_allowed_model_ids),
                "agent_max_cost": (
                    str(self.agent_max_cost) if self.agent_max_cost is not None else None
                ),
                "agent_autonomy_level": self.agent_autonomy_level.value,
                "agent_tools": sorted(self.agent_tools),
                "agent_permissions": sorted(self.agent_permissions),
                "agent_max_runtime_seconds": self.agent_max_runtime_seconds,
                "agent_human_approval_points": sorted(self.agent_human_approval_points),
                "agent_kill_switch_enabled": self.agent_kill_switch_enabled,
                "models": [
                    {
                        "id": model.id,
                        "version": model.version,
                        "status": model.status.value,
                        "routing_group": model.routing_group,
                        "allowed_data_classes": sorted(model.allowed_data_classes),
                        "approved_scope_digest": model.approved_scope_digest,
                        "scope_digest_matches": model.scope_digest_matches,
                        "model_version": model.model_version,
                        "next_review_at": _datetime_text(model.next_review_at),
                    }
                    for model in sorted(self.models, key=lambda item: item.id)
                ],
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RoutingBlock:
    """Structured governance reason for refusing a model invocation."""

    code: str
    reason: str


@dataclass(frozen=True, slots=True)
class PolicyModelRouterRequest:
    """Trusted request sent to the external policy decision point."""

    schema_version: str
    requested_at: datetime
    workflow_id: str
    task_id: str
    agent_name: str
    workload: RoutingWorkload
    risk_level: RiskTier
    data_classification: DataClassification
    context_tokens_estimated: int
    max_output_tokens_estimated: int
    structured_output_required: bool
    max_latency_ms: int
    max_cost_usd: Decimal
    runtime_authorization: SignedRuntimeAuthorization | None = None


@dataclass(frozen=True, slots=True)
class RejectedRoutingCandidate:
    """One logical model group excluded by the routing policy."""

    model_group: str
    reason: str
    reason_code: str
    observed_value: str
    required_value: str


@dataclass(frozen=True, slots=True)
class PolicyModelRouterDecision:
    """Validated provider decision and its reproducibility provenance."""

    outcome: RouterDecisionOutcome
    schema_version: str
    routing_decision_id: str
    decided_at: datetime
    workflow_id: str
    task_id: str
    selected_model_group: str | None
    rejected_model_group: str | None
    reason: str
    reason_code: str | None
    observed_value: str | None
    required_value: str | None
    rejected_candidates: tuple[RejectedRoutingCandidate, ...]
    policy_id: str
    policy_version: str
    policy_digest: str
    service_version: str
    environment: str


@dataclass(frozen=True, slots=True)
class ModelRoutingDecisionRecord:
    """Durable local evidence for one model-routing enforcement attempt."""

    id: str
    ai_system_id: str
    initiative_id: str
    agent_id: str
    requested_by: str
    requested_at: datetime
    scope_digest: str
    command: ModelRoutingCommand
    risk_level: RiskTier
    data_classification: DataClassification
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
    rejected_candidates: tuple[RejectedRoutingCandidate, ...]
    policy_id: str | None
    policy_version: str | None
    policy_digest: str | None
    service_version: str | None
    environment: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    runtime_violation: RuntimeViolationEnvelope | None = None


def build_router_request(
    scope: GovernedRoutingScope,
    command: ModelRoutingCommand,
    *,
    requested_at: datetime,
) -> PolicyModelRouterRequest:
    """Combine caller constraints with authoritative registry context."""
    return PolicyModelRouterRequest(
        schema_version="1.0",
        requested_at=requested_at,
        workflow_id=command.workflow_id,
        task_id=command.task_id,
        agent_name=scope.agent_name,
        workload=command.workload,
        risk_level=scope.risk_tier,
        data_classification=scope.data_classification,
        context_tokens_estimated=command.context_tokens_estimated,
        max_output_tokens_estimated=command.max_output_tokens_estimated,
        structured_output_required=command.structured_output_required,
        max_latency_ms=command.max_latency_ms,
        max_cost_usd=command.max_cost_usd,
    )


def evaluate_routing_scope(
    scope: GovernedRoutingScope,
    command: ModelRoutingCommand,
    *,
    now: datetime,
) -> RoutingBlock | None:
    """Fail closed unless the system, agent, and at least one model remain approved."""
    if scope.ai_system_status not in {EntityStatus.APPROVED, EntityStatus.ACTIVE}:
        return RoutingBlock(
            RoutingBlockCode.SYSTEM_NOT_OPERATIONAL,
            "AI system is not operational for model routing",
        )
    if scope.agent_status is not EntityStatus.APPROVED:
        return RoutingBlock(
            RoutingBlockCode.AGENT_NOT_APPROVED,
            "Agent does not have an approved runtime scope",
        )
    if not scope.agent_scope_digest_matches:
        return RoutingBlock(
            RoutingBlockCode.AGENT_SCOPE_DRIFTED,
            "Agent material scope no longer matches its approved review digest",
        )
    if not _review_current(
        scope.agent_approved_scope_digest,
        scope.agent_next_review_at,
        now,
    ):
        return RoutingBlock(
            RoutingBlockCode.AGENT_REVIEW_NOT_CURRENT,
            "Agent review is missing or expired",
        )
    eligible_models = _eligible_models(scope, now=now)
    if not eligible_models:
        allowed_ids = set(scope.agent_allowed_model_ids)
        if any(
            model.id in allowed_ids
            and model.status is EntityStatus.APPROVED
            and not model.scope_digest_matches
            for model in scope.models
        ):
            return RoutingBlock(
                RoutingBlockCode.MODEL_SCOPE_DRIFTED,
                "An allowed model no longer matches its approved review digest",
            )
        return RoutingBlock(
            RoutingBlockCode.APPROVED_MODEL_UNAVAILABLE,
            "Agent has no currently approved model available for routing",
        )
    if not any(
        scope.data_classification.value in model.allowed_data_classes for model in eligible_models
    ):
        return RoutingBlock(
            RoutingBlockCode.DATA_CLASSIFICATION_NOT_APPROVED,
            "No approved agent model authorizes the initiative data classification",
        )
    if scope.agent_max_cost is not None and command.max_cost_usd > scope.agent_max_cost:
        return RoutingBlock(
            RoutingBlockCode.COST_LIMIT_EXCEEDED,
            "Requested cost ceiling exceeds the reviewed agent limit",
        )
    return None


def enforce_router_decision(
    scope: GovernedRoutingScope,
    command: ModelRoutingCommand,
    decision: PolicyModelRouterDecision,
    *,
    expected_scope_digest: str,
    now: datetime,
) -> RoutingBlock | None:
    """Revalidate mutable scope and bind an accepted group to an approved model."""
    if scope.digest != expected_scope_digest:
        return RoutingBlock(
            RoutingBlockCode.REGISTRY_SCOPE_CHANGED,
            "Governed registry scope changed while routing was in progress",
        )
    current_block = evaluate_routing_scope(scope, command, now=now)
    if current_block is not None:
        return current_block
    if decision.outcome is RouterDecisionOutcome.REJECTED:
        return RoutingBlock(
            decision.reason_code or RoutingBlockCode.ROUTER_REJECTED,
            decision.reason,
        )
    selected_group = decision.selected_model_group
    approved_groups = {
        model.routing_group
        for model in _eligible_models(scope, now=now)
        if scope.data_classification.value in model.allowed_data_classes
    }
    if selected_group is None or selected_group not in approved_groups:
        return RoutingBlock(
            RoutingBlockCode.SELECTED_MODEL_GROUP_NOT_APPROVED,
            "Router selected a logical model group outside the approved agent scope",
        )
    return None


def finalize_routing_record(
    record: ModelRoutingDecisionRecord,
    *,
    outcome: RoutingEnforcementOutcome,
    source: RoutingDecisionSource,
    decided_at: datetime,
    block: RoutingBlock | None = None,
    provider_decision: PolicyModelRouterDecision | None = None,
    runtime_violation: RuntimeViolationEnvelope | None = None,
) -> ModelRoutingDecisionRecord:
    """Produce the immutable completed projection for a pending attempt."""
    if record.outcome is not RoutingEnforcementOutcome.PENDING:
        raise ValueError("Only a pending routing attempt can be finalized")
    return replace(
        record,
        outcome=outcome,
        decision_source=source,
        router_decision_id=(
            provider_decision.routing_decision_id if provider_decision is not None else None
        ),
        router_outcome=(provider_decision.outcome if provider_decision is not None else None),
        decided_at=(provider_decision.decided_at if provider_decision is not None else decided_at),
        selected_model_group=(
            provider_decision.selected_model_group if provider_decision is not None else None
        ),
        rejected_model_group=(
            provider_decision.rejected_model_group if provider_decision is not None else None
        ),
        reason=(
            block.reason
            if block is not None
            else provider_decision.reason
            if provider_decision is not None
            else None
        ),
        reason_code=(
            block.code
            if block is not None
            else provider_decision.reason_code
            if provider_decision is not None
            else None
        ),
        observed_value=(
            provider_decision.observed_value if provider_decision is not None else None
        ),
        required_value=(
            provider_decision.required_value if provider_decision is not None else None
        ),
        rejected_candidates=(
            provider_decision.rejected_candidates if provider_decision is not None else ()
        ),
        policy_id=(provider_decision.policy_id if provider_decision is not None else None),
        policy_version=(
            provider_decision.policy_version if provider_decision is not None else None
        ),
        policy_digest=(provider_decision.policy_digest if provider_decision is not None else None),
        service_version=(
            provider_decision.service_version if provider_decision is not None else None
        ),
        environment=(provider_decision.environment if provider_decision is not None else None),
        runtime_violation=runtime_violation,
        version=record.version + 1,
        updated_at=decided_at,
    )


def _eligible_models(
    scope: GovernedRoutingScope,
    *,
    now: datetime,
) -> tuple[GovernedRoutingModel, ...]:
    """Return current reviewed models explicitly allowed by the agent."""
    allowed_ids = set(scope.agent_allowed_model_ids)
    return tuple(
        model
        for model in scope.models
        if model.id in allowed_ids
        and model.status is EntityStatus.APPROVED
        and bool(model.routing_group.strip())
        and model.routing_group != "unassigned"
        and model.scope_digest_matches
        and _review_current(model.approved_scope_digest, model.next_review_at, now)
    )


def _review_current(
    digest: str | None,
    next_review_at: datetime | None,
    now: datetime,
) -> bool:
    """Require both bound scope evidence and a current deadline."""
    return bool(digest) and review_is_current(next_review_at=next_review_at, now=now)


def _datetime_text(value: datetime | None) -> str | None:
    """Serialize a timestamp deterministically for the scope digest."""
    return value.isoformat() if value is not None else None
