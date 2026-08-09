"""Human approval and rejection evidence for governed Runtime Assurance actuation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from governance_schemas import ApprovalArea

from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation_decisions import (
    RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA,
    RUNTIME_ASSURANCE_ACTUATION_DECISION_SCHEMA_VERSION,
    RuntimeAssuranceActuationDecision,
    RuntimeAssuranceActuationDecisionContext,
    RuntimeAssuranceActuationDecisionDomainError,
    RuntimeAssuranceActuationDecisionOutcome,
    build_actuation_decision_digest,
    normalize_actuation_decision_reason,
    validate_actuation_decision_binding,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


class RuntimeAssuranceActuationDecisionRepositoryPort(Protocol):
    """Persistence boundary for trusted actuation requests and terminal decisions."""

    async def get_context(
        self,
        request_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceActuationDecisionContext | None:
        """Return one validated request and lineage context."""
        ...

    async def get_decision_by_request_id(
        self,
        request_id: str,
    ) -> RuntimeAssuranceActuationDecision | None:
        """Return the terminal decision for one request, when present."""
        ...

    async def save_decision(
        self,
        decision: RuntimeAssuranceActuationDecision,
    ) -> RuntimeAssuranceActuationDecision:
        """Persist immutable terminal decision evidence without committing."""
        ...


class RuntimeAssuranceActuationDecisionAuditPort(Protocol):
    """Append content-minimized human decision evidence to the shared audit chain."""

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
        """Append one human decision event inside the surrounding transaction."""
        ...


class RuntimeAssuranceActuationDecisionTransactionPort(Protocol):
    """Transaction boundary shared by decision and audit writes."""

    async def commit(self) -> None:
        """Commit decision evidence and its audit event."""
        ...

    async def rollback(self) -> None:
        """Roll back the current decision transaction."""
        ...


class RuntimeAssuranceActuationDecisionService:
    """Record an independent human decision without invoking runtime actuation."""

    def __init__(
        self,
        repository: RuntimeAssuranceActuationDecisionRepositoryPort,
        audit: RuntimeAssuranceActuationDecisionAuditPort,
        transaction: RuntimeAssuranceActuationDecisionTransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize the service with evidence-only ports and deterministic seams."""
        self._repository = repository
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def decide(
        self,
        *,
        request_id: str,
        decision: RuntimeAssuranceActuationDecisionOutcome,
        reason: str,
        principal: Principal,
    ) -> RuntimeAssuranceActuationDecision:
        """Create or replay one independent terminal approval/rejection decision."""
        context = await self._load_context(request_id, for_update=True)
        try:
            self._require_independent_security_approver(context, principal)
        except ApplicationError:
            await self._transaction.rollback()
            raise
        try:
            canonical_reason = normalize_actuation_decision_reason(reason)
        except RuntimeAssuranceActuationDecisionDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.UNPROCESSABLE, str(exc)) from exc

        existing = await self._load_existing_decision(request_id, rollback_on_error=True)
        if existing is not None:
            try:
                self._validate_existing(existing, context)
                self._require_idempotent_replay(
                    existing,
                    decision=decision,
                    reason=canonical_reason,
                    principal=principal,
                )
            except ApplicationError:
                await self._transaction.rollback()
                raise
            await self._transaction.commit()
            return existing

        if (
            decision is RuntimeAssuranceActuationDecisionOutcome.APPROVED
            and context.current_incident_status is IncidentStatus.CLOSED
        ):
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Cannot approve runtime actuation for a closed incident",
            )

        decided_at = self._clock()
        decision_id = self._id_factory()
        request = context.request
        try:
            decision_digest = build_actuation_decision_digest(
                decision_id=decision_id,
                request_id=request.id,
                request_digest=request.request_digest,
                action=request.action,
                decision=decision,
                approval_area=RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA,
                decided_by=principal.user_id,
                decided_at=decided_at,
                reason=canonical_reason,
            )
        except RuntimeAssuranceActuationDecisionDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime Assurance actuation decision evidence is invalid",
            ) from exc

        record = RuntimeAssuranceActuationDecision(
            id=decision_id,
            schema_version=RUNTIME_ASSURANCE_ACTUATION_DECISION_SCHEMA_VERSION,
            request_id=request.id,
            request_digest=request.request_digest,
            action=request.action,
            decision=decision,
            approval_area=RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA,
            decided_by=principal.user_id,
            decided_at=decided_at,
            reason=canonical_reason,
            decision_digest=decision_digest,
        )

        try:
            stored = await self._repository.save_decision(record)
            await self._audit.append(
                actor_id=principal.user_id,
                action=(
                    "runtime_assurance.actuation_approved"
                    if stored.decision is RuntimeAssuranceActuationDecisionOutcome.APPROVED
                    else "runtime_assurance.actuation_rejected"
                ),
                entity_type="runtime_assurance_actuation_decision",
                entity_id=stored.id,
                entity_version=stored.version,
                payload={
                    "request_id": stored.request_id,
                    "agent_id": context.request.agent_id,
                    "ai_system_id": context.request.ai_system_id,
                    "action": stored.action.value,
                    "approval_area": stored.approval_area.value,
                    "decision_digest": stored.decision_digest,
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
        request_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceActuationDecision:
        """Return terminal decision evidence to an authorized stakeholder."""
        context = await self._load_context(request_id)
        self._require_decision_viewer(context, principal)
        decision = await self._load_existing_decision(request_id)
        if decision is None:
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime Assurance actuation decision not found",
            )
        self._validate_existing(decision, context)
        return decision

    async def _load_context(
        self,
        request_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceActuationDecisionContext:
        try:
            context = await self._repository.get_context(
                request_id,
                for_update=for_update,
            )
        except ValueError as exc:
            if for_update:
                await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime Assurance actuation request binding is inconsistent",
            ) from exc
        if context is None:
            if for_update:
                await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime Assurance actuation request not found",
            )
        return context

    async def _load_existing_decision(
        self,
        request_id: str,
        *,
        rollback_on_error: bool = False,
    ) -> RuntimeAssuranceActuationDecision | None:
        try:
            return await self._repository.get_decision_by_request_id(request_id)
        except ValueError as exc:
            if rollback_on_error:
                await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime Assurance actuation decision evidence is invalid",
            ) from exc

    @staticmethod
    def _require_independent_security_approver(
        context: RuntimeAssuranceActuationDecisionContext,
        principal: Principal,
    ) -> None:
        if principal.user_id == context.request.requested_by:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Actuation requester cannot decide their own request",
            )
        if RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA not in principal.approval_areas:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Security approval capability is required for runtime actuation decisions",
            )

    @staticmethod
    def _require_decision_viewer(
        context: RuntimeAssuranceActuationDecisionContext,
        principal: Principal,
    ) -> None:
        request = context.request
        source = context.source
        if (
            principal.user_id != request.requested_by
            and principal.user_id != source.ai_system_owner_id
            and not principal.is_admin
            and RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA not in principal.approval_areas
        ):
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Principal is not authorized to view this actuation decision",
            )

    @staticmethod
    def _validate_existing(
        decision: RuntimeAssuranceActuationDecision,
        context: RuntimeAssuranceActuationDecisionContext,
    ) -> None:
        try:
            validate_actuation_decision_binding(decision, context)
        except RuntimeAssuranceActuationDecisionDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc

    @staticmethod
    def _require_idempotent_replay(
        existing: RuntimeAssuranceActuationDecision,
        *,
        decision: RuntimeAssuranceActuationDecisionOutcome,
        reason: str,
        principal: Principal,
    ) -> None:
        if (
            existing.decision is not decision
            or existing.reason != reason
            or existing.decided_by != principal.user_id
            or existing.approval_area is not RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA
        ):
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Actuation request already has a different terminal decision",
            )


def required_runtime_actuation_approval_area() -> ApprovalArea:
    """Expose the concrete P1.9b approval capability for policy and tests."""
    return RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA
