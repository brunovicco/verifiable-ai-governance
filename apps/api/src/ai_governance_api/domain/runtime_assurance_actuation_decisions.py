"""Pure governed-actuation decision contracts and canonical evidence rules."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from governance_schemas import ApprovalArea

from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationSourceContext,
)

RUNTIME_ASSURANCE_ACTUATION_DECISION_SCHEMA_VERSION = "1.0"
RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA = ApprovalArea.SECURITY
MAX_ACTUATION_DECISION_REASON_LENGTH = 2000


class RuntimeAssuranceActuationDecisionDomainError(ValueError):
    """Raised when governed actuation decision evidence is invalid."""


class RuntimeAssuranceActuationDecisionOutcome(StrEnum):
    """Terminal human decisions supported by P1.9b."""

    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceActuationDecisionContext:
    """Trusted actuation request plus its validated source lineage."""

    request: RuntimeAssuranceActuationRequest
    source: RuntimeAssuranceActuationSourceContext

    @property
    def current_incident_status(self) -> IncidentStatus:
        """Return the current linked incident status observed at decision time."""
        return self.source.current_incident_status


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceActuationDecision:
    """Append-only terminal human decision bound to one immutable actuation request."""

    id: str
    schema_version: str
    request_id: str
    request_digest: str
    action: RuntimeAssuranceActuationAction
    decision: RuntimeAssuranceActuationDecisionOutcome
    approval_area: ApprovalArea
    decided_by: str
    decided_at: datetime
    reason: str
    decision_digest: str
    version: int = 1


def normalize_actuation_decision_reason(reason: str) -> str:
    """Return the canonical bounded human reason or fail closed."""
    normalized = reason.strip()
    if not normalized:
        raise RuntimeAssuranceActuationDecisionDomainError(
            "Actuation decision reason must not be empty"
        )
    if len(normalized) > MAX_ACTUATION_DECISION_REASON_LENGTH:
        raise RuntimeAssuranceActuationDecisionDomainError(
            "Actuation decision reason exceeds its size limit"
        )
    return normalized


def build_actuation_decision_digest(
    *,
    decision_id: str,
    request_id: str,
    request_digest: str,
    action: RuntimeAssuranceActuationAction,
    decision: RuntimeAssuranceActuationDecisionOutcome,
    approval_area: ApprovalArea,
    decided_by: str,
    decided_at: datetime,
    reason: str,
    schema_version: str = RUNTIME_ASSURANCE_ACTUATION_DECISION_SCHEMA_VERSION,
    version: int = 1,
) -> str:
    """Return canonical SHA-256 over the complete immutable human decision binding."""
    if schema_version != RUNTIME_ASSURANCE_ACTUATION_DECISION_SCHEMA_VERSION:
        raise RuntimeAssuranceActuationDecisionDomainError(
            "Unsupported actuation decision schema version"
        )
    if version != 1:
        raise RuntimeAssuranceActuationDecisionDomainError("Unsupported actuation decision version")
    if not _is_sha256(request_digest):
        raise RuntimeAssuranceActuationDecisionDomainError("Actuation request digest is invalid")
    if action is not RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH:
        raise RuntimeAssuranceActuationDecisionDomainError("Unsupported P1.9b actuation action")
    if approval_area is not RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA:
        raise RuntimeAssuranceActuationDecisionDomainError(
            "Actuation decision approval area is invalid"
        )
    if decided_at.tzinfo is None or decided_at.utcoffset() is None:
        raise RuntimeAssuranceActuationDecisionDomainError(
            "Actuation decision timestamp must be timezone-aware"
        )
    canonical_reason = normalize_actuation_decision_reason(reason)
    canonical: Mapping[str, object] = {
        "schema_version": schema_version,
        "decision_id": decision_id,
        "request_id": request_id,
        "request_digest": request_digest,
        "action": action.value,
        "decision": decision.value,
        "approval_area": approval_area.value,
        "decided_by": decided_by,
        "decided_at": decided_at.astimezone(UTC).isoformat(),
        "reason": canonical_reason,
        "version": version,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_actuation_decision_binding(
    decision: RuntimeAssuranceActuationDecision,
    context: RuntimeAssuranceActuationDecisionContext,
) -> None:
    """Reject cross-request reuse or tampered human decision evidence."""
    request = context.request
    if (
        decision.request_id != request.id
        or decision.request_digest != request.request_digest
        or decision.action is not request.action
        or request.action is not RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH
        or decision.approval_area is not RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA
        or decision.schema_version != RUNTIME_ASSURANCE_ACTUATION_DECISION_SCHEMA_VERSION
        or decision.version != 1
    ):
        raise RuntimeAssuranceActuationDecisionDomainError(
            "Runtime Assurance actuation decision binding is inconsistent"
        )
    expected_digest = build_actuation_decision_digest(
        decision_id=decision.id,
        request_id=decision.request_id,
        request_digest=decision.request_digest,
        action=decision.action,
        decision=decision.decision,
        approval_area=decision.approval_area,
        decided_by=decision.decided_by,
        decided_at=decision.decided_at,
        reason=decision.reason,
        schema_version=decision.schema_version,
        version=decision.version,
    )
    if decision.decision_digest != expected_digest:
        raise RuntimeAssuranceActuationDecisionDomainError(
            "Runtime Assurance actuation decision digest is inconsistent"
        )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
