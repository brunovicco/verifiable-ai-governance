"""Integration tests for P0.4 scope-digest drift enforcement."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ai_governance_api.adapters import SqlAlchemyModelRoutingScopeReader
from ai_governance_api.database import SessionFactory
from ai_governance_api.domain.asset_registry import (
    ModelReviewCandidate,
    model_scope_digest,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.model_routing import (
    ModelRoutingCommand,
    RoutingBlockCode,
    RoutingWorkload,
    evaluate_routing_scope,
)
from ai_governance_api.errors import ApplicationError, ErrorKind
from ai_governance_api.models import Agent, ModelAsset
from ai_governance_api.schemas import AssetReviewRequest
from ai_governance_api.services import InventoryService
from governance_schemas import ApprovalArea

from scripts.canonical_demo_seed import ensure_canonical_demo


def _command() -> ModelRoutingCommand:
    """Return one bounded credit-opinion routing command."""
    return ModelRoutingCommand(
        workflow_id="p0-4-scope-drift",
        task_id="opinion-draft",
        workload=RoutingWorkload.OPINION_DRAFTING,
        context_tokens_estimated=2500,
        max_output_tokens_estimated=800,
        structured_output_required=True,
        max_latency_ms=4000,
        max_cost_usd=Decimal("0.20"),
    )


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive timestamps for application requests."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def test_public_model_digest_is_order_stable() -> None:
    """Set-like ordering and JSON key ordering must not change the scope digest."""
    candidate = ModelReviewCandidate(
        provider="Example AI",
        model_name="governed-medium",
        model_version="2026-08-01",
        routing_group="reasoning-medium",
        deployment_region="Brazil South",
        approved_use_cases=("knowledge assistance", "summarization"),
        prohibited_use_cases=("employment decision",),
        allowed_data_classes=("internal", "public"),
        evaluation_baseline={"dataset": "eval-v1", "score": 0.94},
        deprecation_date=None,
    )
    reordered = ModelReviewCandidate(
        provider=candidate.provider,
        model_name=candidate.model_name,
        model_version=candidate.model_version,
        routing_group=candidate.routing_group,
        deployment_region=candidate.deployment_region,
        approved_use_cases=tuple(reversed(candidate.approved_use_cases)),
        prohibited_use_cases=candidate.prohibited_use_cases,
        allowed_data_classes=tuple(reversed(candidate.allowed_data_classes)),
        evaluation_baseline={"score": 0.94, "dataset": "eval-v1"},
        deprecation_date=None,
    )

    assert model_scope_digest(candidate) == model_scope_digest(reordered)


async def test_runtime_blocks_direct_model_scope_drift() -> None:
    """A persistence mutation cannot reuse a previously approved model digest."""
    summary = await ensure_canonical_demo()
    reader = SqlAlchemyModelRoutingScopeReader(SessionFactory)

    current = await reader.get(summary.agent_id)
    assert current is not None
    approved = next(model for model in current.models if model.id == summary.approved_model_id)
    assert approved.scope_digest_matches is True

    async with SessionFactory() as session:
        model = await session.get(ModelAsset, summary.approved_model_id)
        assert model is not None
        model.deployment_region = "Unexpected Direct Database Region"
        await session.commit()

    drifted = await reader.get(summary.agent_id)
    assert drifted is not None
    changed_model = next(model for model in drifted.models if model.id == summary.approved_model_id)
    assert changed_model.scope_digest_matches is False

    block = evaluate_routing_scope(drifted, _command(), now=datetime.now(UTC))
    assert block is not None
    assert block.code == RoutingBlockCode.MODEL_SCOPE_DRIFTED


async def test_runtime_blocks_direct_agent_scope_drift() -> None:
    """A direct permission expansion invalidates the reviewed agent scope."""
    summary = await ensure_canonical_demo()
    reader = SqlAlchemyModelRoutingScopeReader(SessionFactory)

    current = await reader.get(summary.agent_id)
    assert current is not None
    assert current.agent_scope_digest_matches is True

    async with SessionFactory() as session:
        agent = await session.get(Agent, summary.agent_id)
        assert agent is not None
        agent.permissions = [*agent.permissions, "credit:approve"]
        await session.commit()

    drifted = await reader.get(summary.agent_id)
    assert drifted is not None
    assert drifted.agent_scope_digest_matches is False

    block = evaluate_routing_scope(drifted, _command(), now=datetime.now(UTC))
    assert block is not None
    assert block.code == RoutingBlockCode.AGENT_SCOPE_DRIFTED


async def test_agent_review_rejects_model_with_scope_drift() -> None:
    """A stale model review cannot support a fresh dependent-agent review."""
    summary = await ensure_canonical_demo()

    async with SessionFactory() as session:
        model = await session.get(ModelAsset, summary.approved_model_id)
        assert model is not None
        model.provider = "Unexpected Direct Database Provider"
        await session.commit()

    async with SessionFactory() as session:
        agent = await session.get(Agent, summary.agent_id)
        assert agent is not None
        assert agent.next_review_at is not None
        request = AssetReviewRequest(
            expected_version=agent.version,
            next_review_at=_as_utc(agent.next_review_at),
            reference="P0-4-SEC-REVIEW",
        )
        reviewer = Principal(
            user_id="p0-4-security-reviewer",
            approval_areas=frozenset({ApprovalArea.SECURITY}),
        )
        with pytest.raises(ApplicationError) as exc_info:
            await InventoryService(session).review_agent(
                agent.id,
                request,
                reviewer,
            )

    assert exc_info.value.kind is ErrorKind.UNPROCESSABLE
