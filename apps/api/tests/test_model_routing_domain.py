"""Pure policy tests for governed model-routing enforcement."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_governance_api.domain.model_routing import (
    GovernedRoutingModel,
    GovernedRoutingScope,
    ModelRoutingCommand,
    PolicyModelRouterDecision,
    RouterDecisionOutcome,
    RoutingBlockCode,
    RoutingWorkload,
    enforce_router_decision,
    evaluate_routing_scope,
)
from governance_schemas import DataClassification, EntityStatus, RiskTier

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def command(**overrides: object) -> ModelRoutingCommand:
    """Return bounded operational constraints for domain tests."""
    values: dict[str, object] = {
        "workflow_id": "workflow-1",
        "task_id": "task-1",
        "workload": RoutingWorkload.DOCUMENT_EXTRACTION,
        "context_tokens_estimated": 1000,
        "max_output_tokens_estimated": 500,
        "structured_output_required": True,
        "max_latency_ms": 3000,
        "max_cost_usd": Decimal("0.25"),
    }
    values.update(overrides)
    return ModelRoutingCommand(**values)  # type: ignore[arg-type]


def scope(**overrides: object) -> GovernedRoutingScope:
    """Return a fully reviewed agent and model registry scope."""
    model = GovernedRoutingModel(
        id="model-1",
        version=2,
        status=EntityStatus.APPROVED,
        routing_group="fast-small",
        allowed_data_classes=("public", "internal"),
        approved_scope_digest="a" * 64,
        next_review_at=NOW + timedelta(days=30),
    )
    values: dict[str, object] = {
        "ai_system_id": "system-1",
        "ai_system_version": 1,
        "ai_system_owner_id": "system-owner",
        "ai_system_status": EntityStatus.ACTIVE,
        "risk_tier": RiskTier.MEDIUM,
        "data_classification": DataClassification.INTERNAL,
        "initiative_id": "initiative-1",
        "agent_id": "agent-1",
        "agent_version": 2,
        "agent_name": "Knowledge agent",
        "agent_owner_id": "agent-owner",
        "agent_status": EntityStatus.APPROVED,
        "agent_approved_scope_digest": "b" * 64,
        "agent_next_review_at": NOW + timedelta(days=20),
        "agent_allowed_model_ids": ("model-1",),
        "agent_max_cost": Decimal("0.50"),
        "models": (model,),
    }
    values.update(overrides)
    return GovernedRoutingScope(**values)  # type: ignore[arg-type]


def accepted_decision(group: str = "fast-small") -> PolicyModelRouterDecision:
    """Return a reproducible accepted external decision."""
    return PolicyModelRouterDecision(
        outcome=RouterDecisionOutcome.ACCEPTED,
        schema_version="1.0",
        routing_decision_id="route-1",
        decided_at=NOW,
        workflow_id="workflow-1",
        task_id="task-1",
        selected_model_group=group,
        rejected_model_group=None,
        reason="Mapped workload to approved group",
        reason_code=None,
        observed_value=None,
        required_value=None,
        rejected_candidates=(),
        policy_id="router-policy",
        policy_version="2026.08",
        policy_digest="c" * 64,
        service_version="1.0.0",
        environment="test",
    )


def rejected_decision(
    reason_code: str | None = "data_classification_not_authorized",
) -> PolicyModelRouterDecision:
    """Return a reproducible hard-rejection external decision."""
    return PolicyModelRouterDecision(
        outcome=RouterDecisionOutcome.REJECTED,
        schema_version="1.0",
        routing_decision_id="route-1",
        decided_at=NOW,
        workflow_id="workflow-1",
        task_id="task-1",
        selected_model_group=None,
        rejected_model_group="fast-small",
        reason="Internal data is not authorized for this group",
        reason_code=reason_code,
        observed_value="internal",
        required_value="public",
        rejected_candidates=(),
        policy_id="router-policy",
        policy_version="2026.08",
        policy_digest="c" * 64,
        service_version="1.0.0",
        environment="test",
    )


def test_current_registry_scope_allows_matching_router_group() -> None:
    governed_scope = scope()

    assert evaluate_routing_scope(governed_scope, command(), now=NOW) is None
    assert (
        enforce_router_decision(
            governed_scope,
            command(),
            accepted_decision(),
            expected_scope_digest=governed_scope.digest,
            now=NOW,
        )
        is None
    )


def test_expired_review_and_cost_above_scope_fail_closed() -> None:
    expired = scope(agent_next_review_at=NOW)
    expired_block = evaluate_routing_scope(expired, command(), now=NOW)
    assert expired_block is not None
    assert expired_block.code == RoutingBlockCode.AGENT_REVIEW_NOT_CURRENT

    cost_block = evaluate_routing_scope(
        scope(),
        command(max_cost_usd=Decimal("0.75")),
        now=NOW,
    )
    assert cost_block is not None
    assert cost_block.code == RoutingBlockCode.COST_LIMIT_EXCEEDED


def test_unapproved_group_or_changed_scope_blocks_external_acceptance() -> None:
    governed_scope = scope()
    group_block = enforce_router_decision(
        governed_scope,
        command(),
        accepted_decision("reasoning-strong"),
        expected_scope_digest=governed_scope.digest,
        now=NOW,
    )
    assert group_block is not None
    assert group_block.code == RoutingBlockCode.SELECTED_MODEL_GROUP_NOT_APPROVED

    changed_scope = replace(governed_scope, agent_version=3)
    changed_block = enforce_router_decision(
        changed_scope,
        command(),
        accepted_decision(),
        expected_scope_digest=governed_scope.digest,
        now=NOW,
    )
    assert changed_block is not None
    assert changed_block.code == RoutingBlockCode.REGISTRY_SCOPE_CHANGED


def test_router_rejection_is_propagated_with_reason_code_fallback() -> None:
    governed_scope = scope()

    block = enforce_router_decision(
        governed_scope,
        command(),
        rejected_decision(),
        expected_scope_digest=governed_scope.digest,
        now=NOW,
    )
    assert block is not None
    assert block.code == "data_classification_not_authorized"
    assert block.reason == "Internal data is not authorized for this group"

    fallback_block = enforce_router_decision(
        governed_scope,
        command(),
        rejected_decision(reason_code=None),
        expected_scope_digest=governed_scope.digest,
        now=NOW,
    )
    assert fallback_block is not None
    assert fallback_block.code == RoutingBlockCode.ROUTER_REJECTED
