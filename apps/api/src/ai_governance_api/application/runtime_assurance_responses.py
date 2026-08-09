"""Governed generation of deterministic runtime-response recommendations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_responses import (
    RuntimeAssuranceResponseContext,
    RuntimeAssuranceResponseRecommendation,
    derive_runtime_assurance_response_plan,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


class RuntimeAssuranceResponseRepositoryPort(Protocol):
    """Persistence boundary for recommendation source facts and evidence."""

    async def get_context(
        self,
        promotion_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceResponseContext | None:
        """Return trusted structural facts for one incident promotion."""
        ...

    async def get_recommendation_by_promotion(
        self,
        promotion_id: str,
    ) -> RuntimeAssuranceResponseRecommendation | None:
        """Return an existing idempotent recommendation for one promotion."""
        ...

    async def save_recommendation(
        self,
        recommendation: RuntimeAssuranceResponseRecommendation,
    ) -> RuntimeAssuranceResponseRecommendation:
        """Persist one append-only advisory recommendation."""
        ...


class RuntimeAssuranceResponseAuditPort(Protocol):
    """Append minimized response-recommendation evidence to the audit chain."""

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
        """Append one recommendation event inside the surrounding transaction."""
        ...


class RuntimeAssuranceResponseTransactionPort(Protocol):
    """Transaction boundary shared by recommendation evidence and audit."""

    async def commit(self) -> None:
        """Commit recommendation evidence and its audit event."""
        ...

    async def rollback(self) -> None:
        """Roll back recommendation evidence after a failure."""
        ...


class RuntimeAssuranceResponseService:
    """Generate immutable advisory guidance from promoted assurance evidence."""

    def __init__(
        self,
        repository: RuntimeAssuranceResponseRepositoryPort,
        audit: RuntimeAssuranceResponseAuditPort,
        transaction: RuntimeAssuranceResponseTransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize explicit ports and deterministic test seams."""
        self._repository = repository
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def generate(
        self,
        *,
        promotion_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceResponseRecommendation:
        """Generate or return one immutable advisory recommendation set."""
        context = await self._repository.get_context(
            promotion_id,
            for_update=True,
        )
        if context is None:
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime Assurance incident promotion not found",
            )
        self._require_system_owner_or_admin(context, principal)

        existing = await self._repository.get_recommendation_by_promotion(promotion_id)
        if existing is not None:
            return existing

        if context.incident_status is IncidentStatus.CLOSED:
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Cannot generate runtime response recommendations for a closed incident",
            )

        plan = derive_runtime_assurance_response_plan(context)
        recommendation = RuntimeAssuranceResponseRecommendation(
            id=self._id_factory(),
            promotion_id=context.promotion_id,
            evaluation_id=context.evaluation_id,
            agent_id=context.agent_id,
            ai_system_id=context.ai_system_id,
            incident_id=context.incident_id,
            breach_fingerprint=context.breach_fingerprint,
            source_evidence_digest=context.source_evidence_digest,
            policy_id=plan.policy_id,
            policy_version=plan.policy_version,
            policy_digest=plan.policy_digest,
            incident_status=context.incident_status,
            incident_severity=context.incident_severity,
            incident_version=context.incident_version,
            kill_switch_enabled=context.kill_switch_enabled,
            kill_switch_engaged=context.kill_switch_engaged,
            actions=plan.actions,
            rationale_codes=plan.rationale_codes,
            advisory_only=True,
            generated_by=principal.user_id,
            generated_at=self._clock(),
            recommendation_digest=plan.recommendation_digest,
        )

        try:
            stored = await self._repository.save_recommendation(recommendation)
            await self._audit.append(
                actor_id=principal.user_id,
                action="runtime_assurance.response_recommended",
                entity_type="runtime_assurance_response_recommendation",
                entity_id=stored.id,
                entity_version=stored.version,
                payload={
                    "promotion_id": stored.promotion_id,
                    "evaluation_id": stored.evaluation_id,
                    "incident_id": stored.incident_id,
                    "agent_id": stored.agent_id,
                    "ai_system_id": stored.ai_system_id,
                    "policy_id": stored.policy_id,
                    "policy_version": stored.policy_version,
                    "policy_digest": stored.policy_digest,
                    "actions": [action.value for action in stored.actions],
                    "advisory_only": stored.advisory_only,
                    "source_evidence_digest": stored.source_evidence_digest,
                    "recommendation_digest": stored.recommendation_digest,
                },
            )
            await self._transaction.commit()
            return stored
        except Exception:
            await self._transaction.rollback()
            raise

    async def get(
        self,
        *,
        promotion_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceResponseRecommendation:
        """Return persisted recommendation evidence to an authorized stakeholder."""
        context = await self._repository.get_context(promotion_id)
        if context is None:
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime Assurance incident promotion not found",
            )
        self._require_system_owner_or_admin(context, principal)
        recommendation = await self._repository.get_recommendation_by_promotion(promotion_id)
        if recommendation is None:
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime response recommendation not found",
            )
        return recommendation

    def _require_system_owner_or_admin(
        self,
        context: RuntimeAssuranceResponseContext,
        principal: Principal,
    ) -> None:
        if principal.user_id != context.ai_system_owner_id and not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the AI system owner or an administrator "
                "can generate runtime response recommendations",
            )
