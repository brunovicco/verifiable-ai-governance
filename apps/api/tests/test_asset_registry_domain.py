from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.domain.asset_registry import (
    AgentReviewCandidate,
    AssetReviewContext,
    AssetReviewError,
    AssetReviewForbidden,
    AssetReviewState,
    ModelReviewCandidate,
    asset_review_state,
    review_agent_scope,
    review_is_current,
    review_model_scope,
)
from governance_schemas import ApprovalArea, AutonomyLevel, RiskTier

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def review_context(
    *,
    area: ApprovalArea,
    risk_tier: RiskTier = RiskTier.MEDIUM,
    days: int = 30,
    reviewer_id: str = "independent-reviewer",
) -> AssetReviewContext:
    """Return one deterministic independent review context."""
    return AssetReviewContext(
        reviewer_id=reviewer_id,
        reviewer_areas=frozenset({area}),
        owner_ids=frozenset({"asset-owner", "system-owner"}),
        risk_tier=risk_tier,
        reviewed_at=NOW,
        next_review_at=NOW + timedelta(days=days),
        reference="GOV-2026-184",
    )


def model_candidate(**overrides: object) -> ModelReviewCandidate:
    """Return a complete model review scope."""
    values: dict[str, object] = {
        "provider": "Example AI",
        "model_name": "governed-medium",
        "model_version": "2026-08-01",
        "routing_group": "reasoning-medium",
        "deployment_region": "Brazil South",
        "approved_use_cases": ("knowledge assistance",),
        "prohibited_use_cases": ("employment decision",),
        "allowed_data_classes": ("internal", "public"),
        "evaluation_baseline": {"dataset": "rag-eval-v1", "score": 0.91},
        "deprecation_date": None,
    }
    values.update(overrides)
    return ModelReviewCandidate(**values)  # type: ignore[arg-type]


def agent_candidate(**overrides: object) -> AgentReviewCandidate:
    """Return a complete agent review scope."""
    values: dict[str, object] = {
        "name": "Knowledge agent",
        "purpose": "Prepare grounded recommendations from approved sources.",
        "owner_id": "asset-owner",
        "agent_version": "1.0.0",
        "deployment_region": "Brazil South",
        "autonomy_level": AutonomyLevel.A1_RECOMMENDATION,
        "allowed_models": ("model-1",),
        "tools": ("enterprise-search",),
        "permissions": ("knowledge:read",),
        "max_cost": 0.5,
        "max_runtime_seconds": 30,
        "human_approval_points": (),
        "kill_switch_enabled": True,
    }
    values.update(overrides)
    return AgentReviewCandidate(**values)  # type: ignore[arg-type]


def test_model_review_digest_is_stable_and_bound_to_scope() -> None:
    first = review_model_scope(
        model_candidate(),
        review_context(area=ApprovalArea.ARCHITECTURE),
    )
    reordered = review_model_scope(
        model_candidate(
            approved_use_cases=("knowledge assistance",),
            allowed_data_classes=("public", "internal"),
            evaluation_baseline={"score": 0.91, "dataset": "rag-eval-v1"},
        ),
        review_context(area=ApprovalArea.ARCHITECTURE),
    )
    changed = review_model_scope(
        model_candidate(deployment_region="Brazil Southeast"),
        review_context(area=ApprovalArea.ARCHITECTURE),
    )

    assert first.approved_scope_digest == reordered.approved_scope_digest
    assert first.approved_scope_digest != changed.approved_scope_digest
    assert len(first.approved_scope_digest) == 64


def test_review_enforces_authority_independence_and_risk_cadence() -> None:
    with pytest.raises(AssetReviewForbidden, match="architecture"):
        review_model_scope(
            model_candidate(),
            review_context(area=ApprovalArea.SECURITY),
        )

    with pytest.raises(AssetReviewForbidden, match="own scope"):
        review_model_scope(
            model_candidate(),
            review_context(
                area=ApprovalArea.ARCHITECTURE,
                reviewer_id="system-owner",
            ),
        )

    with pytest.raises(AssetReviewError, match="critical"):
        review_model_scope(
            model_candidate(),
            review_context(
                area=ApprovalArea.ARCHITECTURE,
                risk_tier=RiskTier.CRITICAL,
                days=31,
            ),
        )


def test_model_review_requires_use_data_and_evaluation_boundaries() -> None:
    context = review_context(area=ApprovalArea.ARCHITECTURE)

    with pytest.raises(AssetReviewError, match="approved use case"):
        review_model_scope(model_candidate(approved_use_cases=()), context)
    with pytest.raises(AssetReviewError, match="allowed data class"):
        review_model_scope(model_candidate(allowed_data_classes=()), context)
    with pytest.raises(AssetReviewError, match="evaluation baseline"):
        review_model_scope(model_candidate(evaluation_baseline={}), context)
    with pytest.raises(AssetReviewError, match="logical routing group"):
        review_model_scope(model_candidate(routing_group="unassigned"), context)


def test_action_capable_agent_requires_human_and_runtime_boundaries() -> None:
    context = review_context(area=ApprovalArea.SECURITY)
    candidate = agent_candidate(
        autonomy_level=AutonomyLevel.A3_REVERSIBLE_ACTIONS,
        human_approval_points=(),
    )

    with pytest.raises(AssetReviewError, match="human approval"):
        review_agent_scope(candidate, context)

    without_limits = agent_candidate(
        autonomy_level=AutonomyLevel.A3_REVERSIBLE_ACTIONS,
        human_approval_points=("before-write",),
        max_cost=None,
    )
    with pytest.raises(AssetReviewError, match="cost and runtime"):
        review_agent_scope(without_limits, context)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("agent_version", "unversioned", "semantic version"),
        ("deployment_region", "unspecified", "deployment region"),
    ],
)
def test_agent_review_rejects_migration_markers(
    field: str,
    value: str,
    message: str,
) -> None:
    """Prevent transitional migration values from becoming approved scope."""
    with pytest.raises(AssetReviewError, match=message):
        review_agent_scope(
            agent_candidate(**{field: value}),
            review_context(area=ApprovalArea.SECURITY),
        )


def test_review_currentness_expires_at_the_deadline() -> None:
    deadline = NOW + timedelta(days=30)

    assert review_is_current(next_review_at=deadline, now=deadline - timedelta(seconds=1))
    assert not review_is_current(next_review_at=deadline, now=deadline)
    assert not review_is_current(next_review_at=None, now=NOW)


def test_asset_review_state_distinguishes_missing_current_and_expired() -> None:
    """Expose review validity independently from persisted lifecycle status."""
    deadline = NOW + timedelta(days=30)

    assert (
        asset_review_state(
            approved_scope_digest=None,
            next_review_at=None,
            now=NOW,
        )
        is AssetReviewState.NOT_REVIEWED
    )
    assert (
        asset_review_state(
            approved_scope_digest="a" * 64,
            next_review_at=deadline,
            now=NOW,
        )
        is AssetReviewState.CURRENT
    )
    assert (
        asset_review_state(
            approved_scope_digest="a" * 64,
            next_review_at=deadline,
            now=deadline,
        )
        is AssetReviewState.EXPIRED
    )
