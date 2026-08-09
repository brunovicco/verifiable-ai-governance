from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance import RuntimeAssuranceBreachReason
from ai_governance_api.domain.runtime_assurance_responses import (
    RuntimeAssuranceResponseAction,
    RuntimeAssuranceResponseContext,
    RuntimeAssuranceResponseRationale,
    derive_runtime_assurance_response_plan,
)
from governance_schemas import RiskTier


def context(
    *,
    reasons: tuple[RuntimeAssuranceBreachReason, ...],
    severity: RiskTier,
    kill_switch_enabled: bool = True,
    kill_switch_engaged: bool = False,
) -> RuntimeAssuranceResponseContext:
    return RuntimeAssuranceResponseContext(
        promotion_id="promotion-1",
        evaluation_id="evaluation-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        incident_id="incident-1",
        breach_fingerprint="b" * 64,
        source_evidence_digest="e" * 64,
        breach_reasons=reasons,
        incident_status=IncidentStatus.OPEN,
        incident_severity=severity,
        incident_version=1,
        ai_system_owner_id="system-owner",
        kill_switch_enabled=kill_switch_enabled,
        kill_switch_engaged=kill_switch_engaged,
    )


def test_high_failure_breach_recommends_investigation_and_containment() -> None:
    plan = derive_runtime_assurance_response_plan(
        context(
            reasons=(RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,),
            severity=RiskTier.HIGH,
        )
    )

    assert plan.actions == (
        RuntimeAssuranceResponseAction.INVESTIGATE_FAILURES,
        RuntimeAssuranceResponseAction.PREPARE_CONTAINMENT,
    )
    assert plan.rationale_codes == (
        RuntimeAssuranceResponseRationale.FAILURE_RATE_EXCEEDED,
        RuntimeAssuranceResponseRationale.ELEVATED_SEVERITY,
    )
    assert len(plan.policy_digest) == 64
    assert len(plan.recommendation_digest) == 64


def test_medium_latency_breach_recommends_latency_review_and_recovery_monitoring() -> None:
    plan = derive_runtime_assurance_response_plan(
        context(
            reasons=(RuntimeAssuranceBreachReason.P95_DURATION_EXCEEDED,),
            severity=RiskTier.MEDIUM,
        )
    )

    assert plan.actions == (
        RuntimeAssuranceResponseAction.INVESTIGATE_LATENCY,
        RuntimeAssuranceResponseAction.MONITOR_RECOVERY,
    )


def test_critical_breach_only_considers_kill_switch_when_available_and_inactive() -> None:
    available = derive_runtime_assurance_response_plan(
        context(
            reasons=(RuntimeAssuranceBreachReason.CONSECUTIVE_FAILURES_EXCEEDED,),
            severity=RiskTier.CRITICAL,
        )
    )
    unavailable = derive_runtime_assurance_response_plan(
        context(
            reasons=(RuntimeAssuranceBreachReason.CONSECUTIVE_FAILURES_EXCEEDED,),
            severity=RiskTier.CRITICAL,
            kill_switch_enabled=False,
        )
    )
    engaged = derive_runtime_assurance_response_plan(
        context(
            reasons=(RuntimeAssuranceBreachReason.CONSECUTIVE_FAILURES_EXCEEDED,),
            severity=RiskTier.CRITICAL,
            kill_switch_engaged=True,
        )
    )

    assert RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH in available.actions
    assert RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH not in unavailable.actions
    assert RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH not in engaged.actions


def test_recommendation_digest_is_reproducible_for_same_structural_context() -> None:
    first = derive_runtime_assurance_response_plan(
        context(
            reasons=(
                RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,
                RuntimeAssuranceBreachReason.P95_DURATION_EXCEEDED,
            ),
            severity=RiskTier.CRITICAL,
        )
    )
    second = derive_runtime_assurance_response_plan(
        context(
            reasons=(
                RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,
                RuntimeAssuranceBreachReason.P95_DURATION_EXCEEDED,
            ),
            severity=RiskTier.CRITICAL,
        )
    )

    assert first == second
