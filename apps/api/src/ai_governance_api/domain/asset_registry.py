"""Pure review policies for governed model and agent registry assets."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from governance_schemas import ApprovalArea, AutonomyLevel, RiskTier


class AssetReviewError(ValueError):
    """Raised when an asset scope cannot receive a trusted review decision."""


class AssetReviewForbidden(AssetReviewError):
    """Raised when a reviewer lacks authority or independence for the asset."""


class RegistryAssetKind(StrEnum):
    """Asset kinds governed by the operational registry review policy."""

    MODEL = "model"
    AGENT = "agent"


class AssetReviewState(StrEnum):
    """Current validity of a persisted asset review projection."""

    NOT_REVIEWED = "not_reviewed"
    CURRENT = "current"
    EXPIRED = "expired"


MIGRATED_AGENT_VERSION = "unversioned"
MIGRATED_DEPLOYMENT_REGION = "unspecified"
MIGRATED_ROUTING_GROUP = "unassigned"


MAX_REVIEW_INTERVAL = {
    RiskTier.LOW: timedelta(days=365),
    RiskTier.MEDIUM: timedelta(days=180),
    RiskTier.HIGH: timedelta(days=90),
    RiskTier.CRITICAL: timedelta(days=30),
}


@dataclass(frozen=True, slots=True)
class AssetReviewContext:
    """Independent reviewer identity, authority, and bounded validity interval."""

    reviewer_id: str
    reviewer_areas: frozenset[ApprovalArea]
    owner_ids: frozenset[str]
    risk_tier: RiskTier
    reviewed_at: datetime
    next_review_at: datetime
    reference: str


@dataclass(frozen=True, slots=True)
class ModelReviewCandidate:
    """Material model scope bound into one review decision."""

    provider: str
    model_name: str
    model_version: str
    routing_group: str
    deployment_region: str
    approved_use_cases: tuple[str, ...]
    prohibited_use_cases: tuple[str, ...]
    allowed_data_classes: tuple[str, ...]
    evaluation_baseline: dict[str, Any]
    deprecation_date: datetime | None


@dataclass(frozen=True, slots=True)
class AgentReviewCandidate:
    """Material agent capability boundary bound into one review decision."""

    name: str
    purpose: str
    owner_id: str
    agent_version: str
    deployment_region: str
    autonomy_level: AutonomyLevel
    allowed_models: tuple[str, ...]
    tools: tuple[str, ...]
    permissions: tuple[str, ...]
    max_cost: float | None
    max_runtime_seconds: int | None
    human_approval_points: tuple[str, ...]
    kill_switch_enabled: bool


@dataclass(frozen=True, slots=True)
class AssetReviewDecision:
    """Content-minimized evidence produced by one successful asset review."""

    kind: RegistryAssetKind
    approved_scope_digest: str
    reviewed_by: str
    reviewed_at: datetime
    next_review_at: datetime
    review_reference: str
    reviewer_area: ApprovalArea


def model_scope_digest(candidate: ModelReviewCandidate) -> str:
    """Return the canonical digest of the material model review scope."""
    return _scope_digest(_model_scope(candidate))


def agent_scope_digest(candidate: AgentReviewCandidate) -> str:
    """Return the canonical digest of the material agent review scope."""
    return _scope_digest(_agent_scope(candidate))


def _model_scope(candidate: ModelReviewCandidate) -> dict[str, Any]:
    """Project material model facts into the canonical review payload."""
    return {
        "provider": candidate.provider,
        "model_name": candidate.model_name,
        "model_version": candidate.model_version,
        "routing_group": candidate.routing_group,
        "deployment_region": candidate.deployment_region,
        "approved_use_cases": sorted(candidate.approved_use_cases),
        "prohibited_use_cases": sorted(candidate.prohibited_use_cases),
        "allowed_data_classes": sorted(candidate.allowed_data_classes),
        "evaluation_baseline": candidate.evaluation_baseline,
        "deprecation_date": (
            candidate.deprecation_date.isoformat()
            if candidate.deprecation_date is not None
            else None
        ),
    }


def _agent_scope(candidate: AgentReviewCandidate) -> dict[str, Any]:
    """Project material agent facts into the canonical review payload."""
    return {
        "name": candidate.name,
        "purpose": candidate.purpose,
        "owner_id": candidate.owner_id,
        "agent_version": candidate.agent_version,
        "deployment_region": candidate.deployment_region,
        "autonomy_level": candidate.autonomy_level.value,
        "allowed_models": sorted(candidate.allowed_models),
        "tools": sorted(candidate.tools),
        "permissions": sorted(candidate.permissions),
        "max_cost": candidate.max_cost,
        "max_runtime_seconds": candidate.max_runtime_seconds,
        "human_approval_points": sorted(candidate.human_approval_points),
        "kill_switch_enabled": candidate.kill_switch_enabled,
    }


def _scope_digest(scope: dict[str, Any]) -> str:
    """Hash deterministic JSON scope, rejecting non-canonical values."""
    try:
        canonical = json.dumps(
            scope,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise AssetReviewError("Asset scope is not canonically serializable") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def review_model_scope(
    candidate: ModelReviewCandidate,
    context: AssetReviewContext,
) -> AssetReviewDecision:
    """Approve an explicit model scope after independent architecture review."""
    _validate_review_context(context, required_area=ApprovalArea.ARCHITECTURE)
    normalized_routing_group = candidate.routing_group.strip().casefold()
    if not normalized_routing_group or normalized_routing_group == MIGRATED_ROUTING_GROUP:
        raise AssetReviewError("Model review requires an explicit logical routing group")
    if not candidate.approved_use_cases:
        raise AssetReviewError("Model review requires at least one approved use case")
    if not candidate.allowed_data_classes:
        raise AssetReviewError("Model review requires at least one allowed data class")
    if not candidate.evaluation_baseline:
        raise AssetReviewError("Model review requires an evaluation baseline")
    overlap = set(candidate.approved_use_cases) & set(candidate.prohibited_use_cases)
    if overlap:
        raise AssetReviewError("Approved and prohibited model use cases must not overlap")
    if candidate.deprecation_date is not None:
        _require_aware(candidate.deprecation_date, "deprecation_date")
        if candidate.deprecation_date <= context.reviewed_at:
            raise AssetReviewError("A deprecated model cannot be approved")
        if context.next_review_at > candidate.deprecation_date:
            raise AssetReviewError("Model review cannot outlive its deprecation date")

    return _decision(
        RegistryAssetKind.MODEL,
        context,
        ApprovalArea.ARCHITECTURE,
        _model_scope(candidate),
    )


def review_agent_scope(
    candidate: AgentReviewCandidate,
    context: AssetReviewContext,
) -> AssetReviewDecision:
    """Approve an explicit agent boundary after independent security review."""
    _validate_review_context(context, required_area=ApprovalArea.SECURITY)
    normalized_version = candidate.agent_version.strip().casefold()
    normalized_region = candidate.deployment_region.strip().casefold()
    if not normalized_version or normalized_version == MIGRATED_AGENT_VERSION:
        raise AssetReviewError("Agent review requires an explicit semantic version")
    if not normalized_region or normalized_region == MIGRATED_DEPLOYMENT_REGION:
        raise AssetReviewError("Agent review requires an explicit deployment region")
    if not candidate.allowed_models:
        raise AssetReviewError("Agent review requires at least one approved model")
    if not candidate.kill_switch_enabled:
        raise AssetReviewError("Agent review requires an enabled kill switch")
    if candidate.tools and not candidate.permissions:
        raise AssetReviewError("Agent tools require an explicit permission boundary")
    if (
        candidate.autonomy_level
        in {
            AutonomyLevel.A2_PREPARE_FOR_APPROVAL,
            AutonomyLevel.A3_REVERSIBLE_ACTIONS,
            AutonomyLevel.A4_HIGH_IMPACT_ACTIONS,
            AutonomyLevel.A5_HIGH_AUTONOMY,
        }
        and not candidate.human_approval_points
    ):
        raise AssetReviewError("Agent autonomy requires at least one human approval point")
    if candidate.autonomy_level in {
        AutonomyLevel.A3_REVERSIBLE_ACTIONS,
        AutonomyLevel.A4_HIGH_IMPACT_ACTIONS,
        AutonomyLevel.A5_HIGH_AUTONOMY,
    } and (candidate.max_cost is None or candidate.max_runtime_seconds is None):
        raise AssetReviewError("Action-capable agents require cost and runtime limits")

    return _decision(
        RegistryAssetKind.AGENT,
        context,
        ApprovalArea.SECURITY,
        _agent_scope(candidate),
    )


def review_is_current(*, next_review_at: datetime | None, now: datetime) -> bool:
    """Return whether a persisted review remains valid at the supplied instant."""
    _require_aware(now, "now")
    if next_review_at is None:
        return False
    _require_aware(next_review_at, "next_review_at")
    return now < next_review_at


def asset_review_state(
    *,
    approved_scope_digest: str | None,
    next_review_at: datetime | None,
    now: datetime,
) -> AssetReviewState:
    """Classify current review validity without mutating lifecycle history."""
    _require_aware(now, "now")
    if not approved_scope_digest or next_review_at is None:
        return AssetReviewState.NOT_REVIEWED
    return (
        AssetReviewState.CURRENT
        if review_is_current(next_review_at=next_review_at, now=now)
        else AssetReviewState.EXPIRED
    )


def _validate_review_context(
    context: AssetReviewContext,
    *,
    required_area: ApprovalArea,
) -> None:
    """Enforce authority, segregation of duties, and risk-based cadence."""
    reviewer_id = context.reviewer_id.strip()
    reference = context.reference.strip()
    if not reviewer_id:
        raise AssetReviewError("Reviewer identity is required")
    if reviewer_id in context.owner_ids:
        raise AssetReviewForbidden("Asset owners cannot approve their own scope")
    if required_area not in context.reviewer_areas:
        raise AssetReviewForbidden(f"Asset review requires the {required_area.value} approval area")
    if not reference:
        raise AssetReviewError("Asset review reference is required")
    _require_aware(context.reviewed_at, "reviewed_at")
    _require_aware(context.next_review_at, "next_review_at")
    if context.next_review_at <= context.reviewed_at:
        raise AssetReviewError("Next review must follow the current review")
    if context.next_review_at > (context.reviewed_at + MAX_REVIEW_INTERVAL[context.risk_tier]):
        raise AssetReviewError(f"Review interval exceeds the {context.risk_tier.value} risk policy")


def _decision(
    kind: RegistryAssetKind,
    context: AssetReviewContext,
    reviewer_area: ApprovalArea,
    scope: dict[str, Any],
) -> AssetReviewDecision:
    """Create a decision bound to a deterministic canonical JSON digest."""
    return AssetReviewDecision(
        kind=kind,
        approved_scope_digest=_scope_digest(scope),
        reviewed_by=context.reviewer_id.strip(),
        reviewed_at=context.reviewed_at,
        next_review_at=context.next_review_at,
        review_reference=context.reference.strip(),
        reviewer_area=reviewer_area,
    )


def _require_aware(value: datetime, label: str) -> None:
    """Reject naive timestamps in review validity calculations."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise AssetReviewError(f"{label} must be timezone-aware")
