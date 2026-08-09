"""Pure deterministic runtime-assurance policy and evaluation rules."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from governance_schemas import RiskTier


class RuntimeAssuranceOutcome(StrEnum):
    """Closed evaluation outcomes persisted as governance evidence."""

    INSUFFICIENT_DATA = "insufficient_data"
    HEALTHY = "healthy"
    BREACHED = "breached"


class RuntimeAssuranceBreachReason(StrEnum):
    """Closed, deterministic SLO breach reasons."""

    FAILURE_RATE_EXCEEDED = "failure_rate_exceeded"
    P95_DURATION_EXCEEDED = "p95_duration_exceeded"
    CONSECUTIVE_FAILURES_EXCEEDED = "consecutive_failures_exceeded"


_TERMINAL_OUTCOMES = frozenset({"success", "failure", "error"})
_FAILURE_OUTCOMES = frozenset({"failure", "error"})


@dataclass(frozen=True, slots=True)
class RuntimeAssurancePolicy:
    """Versioned SLO policy bound to one governed Agent."""

    agent_id: str
    ai_system_id: str
    enabled: bool
    lookback_seconds: int
    evaluation_sample_size: int
    minimum_samples: int
    max_failure_rate: float
    max_p95_duration_ms: float | None
    max_consecutive_failures: int | None
    breach_severity: RiskTier
    version: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not 60 <= self.lookback_seconds <= 86_400:
            raise ValueError("lookback_seconds must be in 60..86400")
        if not 1 <= self.evaluation_sample_size <= 1000:
            raise ValueError("evaluation_sample_size must be in 1..1000")
        if not 1 <= self.minimum_samples <= self.evaluation_sample_size:
            raise ValueError("minimum_samples must be in 1..evaluation_sample_size")
        if not 0 <= self.max_failure_rate <= 1:
            raise ValueError("max_failure_rate must be in 0..1")
        if self.max_p95_duration_ms is not None and self.max_p95_duration_ms <= 0:
            raise ValueError("max_p95_duration_ms must be positive")
        if self.max_consecutive_failures is not None and not (
            1 <= self.max_consecutive_failures <= self.evaluation_sample_size
        ):
            raise ValueError("max_consecutive_failures must be in 1..evaluation_sample_size")
        if self.version < 1:
            raise ValueError("policy version must be positive")


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceSample:
    """Content-free terminal telemetry facts consumed by the evaluator."""

    event_id: str
    observed_at: datetime
    event_outcome: str
    duration_ms: float | None

    def __post_init__(self) -> None:
        if self.event_outcome not in _TERMINAL_OUTCOMES:
            raise ValueError("runtime assurance samples must be terminal telemetry")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceEvaluation:
    """Append-only deterministic assurance evidence."""

    id: str
    agent_id: str
    ai_system_id: str
    initiative_id: str
    policy_version: int
    evaluated_at: datetime
    window_started_at: datetime
    window_ended_at: datetime
    sample_count: int
    duration_sample_count: int
    failure_count: int
    failure_rate: float
    p95_duration_ms: float | None
    max_consecutive_failures: int
    outcome: RuntimeAssuranceOutcome
    breach_reasons: tuple[RuntimeAssuranceBreachReason, ...]
    severity: RiskTier | None
    source_event_ids: tuple[str, ...]
    evidence_digest: str
    version: int = 1


def evaluate_runtime_assurance(
    *,
    evaluation_id: str,
    initiative_id: str,
    policy: RuntimeAssurancePolicy,
    samples: list[RuntimeAssuranceSample],
    evaluated_at: datetime,
) -> RuntimeAssuranceEvaluation:
    """Evaluate one bounded window using deterministic SLO rules only."""
    evaluated = _as_utc(evaluated_at)
    window_started_at = evaluated - timedelta(seconds=policy.lookback_seconds)
    eligible = [
        sample
        for sample in samples
        if window_started_at <= _as_utc(sample.observed_at) <= evaluated
        and sample.event_outcome in _TERMINAL_OUTCOMES
    ]
    eligible.sort(key=lambda sample: (_as_utc(sample.observed_at), sample.event_id))
    bounded = eligible[-policy.evaluation_sample_size :]

    sample_count = len(bounded)
    failures = [sample for sample in bounded if sample.event_outcome in _FAILURE_OUTCOMES]
    failure_count = len(failures)
    failure_rate = failure_count / sample_count if sample_count else 0.0
    durations = sorted(sample.duration_ms for sample in bounded if sample.duration_ms is not None)
    duration_sample_count = len(durations)
    p95_duration_ms = _nearest_rank_p95(durations)
    max_consecutive_failures = _max_consecutive_failures(bounded)

    enough_samples = sample_count >= policy.minimum_samples
    enough_duration_samples = (
        policy.max_p95_duration_ms is None or duration_sample_count >= policy.minimum_samples
    )
    reasons: list[RuntimeAssuranceBreachReason] = []
    if enough_samples and enough_duration_samples:
        if failure_rate > policy.max_failure_rate:
            reasons.append(RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED)
        if (
            policy.max_p95_duration_ms is not None
            and p95_duration_ms is not None
            and p95_duration_ms > policy.max_p95_duration_ms
        ):
            reasons.append(RuntimeAssuranceBreachReason.P95_DURATION_EXCEEDED)
        if (
            policy.max_consecutive_failures is not None
            and max_consecutive_failures >= policy.max_consecutive_failures
        ):
            reasons.append(RuntimeAssuranceBreachReason.CONSECUTIVE_FAILURES_EXCEEDED)

    if not enough_samples or not enough_duration_samples:
        outcome = RuntimeAssuranceOutcome.INSUFFICIENT_DATA
    elif reasons:
        outcome = RuntimeAssuranceOutcome.BREACHED
    else:
        outcome = RuntimeAssuranceOutcome.HEALTHY

    severity = policy.breach_severity if outcome is RuntimeAssuranceOutcome.BREACHED else None
    source_event_ids = tuple(sample.event_id for sample in bounded)
    canonical = {
        "id": evaluation_id,
        "agent_id": policy.agent_id,
        "ai_system_id": policy.ai_system_id,
        "initiative_id": initiative_id,
        "policy_version": policy.version,
        "evaluated_at": evaluated.isoformat(),
        "window_started_at": window_started_at.isoformat(),
        "window_ended_at": evaluated.isoformat(),
        "sample_count": sample_count,
        "duration_sample_count": duration_sample_count,
        "failure_count": failure_count,
        "failure_rate": failure_rate,
        "p95_duration_ms": p95_duration_ms,
        "max_consecutive_failures": max_consecutive_failures,
        "outcome": outcome.value,
        "breach_reasons": [reason.value for reason in reasons],
        "severity": severity.value if severity is not None else None,
        "source_event_ids": list(source_event_ids),
        "version": 1,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return RuntimeAssuranceEvaluation(
        id=evaluation_id,
        agent_id=policy.agent_id,
        ai_system_id=policy.ai_system_id,
        initiative_id=initiative_id,
        policy_version=policy.version,
        evaluated_at=evaluated,
        window_started_at=window_started_at,
        window_ended_at=evaluated,
        sample_count=sample_count,
        duration_sample_count=duration_sample_count,
        failure_count=failure_count,
        failure_rate=failure_rate,
        p95_duration_ms=p95_duration_ms,
        max_consecutive_failures=max_consecutive_failures,
        outcome=outcome,
        breach_reasons=tuple(reasons),
        severity=severity,
        source_event_ids=source_event_ids,
        evidence_digest=digest,
    )


def _nearest_rank_p95(values: list[float]) -> float | None:
    if not values:
        return None
    rank = math.ceil(0.95 * len(values))
    return values[rank - 1]


def _max_consecutive_failures(samples: list[RuntimeAssuranceSample]) -> int:
    maximum = 0
    current = 0
    for sample in samples:
        if sample.event_outcome in _FAILURE_OUTCOMES:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
