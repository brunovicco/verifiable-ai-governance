"""Pure governed-actuation request contracts and canonical evidence rules."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_responses import RuntimeAssuranceResponseAction

RUNTIME_ASSURANCE_ACTUATION_REQUEST_SCHEMA_VERSION = "1.0"


class RuntimeAssuranceActuationDomainError(ValueError):
    """Raised when trusted recommendation evidence cannot authorize an actuation intent."""


class RuntimeAssuranceActuationAction(StrEnum):
    """Closed set of governed actuation intents; these are not advisory actions."""

    ENGAGE_KILL_SWITCH = "engage_kill_switch"


class RuntimeAssuranceActuationRequestState(StrEnum):
    """States with concrete semantics in P1.9a."""

    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceActuationSourceContext:
    """Trusted immutable lineage plus current governance ownership for one recommendation."""

    recommendation_id: str
    recommendation_digest: str
    promotion_id: str
    evaluation_id: str
    incident_id: str
    agent_id: str
    ai_system_id: str
    ai_system_owner_id: str
    advisory_only: bool
    recommendation_actions: tuple[RuntimeAssuranceResponseAction, ...]
    current_incident_status: IncidentStatus


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceActuationRequest:
    """Append-only genesis evidence for a future human-governed runtime actuation."""

    id: str
    schema_version: str
    recommendation_id: str
    recommendation_digest: str
    promotion_id: str
    evaluation_id: str
    incident_id: str
    agent_id: str
    ai_system_id: str
    action: RuntimeAssuranceActuationAction
    state: RuntimeAssuranceActuationRequestState
    requested_by: str
    requested_at: datetime
    request_digest: str
    version: int = 1


def derive_actuation_action(
    context: RuntimeAssuranceActuationSourceContext,
) -> RuntimeAssuranceActuationAction:
    """Map advisory evidence to one distinct governed intent or fail closed."""
    if not context.advisory_only:
        raise RuntimeAssuranceActuationDomainError(
            "Runtime response recommendation is not advisory-only evidence"
        )
    if len(set(context.recommendation_actions)) != len(context.recommendation_actions):
        raise RuntimeAssuranceActuationDomainError(
            "Runtime response recommendation contains duplicate actions"
        )
    if RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH not in context.recommendation_actions:
        raise RuntimeAssuranceActuationDomainError(
            "Runtime response recommendation does not support kill-switch actuation"
        )
    return RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH


def build_actuation_request_digest(
    *,
    request_id: str,
    recommendation_id: str,
    recommendation_digest: str,
    promotion_id: str,
    evaluation_id: str,
    incident_id: str,
    agent_id: str,
    ai_system_id: str,
    action: RuntimeAssuranceActuationAction,
    state: RuntimeAssuranceActuationRequestState,
    requested_by: str,
    requested_at: datetime,
    schema_version: str = RUNTIME_ASSURANCE_ACTUATION_REQUEST_SCHEMA_VERSION,
    version: int = 1,
) -> str:
    """Return canonical SHA-256 over the complete immutable request binding."""
    if schema_version != RUNTIME_ASSURANCE_ACTUATION_REQUEST_SCHEMA_VERSION:
        raise RuntimeAssuranceActuationDomainError("Unsupported actuation request schema version")
    if version != 1:
        raise RuntimeAssuranceActuationDomainError("Unsupported actuation request version")
    if not _is_sha256(recommendation_digest):
        raise RuntimeAssuranceActuationDomainError("Recommendation digest is invalid")
    if requested_at.tzinfo is None or requested_at.utcoffset() is None:
        raise RuntimeAssuranceActuationDomainError(
            "Actuation request timestamp must be timezone-aware"
        )

    canonical: Mapping[str, object] = {
        "schema_version": schema_version,
        "request_id": request_id,
        "recommendation_id": recommendation_id,
        "recommendation_digest": recommendation_digest,
        "promotion_id": promotion_id,
        "evaluation_id": evaluation_id,
        "incident_id": incident_id,
        "agent_id": agent_id,
        "ai_system_id": ai_system_id,
        "action": action.value,
        "state": state.value,
        "requested_by": requested_by,
        "requested_at": requested_at.astimezone(UTC).isoformat(),
        "version": version,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_actuation_request_binding(
    request: RuntimeAssuranceActuationRequest,
    context: RuntimeAssuranceActuationSourceContext,
    action: RuntimeAssuranceActuationAction,
) -> None:
    """Reject cross-recommendation, cross-Agent, or tampered request evidence."""
    expected = {
        "recommendation_id": context.recommendation_id,
        "recommendation_digest": context.recommendation_digest,
        "promotion_id": context.promotion_id,
        "evaluation_id": context.evaluation_id,
        "incident_id": context.incident_id,
        "agent_id": context.agent_id,
        "ai_system_id": context.ai_system_id,
    }
    observed = {
        "recommendation_id": request.recommendation_id,
        "recommendation_digest": request.recommendation_digest,
        "promotion_id": request.promotion_id,
        "evaluation_id": request.evaluation_id,
        "incident_id": request.incident_id,
        "agent_id": request.agent_id,
        "ai_system_id": request.ai_system_id,
    }
    if observed != expected or request.action is not action:
        raise RuntimeAssuranceActuationDomainError(
            "Runtime Assurance actuation request binding is inconsistent"
        )
    if request.state is not RuntimeAssuranceActuationRequestState.PENDING:
        raise RuntimeAssuranceActuationDomainError(
            "Runtime Assurance actuation request state is invalid for P1.9a"
        )

    expected_digest = build_actuation_request_digest(
        request_id=request.id,
        recommendation_id=request.recommendation_id,
        recommendation_digest=request.recommendation_digest,
        promotion_id=request.promotion_id,
        evaluation_id=request.evaluation_id,
        incident_id=request.incident_id,
        agent_id=request.agent_id,
        ai_system_id=request.ai_system_id,
        action=request.action,
        state=request.state,
        requested_by=request.requested_by,
        requested_at=request.requested_at,
        schema_version=request.schema_version,
        version=request.version,
    )
    if request.request_digest != expected_digest:
        raise RuntimeAssuranceActuationDomainError(
            "Runtime Assurance actuation request digest is inconsistent"
        )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
