"""SQLAlchemy persistence for deterministic runtime-assurance evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from governance_schemas import RiskTier
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.application.runtime_assurance import (
    RuntimeAssuranceAuditPort,
    RuntimeAssuranceRepositoryPort,
    RuntimeAssuranceScope,
)
from ai_governance_api.audit import append_audit_event
from ai_governance_api.domain.runtime_assurance import (
    RuntimeAssuranceBreachReason,
    RuntimeAssuranceEvaluation,
    RuntimeAssuranceOutcome,
    RuntimeAssurancePolicy,
    RuntimeAssuranceSample,
)
from ai_governance_api.models import (
    Agent,
    AISystem,
    RuntimeAssuranceEvaluationEntry,
    RuntimeAssurancePolicyEntry,
    RuntimeTelemetryEventEntry,
)


class SqlAlchemyRuntimeAssuranceRepository(RuntimeAssuranceRepositoryPort):
    """Read telemetry and persist policy/evaluation evidence in one request transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_scope(
        self, agent_id: str, *, for_update: bool = False
    ) -> RuntimeAssuranceScope | None:
        """Return trusted Agent/system ownership and aggregate binding."""
        statement = (
            select(Agent, AISystem)
            .join(AISystem, Agent.ai_system_id == AISystem.id)
            .where(Agent.id == agent_id)
        )
        if for_update:
            statement = statement.with_for_update(of=Agent)
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        agent, system = row
        return RuntimeAssuranceScope(
            agent_id=agent.id,
            ai_system_id=system.id,
            initiative_id=system.initiative_id,
            agent_owner_id=agent.owner_id,
            ai_system_owner_id=system.owner_id,
        )

    async def get_policy(
        self, agent_id: str, *, for_update: bool = False
    ) -> RuntimeAssurancePolicy | None:
        """Return the current persisted assurance policy."""
        statement = select(RuntimeAssurancePolicyEntry).where(
            RuntimeAssurancePolicyEntry.agent_id == agent_id
        )
        if for_update:
            statement = statement.with_for_update()
        entity = await self._session.scalar(statement)
        return _policy_to_domain(entity) if entity is not None else None

    async def save_policy(self, policy: RuntimeAssurancePolicy) -> RuntimeAssurancePolicy:
        """Create or update the versioned assurance policy without committing."""
        entity = await self._session.get(RuntimeAssurancePolicyEntry, policy.agent_id)
        if entity is None:
            entity = RuntimeAssurancePolicyEntry(
                agent_id=policy.agent_id,
                ai_system_id=policy.ai_system_id,
                enabled=policy.enabled,
                lookback_seconds=policy.lookback_seconds,
                evaluation_sample_size=policy.evaluation_sample_size,
                minimum_samples=policy.minimum_samples,
                max_failure_rate=policy.max_failure_rate,
                max_p95_duration_ms=policy.max_p95_duration_ms,
                max_consecutive_failures=policy.max_consecutive_failures,
                breach_severity=policy.breach_severity.value,
                version=policy.version,
                created_at=policy.created_at,
                updated_at=policy.updated_at,
            )
            self._session.add(entity)
        else:
            if policy.version != entity.version + 1:
                raise ValueError("Runtime assurance policy version conflict")
            entity.ai_system_id = policy.ai_system_id
            entity.enabled = policy.enabled
            entity.lookback_seconds = policy.lookback_seconds
            entity.evaluation_sample_size = policy.evaluation_sample_size
            entity.minimum_samples = policy.minimum_samples
            entity.max_failure_rate = policy.max_failure_rate
            entity.max_p95_duration_ms = policy.max_p95_duration_ms
            entity.max_consecutive_failures = policy.max_consecutive_failures
            entity.breach_severity = policy.breach_severity.value
            entity.version = policy.version
            entity.updated_at = policy.updated_at
        await self._session.flush()
        return _policy_to_domain(entity)

    async def list_terminal_samples(
        self,
        agent_id: str,
        *,
        since: datetime,
        until: datetime,
        limit: int,
    ) -> list[RuntimeAssuranceSample]:
        """Return bounded terminal telemetry facts in chronological order."""
        entries = (
            await self._session.scalars(
                select(RuntimeTelemetryEventEntry)
                .where(
                    RuntimeTelemetryEventEntry.agent_id == agent_id,
                    RuntimeTelemetryEventEntry.observed_at >= since,
                    RuntimeTelemetryEventEntry.observed_at <= until,
                    RuntimeTelemetryEventEntry.event_outcome.in_(("success", "failure", "error")),
                )
                .order_by(
                    RuntimeTelemetryEventEntry.observed_at.desc(),
                    RuntimeTelemetryEventEntry.event_id.desc(),
                )
                .limit(limit)
            )
        ).all()
        samples = [
            RuntimeAssuranceSample(
                event_id=entry.event_id,
                observed_at=_as_utc(entry.observed_at),
                event_outcome=entry.event_outcome,
                duration_ms=entry.duration_ms,
            )
            for entry in entries
        ]
        samples.reverse()
        return samples

    async def save_evaluation(
        self, evaluation: RuntimeAssuranceEvaluation
    ) -> RuntimeAssuranceEvaluation:
        """Persist one append-only assurance evaluation without committing."""
        self._session.add(
            RuntimeAssuranceEvaluationEntry(
                id=evaluation.id,
                agent_id=evaluation.agent_id,
                ai_system_id=evaluation.ai_system_id,
                initiative_id=evaluation.initiative_id,
                policy_version=evaluation.policy_version,
                evaluated_at=evaluation.evaluated_at,
                window_started_at=evaluation.window_started_at,
                window_ended_at=evaluation.window_ended_at,
                sample_count=evaluation.sample_count,
                duration_sample_count=evaluation.duration_sample_count,
                failure_count=evaluation.failure_count,
                failure_rate=evaluation.failure_rate,
                p95_duration_ms=evaluation.p95_duration_ms,
                max_consecutive_failures=evaluation.max_consecutive_failures,
                outcome=evaluation.outcome.value,
                breach_reasons=[reason.value for reason in evaluation.breach_reasons],
                severity=evaluation.severity.value if evaluation.severity else None,
                source_event_ids=list(evaluation.source_event_ids),
                evidence_digest=evaluation.evidence_digest,
                version=evaluation.version,
            )
        )
        await self._session.flush()
        return evaluation

    async def list_evaluations(
        self, agent_id: str, *, limit: int
    ) -> list[RuntimeAssuranceEvaluation]:
        """Return recent persisted assurance evaluations."""
        entries = (
            await self._session.scalars(
                select(RuntimeAssuranceEvaluationEntry)
                .where(RuntimeAssuranceEvaluationEntry.agent_id == agent_id)
                .order_by(
                    RuntimeAssuranceEvaluationEntry.evaluated_at.desc(),
                    RuntimeAssuranceEvaluationEntry.id.desc(),
                )
                .limit(limit)
            )
        ).all()
        return [_evaluation_to_domain(entry) for entry in entries]


class SqlAlchemyRuntimeAssuranceAudit(RuntimeAssuranceAuditPort):
    """Append minimized policy/evaluation facts to the shared hash chain."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        entity_version: int,
        payload: dict[str, object],
    ) -> None:
        """Append minimized assurance evidence to the shared audit chain."""
        await append_audit_event(
            self._session,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_version=entity_version,
            payload=payload,
        )


def _policy_to_domain(
    entity: RuntimeAssurancePolicyEntry,
) -> RuntimeAssurancePolicy:
    return RuntimeAssurancePolicy(
        agent_id=entity.agent_id,
        ai_system_id=entity.ai_system_id,
        enabled=entity.enabled,
        lookback_seconds=entity.lookback_seconds,
        evaluation_sample_size=entity.evaluation_sample_size,
        minimum_samples=entity.minimum_samples,
        max_failure_rate=entity.max_failure_rate,
        max_p95_duration_ms=entity.max_p95_duration_ms,
        max_consecutive_failures=entity.max_consecutive_failures,
        breach_severity=RiskTier(entity.breach_severity),
        version=entity.version,
        created_at=_as_utc(entity.created_at),
        updated_at=_as_utc(entity.updated_at),
    )


def _evaluation_to_domain(
    entity: RuntimeAssuranceEvaluationEntry,
) -> RuntimeAssuranceEvaluation:
    return RuntimeAssuranceEvaluation(
        id=entity.id,
        agent_id=entity.agent_id,
        ai_system_id=entity.ai_system_id,
        initiative_id=entity.initiative_id,
        policy_version=entity.policy_version,
        evaluated_at=_as_utc(entity.evaluated_at),
        window_started_at=_as_utc(entity.window_started_at),
        window_ended_at=_as_utc(entity.window_ended_at),
        sample_count=entity.sample_count,
        duration_sample_count=entity.duration_sample_count,
        failure_count=entity.failure_count,
        failure_rate=entity.failure_rate,
        p95_duration_ms=entity.p95_duration_ms,
        max_consecutive_failures=entity.max_consecutive_failures,
        outcome=RuntimeAssuranceOutcome(entity.outcome),
        breach_reasons=tuple(
            RuntimeAssuranceBreachReason(value) for value in entity.breach_reasons
        ),
        severity=RiskTier(entity.severity) if entity.severity is not None else None,
        source_event_ids=tuple(entity.source_event_ids),
        evidence_digest=entity.evidence_digest,
        version=entity.version,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
