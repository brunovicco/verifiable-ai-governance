from datetime import UTC, datetime

from ai_governance_api.domain.runtime_assurance import (
    RuntimeAssuranceBreachReason,
)
from ai_governance_api.domain.runtime_assurance_incidents import (
    runtime_assurance_breach_fingerprint,
    should_escalate_incident_severity,
)
from governance_schemas import RiskTier

NOW = datetime(2026, 8, 9, 18, 30, tzinfo=UTC)


def test_breach_fingerprint_is_stable_across_reason_order() -> None:
    left = runtime_assurance_breach_fingerprint(
        agent_id="agent-1",
        breach_reasons=(
            RuntimeAssuranceBreachReason.P95_DURATION_EXCEEDED,
            RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,
        ),
    )
    right = runtime_assurance_breach_fingerprint(
        agent_id="agent-1",
        breach_reasons=(
            RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,
            RuntimeAssuranceBreachReason.P95_DURATION_EXCEEDED,
        ),
    )
    assert left == right
    assert len(left) == 64


def test_breach_fingerprint_changes_for_agent_or_reason_family() -> None:
    baseline = runtime_assurance_breach_fingerprint(
        agent_id="agent-1",
        breach_reasons=(RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,),
    )
    other_agent = runtime_assurance_breach_fingerprint(
        agent_id="agent-2",
        breach_reasons=(RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,),
    )
    other_reason = runtime_assurance_breach_fingerprint(
        agent_id="agent-1",
        breach_reasons=(RuntimeAssuranceBreachReason.P95_DURATION_EXCEEDED,),
    )
    assert baseline != other_agent
    assert baseline != other_reason


def test_only_strictly_higher_severity_escalates() -> None:
    assert should_escalate_incident_severity(
        current=RiskTier.HIGH,
        observed=RiskTier.CRITICAL,
    )
    assert not should_escalate_incident_severity(
        current=RiskTier.HIGH,
        observed=RiskTier.HIGH,
    )
    assert not should_escalate_incident_severity(
        current=RiskTier.HIGH,
        observed=RiskTier.MEDIUM,
    )
