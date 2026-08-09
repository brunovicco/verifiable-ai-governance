from datetime import UTC, datetime, timedelta

from ai_governance_api.domain.runtime_assurance import (
    RuntimeAssuranceBreachReason,
    RuntimeAssuranceOutcome,
    RuntimeAssurancePolicy,
    RuntimeAssuranceSample,
    evaluate_runtime_assurance,
)
from governance_schemas import RiskTier

NOW = datetime(2026, 8, 9, 18, 0, tzinfo=UTC)


def policy(**overrides: object) -> RuntimeAssurancePolicy:
    values: dict[str, object] = {
        "agent_id": "agent-1",
        "ai_system_id": "system-1",
        "enabled": True,
        "lookback_seconds": 300,
        "evaluation_sample_size": 20,
        "minimum_samples": 3,
        "max_failure_rate": 0.34,
        "max_p95_duration_ms": 500.0,
        "max_consecutive_failures": 3,
        "breach_severity": RiskTier.HIGH,
        "version": 2,
        "created_at": NOW - timedelta(days=1),
        "updated_at": NOW,
    }
    values.update(overrides)
    return RuntimeAssurancePolicy(**values)  # type: ignore[arg-type]


def sample(
    ordinal: int,
    outcome: str,
    duration_ms: float | None = 100.0,
) -> RuntimeAssuranceSample:
    return RuntimeAssuranceSample(
        event_id=f"event-{ordinal:02d}",
        observed_at=NOW - timedelta(seconds=20 - ordinal),
        event_outcome=outcome,
        duration_ms=duration_ms,
    )


def evaluate(
    samples: list[RuntimeAssuranceSample],
    **policy_overrides: object,
):
    return evaluate_runtime_assurance(
        evaluation_id="eval-1",
        initiative_id="initiative-1",
        policy=policy(**policy_overrides),
        samples=samples,
        evaluated_at=NOW,
    )


def test_insufficient_data_never_becomes_breach() -> None:
    result = evaluate([sample(1, "failure"), sample(2, "failure")])
    assert result.outcome is RuntimeAssuranceOutcome.INSUFFICIENT_DATA
    assert result.breach_reasons == ()
    assert result.severity is None


def test_missing_latency_coverage_is_insufficient_when_p95_is_governed() -> None:
    result = evaluate(
        [
            sample(1, "success", None),
            sample(2, "success", None),
            sample(3, "success", None),
        ]
    )
    assert result.sample_count == 3
    assert result.duration_sample_count == 0
    assert result.outcome is RuntimeAssuranceOutcome.INSUFFICIENT_DATA


def test_healthy_sample_is_healthy() -> None:
    result = evaluate(
        [
            sample(1, "success", 100),
            sample(2, "success", 200),
            sample(3, "failure", 300),
        ]
    )
    assert result.failure_rate == 1 / 3
    assert result.p95_duration_ms == 300
    assert result.outcome is RuntimeAssuranceOutcome.HEALTHY


def test_failure_rate_breach_is_strictly_greater_than_threshold() -> None:
    result = evaluate(
        [sample(1, "failure"), sample(2, "failure"), sample(3, "success")],
        max_failure_rate=0.5,
    )
    assert result.outcome is RuntimeAssuranceOutcome.BREACHED
    assert RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED in result.breach_reasons


def test_nearest_rank_p95_can_breach() -> None:
    result = evaluate(
        [
            sample(1, "success", 10),
            sample(2, "success", 20),
            sample(3, "success", 1000),
        ],
        max_p95_duration_ms=999.0,
    )
    assert result.p95_duration_ms == 1000
    assert result.breach_reasons == (RuntimeAssuranceBreachReason.P95_DURATION_EXCEEDED,)


def test_consecutive_failure_breach_counts_error_as_failure() -> None:
    result = evaluate(
        [
            sample(1, "success"),
            sample(2, "failure"),
            sample(3, "error"),
            sample(4, "success"),
        ],
        minimum_samples=4,
        max_failure_rate=1.0,
        max_p95_duration_ms=None,
        max_consecutive_failures=2,
    )
    assert result.max_consecutive_failures == 2
    assert result.breach_reasons == (RuntimeAssuranceBreachReason.CONSECUTIVE_FAILURES_EXCEEDED,)


def test_multiple_breach_reasons_have_stable_order_and_severity() -> None:
    result = evaluate(
        [
            sample(1, "failure", 900),
            sample(2, "failure", 1000),
            sample(3, "failure", 1100),
        ],
        max_failure_rate=0.1,
        max_p95_duration_ms=500,
        max_consecutive_failures=2,
        breach_severity=RiskTier.CRITICAL,
    )
    assert result.outcome is RuntimeAssuranceOutcome.BREACHED
    assert result.breach_reasons == (
        RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,
        RuntimeAssuranceBreachReason.P95_DURATION_EXCEEDED,
        RuntimeAssuranceBreachReason.CONSECUTIVE_FAILURES_EXCEEDED,
    )
    assert result.severity is RiskTier.CRITICAL


def test_sample_is_bounded_to_most_recent_policy_limit() -> None:
    samples = [sample(index, "success") for index in range(1, 8)]
    result = evaluate(
        samples,
        evaluation_sample_size=3,
        minimum_samples=3,
        max_p95_duration_ms=None,
    )
    assert result.sample_count == 3
    assert result.source_event_ids == ("event-05", "event-06", "event-07")


def test_evidence_digest_is_reproducible() -> None:
    samples = [sample(1, "success"), sample(2, "success"), sample(3, "failure")]
    left = evaluate(samples)
    right = evaluate(samples)
    assert left.evidence_digest == right.evidence_digest
    assert len(left.evidence_digest) == 64
