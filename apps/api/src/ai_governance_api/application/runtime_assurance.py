"""Governed runtime-assurance policy and deterministic evaluation use cases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from governance_schemas import RiskTier

from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.runtime_assurance import (
    RuntimeAssuranceEvaluation,
    RuntimeAssurancePolicy,
    RuntimeAssuranceSample,
    evaluate_runtime_assurance,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]


class RuntimeAssuranceScope:
    """Trusted ownership and aggregate binding for one Agent."""

    __slots__ = (
        "agent_id",
        "ai_system_id",
        "initiative_id",
        "agent_owner_id",
        "ai_system_owner_id",
    )

    def __init__(
        self,
        *,
        agent_id: str,
        ai_system_id: str,
        initiative_id: str,
        agent_owner_id: str,
        ai_system_owner_id: str,
    ) -> None:
        self.agent_id = agent_id
        self.ai_system_id = ai_system_id
        self.initiative_id = initiative_id
        self.agent_owner_id = agent_owner_id
        self.ai_system_owner_id = ai_system_owner_id


class RuntimeAssuranceRepositoryPort(Protocol):
    """Persistence/query boundary for runtime assurance."""

    async def get_scope(
        self, agent_id: str, *, for_update: bool = False
    ) -> RuntimeAssuranceScope | None:
        """Return the trusted governed scope for one Agent."""
        ...

    async def get_policy(
        self, agent_id: str, *, for_update: bool = False
    ) -> RuntimeAssurancePolicy | None:
        """Return the current assurance policy for one Agent."""
        ...

    async def save_policy(self, policy: RuntimeAssurancePolicy) -> RuntimeAssurancePolicy:
        """Persist the current versioned assurance policy."""
        ...

    async def list_terminal_samples(
        self,
        agent_id: str,
        *,
        since: datetime,
        until: datetime,
        limit: int,
    ) -> list[RuntimeAssuranceSample]:
        """Return bounded terminal telemetry samples for evaluation."""
        ...

    async def save_evaluation(
        self, evaluation: RuntimeAssuranceEvaluation
    ) -> RuntimeAssuranceEvaluation:
        """Persist one append-only assurance evaluation."""
        ...

    async def list_evaluations(
        self, agent_id: str, *, limit: int
    ) -> list[RuntimeAssuranceEvaluation]:
        """Return recent assurance evaluations for one Agent."""
        ...


class RuntimeAssuranceAuditPort(Protocol):
    """Append minimized runtime-assurance facts to the audit chain."""

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
        """Append minimized assurance facts to the shared audit chain."""
        ...


class RuntimeAssuranceTransactionPort(Protocol):
    """Transaction boundary shared by assurance evidence and audit."""

    async def commit(self) -> None:
        """Commit the assurance evidence transaction."""
        ...

    async def rollback(self) -> None:
        """Roll back the assurance evidence transaction."""
        ...


class RuntimeAssuranceService:
    """Manage Agent assurance policy and execute deterministic evaluations."""

    def __init__(
        self,
        repository: RuntimeAssuranceRepositoryPort,
        audit: RuntimeAssuranceAuditPort,
        transaction: RuntimeAssuranceTransactionPort,
        *,
        clock: Clock | None = None,
        evaluation_list_limit: int = 100,
    ) -> None:
        self._repository = repository
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._evaluation_list_limit = evaluation_list_limit

    async def put_policy(
        self,
        *,
        agent_id: str,
        enabled: bool,
        lookback_seconds: int,
        evaluation_sample_size: int,
        minimum_samples: int,
        max_failure_rate: float,
        max_p95_duration_ms: float | None,
        max_consecutive_failures: int | None,
        breach_severity: RiskTier,
        expected_version: int | None,
        principal: Principal,
    ) -> RuntimeAssurancePolicy:
        """Create or replace one versioned Agent policy using optimistic concurrency."""
        scope = await self._require_scope(agent_id, principal, for_update=True)
        current = await self._repository.get_policy(agent_id, for_update=True)
        if current is None:
            if expected_version is not None:
                raise ApplicationError(
                    ErrorKind.CONFLICT,
                    "Runtime assurance policy does not exist at expected version",
                )
            version = 1
            created_at = self._clock()
            action = "runtime_assurance.policy_created"
        else:
            if expected_version is None or expected_version != current.version:
                raise ApplicationError(
                    ErrorKind.CONFLICT,
                    "Runtime assurance policy version conflict",
                )
            version = current.version + 1
            created_at = current.created_at
            action = "runtime_assurance.policy_updated"

        now = self._clock()
        policy = RuntimeAssurancePolicy(
            agent_id=scope.agent_id,
            ai_system_id=scope.ai_system_id,
            enabled=enabled,
            lookback_seconds=lookback_seconds,
            evaluation_sample_size=evaluation_sample_size,
            minimum_samples=minimum_samples,
            max_failure_rate=max_failure_rate,
            max_p95_duration_ms=max_p95_duration_ms,
            max_consecutive_failures=max_consecutive_failures,
            breach_severity=breach_severity,
            version=version,
            created_at=created_at,
            updated_at=now,
        )
        try:
            stored = await self._repository.save_policy(policy)
            await self._audit.append(
                actor_id=principal.user_id,
                action=action,
                entity_type="runtime_assurance_policy",
                entity_id=scope.agent_id,
                entity_version=stored.version,
                payload={
                    "agent_id": stored.agent_id,
                    "ai_system_id": stored.ai_system_id,
                    "enabled": stored.enabled,
                    "policy_version": stored.version,
                },
            )
            await self._transaction.commit()
            return stored
        except Exception:
            await self._transaction.rollback()
            raise

    async def get_policy(self, *, agent_id: str, principal: Principal) -> RuntimeAssurancePolicy:
        """Return the current policy to an authorized stakeholder."""
        await self._require_scope(agent_id, principal)
        policy = await self._repository.get_policy(agent_id)
        if policy is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Runtime assurance policy not found")
        return policy

    async def evaluate(self, *, agent_id: str, principal: Principal) -> RuntimeAssuranceEvaluation:
        """Evaluate a bounded telemetry window and persist append-only evidence."""
        scope = await self._require_scope(agent_id, principal)
        policy = await self._repository.get_policy(agent_id)
        if policy is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Runtime assurance policy not found")
        if not policy.enabled:
            raise ApplicationError(ErrorKind.CONFLICT, "Runtime assurance policy is disabled")

        evaluated_at = self._clock()
        samples = await self._repository.list_terminal_samples(
            agent_id,
            since=evaluated_at - timedelta(seconds=policy.lookback_seconds),
            until=evaluated_at,
            limit=policy.evaluation_sample_size,
        )
        evaluation = evaluate_runtime_assurance(
            evaluation_id=str(uuid4()),
            initiative_id=scope.initiative_id,
            policy=policy,
            samples=samples,
            evaluated_at=evaluated_at,
        )
        try:
            stored = await self._repository.save_evaluation(evaluation)
            await self._audit.append(
                actor_id=principal.user_id,
                action="runtime_assurance.evaluated",
                entity_type="runtime_assurance_evaluation",
                entity_id=stored.id,
                entity_version=stored.version,
                payload={
                    "agent_id": stored.agent_id,
                    "ai_system_id": stored.ai_system_id,
                    "policy_version": stored.policy_version,
                    "outcome": stored.outcome.value,
                    "severity": stored.severity.value if stored.severity else None,
                    "breach_reasons": [reason.value for reason in stored.breach_reasons],
                    "evidence_digest": stored.evidence_digest,
                },
            )
            await self._transaction.commit()
            return stored
        except Exception:
            await self._transaction.rollback()
            raise

    async def list_evaluations(
        self, *, agent_id: str, principal: Principal
    ) -> list[RuntimeAssuranceEvaluation]:
        """List recent append-only assurance evidence for an Agent."""
        await self._require_scope(agent_id, principal)
        return await self._repository.list_evaluations(agent_id, limit=self._evaluation_list_limit)

    async def _require_scope(
        self,
        agent_id: str,
        principal: Principal,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceScope:
        scope = await self._repository.get_scope(agent_id, for_update=for_update)
        if scope is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Agent not found")
        if (
            principal.user_id not in {scope.agent_owner_id, scope.ai_system_owner_id}
            and not principal.is_admin
        ):
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the system owner, agent owner, or an administrator "
                "can manage runtime assurance",
            )
        return scope
