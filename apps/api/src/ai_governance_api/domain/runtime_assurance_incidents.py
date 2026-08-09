"""Pure breach fingerprinting and incident-promotion evidence rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from governance_schemas import RiskTier

from ai_governance_api.domain.incidents import IncidentRecord
from ai_governance_api.domain.runtime_assurance import RuntimeAssuranceBreachReason


class RuntimeAssuranceIncidentDisposition(StrEnum):
    """Outcome of one explicit Runtime Assurance incident-promotion command."""

    CREATED = "created"
    DEDUPLICATED = "deduplicated"
    SEVERITY_ESCALATED = "severity_escalated"


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceIncidentPromotion:
    """Append-only evidence binding one assurance evaluation to one incident."""

    id: str
    evaluation_id: str
    agent_id: str
    ai_system_id: str
    incident_id: str
    breach_fingerprint: str
    disposition: RuntimeAssuranceIncidentDisposition
    promoted_by: str
    promoted_at: datetime
    evidence_digest: str
    version: int = 1


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceIncidentPromotionResult:
    """Promotion evidence together with the current linked incident projection."""

    promotion: RuntimeAssuranceIncidentPromotion
    incident: IncidentRecord


def runtime_assurance_breach_fingerprint(
    *,
    agent_id: str,
    breach_reasons: tuple[RuntimeAssuranceBreachReason, ...],
) -> str:
    """Return a stable breach family key independent of policy version and severity."""
    canonical = {
        "schema_version": "1.0",
        "agent_id": agent_id,
        "breach_reasons": sorted(reason.value for reason in breach_reasons),
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def should_escalate_incident_severity(
    *,
    current: RiskTier,
    observed: RiskTier,
) -> bool:
    """Return whether the new breach severity is strictly more severe."""
    rank = {
        RiskTier.LOW: 1,
        RiskTier.MEDIUM: 2,
        RiskTier.HIGH: 3,
        RiskTier.CRITICAL: 4,
    }
    return rank[observed] > rank[current]
