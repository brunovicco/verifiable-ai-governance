"""Pure deterministic runtime-response recommendation rules."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from governance_schemas import RiskTier

from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance import RuntimeAssuranceBreachReason

RUNTIME_ASSURANCE_RESPONSE_POLICY_ID = "runtime-assurance-response"
RUNTIME_ASSURANCE_RESPONSE_POLICY_VERSION = "1.0"


class RuntimeAssuranceResponseAction(StrEnum):
    """Closed set of advisory actions emitted by the response policy."""

    INVESTIGATE_FAILURES = "investigate_failures"
    INVESTIGATE_LATENCY = "investigate_latency"
    PREPARE_CONTAINMENT = "prepare_containment"
    CONSIDER_KILL_SWITCH = "consider_kill_switch"
    MONITOR_RECOVERY = "monitor_recovery"


class RuntimeAssuranceResponseRationale(StrEnum):
    """Closed rationale codes explaining deterministic recommendations."""

    FAILURE_RATE_EXCEEDED = "failure_rate_exceeded"
    P95_DURATION_EXCEEDED = "p95_duration_exceeded"
    CONSECUTIVE_FAILURES_EXCEEDED = "consecutive_failures_exceeded"
    ELEVATED_SEVERITY = "elevated_severity"
    CRITICAL_KILL_SWITCH_AVAILABLE = "critical_kill_switch_available"
    LOWER_SEVERITY_RECOVERY_MONITORING = "lower_severity_recovery_monitoring"


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceResponseContext:
    """Trusted structural facts used to derive an advisory recommendation."""

    promotion_id: str
    evaluation_id: str
    agent_id: str
    ai_system_id: str
    incident_id: str
    breach_fingerprint: str
    source_evidence_digest: str
    breach_reasons: tuple[RuntimeAssuranceBreachReason, ...]
    incident_status: IncidentStatus
    incident_severity: RiskTier
    incident_version: int
    ai_system_owner_id: str
    kill_switch_enabled: bool
    kill_switch_engaged: bool


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceResponsePlan:
    """Deterministic advisory actions and their controlled rationale codes."""

    actions: tuple[RuntimeAssuranceResponseAction, ...]
    rationale_codes: tuple[RuntimeAssuranceResponseRationale, ...]
    policy_id: str
    policy_version: str
    policy_digest: str
    recommendation_digest: str


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceResponseRecommendation:
    """Append-only evidence for one generated advisory response plan."""

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
    actions: tuple[RuntimeAssuranceResponseAction, ...]
    rationale_codes: tuple[RuntimeAssuranceResponseRationale, ...]
    advisory_only: bool
    generated_by: str
    generated_at: datetime
    recommendation_digest: str
    version: int = 1


def runtime_assurance_response_policy_digest() -> str:
    """Return the canonical digest of the immutable P1.8c response rule catalog."""
    policy = {
        "schema_version": "1.0",
        "policy_id": RUNTIME_ASSURANCE_RESPONSE_POLICY_ID,
        "policy_version": RUNTIME_ASSURANCE_RESPONSE_POLICY_VERSION,
        "rules": [
            {
                "when": [
                    RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED.value,
                    RuntimeAssuranceBreachReason.CONSECUTIVE_FAILURES_EXCEEDED.value,
                ],
                "action": RuntimeAssuranceResponseAction.INVESTIGATE_FAILURES.value,
            },
            {
                "when": [RuntimeAssuranceBreachReason.P95_DURATION_EXCEEDED.value],
                "action": RuntimeAssuranceResponseAction.INVESTIGATE_LATENCY.value,
            },
            {
                "when_severity": [RiskTier.HIGH.value, RiskTier.CRITICAL.value],
                "action": RuntimeAssuranceResponseAction.PREPARE_CONTAINMENT.value,
            },
            {
                "when_severity": [RiskTier.CRITICAL.value],
                "when_kill_switch_enabled": True,
                "when_kill_switch_engaged": False,
                "action": RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH.value,
            },
            {
                "when_severity": [RiskTier.LOW.value, RiskTier.MEDIUM.value],
                "action": RuntimeAssuranceResponseAction.MONITOR_RECOVERY.value,
            },
        ],
    }
    return _sha256(policy)


def derive_runtime_assurance_response_plan(
    context: RuntimeAssuranceResponseContext,
) -> RuntimeAssuranceResponsePlan:
    """Derive deterministic advisory actions without mutating runtime or incidents."""
    actions: list[RuntimeAssuranceResponseAction] = []
    rationales: list[RuntimeAssuranceResponseRationale] = []
    reasons = frozenset(context.breach_reasons)

    if reasons & {
        RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,
        RuntimeAssuranceBreachReason.CONSECUTIVE_FAILURES_EXCEEDED,
    }:
        actions.append(RuntimeAssuranceResponseAction.INVESTIGATE_FAILURES)
        if RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED in reasons:
            rationales.append(RuntimeAssuranceResponseRationale.FAILURE_RATE_EXCEEDED)
        if RuntimeAssuranceBreachReason.CONSECUTIVE_FAILURES_EXCEEDED in reasons:
            rationales.append(RuntimeAssuranceResponseRationale.CONSECUTIVE_FAILURES_EXCEEDED)

    if RuntimeAssuranceBreachReason.P95_DURATION_EXCEEDED in reasons:
        actions.append(RuntimeAssuranceResponseAction.INVESTIGATE_LATENCY)
        rationales.append(RuntimeAssuranceResponseRationale.P95_DURATION_EXCEEDED)

    if context.incident_severity in {RiskTier.HIGH, RiskTier.CRITICAL}:
        actions.append(RuntimeAssuranceResponseAction.PREPARE_CONTAINMENT)
        rationales.append(RuntimeAssuranceResponseRationale.ELEVATED_SEVERITY)
    else:
        actions.append(RuntimeAssuranceResponseAction.MONITOR_RECOVERY)
        rationales.append(RuntimeAssuranceResponseRationale.LOWER_SEVERITY_RECOVERY_MONITORING)

    if (
        context.incident_severity is RiskTier.CRITICAL
        and context.kill_switch_enabled
        and not context.kill_switch_engaged
    ):
        actions.append(RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH)
        rationales.append(RuntimeAssuranceResponseRationale.CRITICAL_KILL_SWITCH_AVAILABLE)

    actions_tuple = tuple(dict.fromkeys(actions))
    rationales_tuple = tuple(dict.fromkeys(rationales))
    policy_digest = runtime_assurance_response_policy_digest()
    recommendation_digest = _recommendation_digest(
        context=context,
        actions=actions_tuple,
        rationale_codes=rationales_tuple,
        policy_digest=policy_digest,
    )
    return RuntimeAssuranceResponsePlan(
        actions=actions_tuple,
        rationale_codes=rationales_tuple,
        policy_id=RUNTIME_ASSURANCE_RESPONSE_POLICY_ID,
        policy_version=RUNTIME_ASSURANCE_RESPONSE_POLICY_VERSION,
        policy_digest=policy_digest,
        recommendation_digest=recommendation_digest,
    )


def _recommendation_digest(
    *,
    context: RuntimeAssuranceResponseContext,
    actions: tuple[RuntimeAssuranceResponseAction, ...],
    rationale_codes: tuple[RuntimeAssuranceResponseRationale, ...],
    policy_digest: str,
) -> str:
    canonical = {
        "schema_version": "1.0",
        "promotion_id": context.promotion_id,
        "evaluation_id": context.evaluation_id,
        "agent_id": context.agent_id,
        "ai_system_id": context.ai_system_id,
        "incident_id": context.incident_id,
        "breach_fingerprint": context.breach_fingerprint,
        "source_evidence_digest": context.source_evidence_digest,
        "breach_reasons": sorted(reason.value for reason in context.breach_reasons),
        "incident_status": context.incident_status.value,
        "incident_severity": context.incident_severity.value,
        "incident_version": context.incident_version,
        "kill_switch_enabled": context.kill_switch_enabled,
        "kill_switch_engaged": context.kill_switch_engaged,
        "policy_id": RUNTIME_ASSURANCE_RESPONSE_POLICY_ID,
        "policy_version": RUNTIME_ASSURANCE_RESPONSE_POLICY_VERSION,
        "policy_digest": policy_digest,
        "actions": [action.value for action in actions],
        "rationale_codes": [rationale.value for rationale in rationale_codes],
        "advisory_only": True,
    }
    return _sha256(canonical)


def _sha256(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
