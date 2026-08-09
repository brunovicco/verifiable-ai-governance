"""Governed creation and retrieval of append-only actuation approval requests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import (
    RUNTIME_ASSURANCE_ACTUATION_REQUEST_SCHEMA_VERSION,
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationDomainError,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationRequestState,
    RuntimeAssuranceActuationSourceContext,
    build_actuation_request_digest,
    derive_actuation_action,
    validate_actuation_request_binding,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


class RuntimeAssuranceActuationRequestRepositoryPort(Protocol):
    """Persistence boundary for trusted recommendation lineage and immutable requests."""

    async def get_context(
        self,
        recommendation_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceActuationSourceContext | None:
        """Return trusted lineage and ownership for one recommendation."""
        ...

    async def get_request_by_recommendation_action(
        self,
        recommendation_id: str,
        action: RuntimeAssuranceActuationAction,
    ) -> RuntimeAssuranceActuationRequest | None:
        """Return the idempotent request for one recommendation/action pair."""
        ...

    async def save_request(
        self,
        request: RuntimeAssuranceActuationRequest,
    ) -> RuntimeAssuranceActuationRequest:
        """Persist immutable request genesis evidence without committing."""
        ...


class RuntimeAssuranceActuationAuditPort(Protocol):
    """Append content-minimized actuation-request evidence to the shared audit chain."""

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
        """Append one actuation-request event inside the surrounding transaction."""
        ...


class RuntimeAssuranceActuationTransactionPort(Protocol):
    """Transaction boundary shared by immutable request and audit writes."""

    async def commit(self) -> None:
        """Commit request evidence and its audit event."""
        ...

    async def rollback(self) -> None:
        """Roll back the current request transaction."""
        ...


class RuntimeAssuranceActuationRequestService:
    """Create governed intent only; this service has no runtime-control dependency."""

    def __init__(
        self,
        repository: RuntimeAssuranceActuationRequestRepositoryPort,
        audit: RuntimeAssuranceActuationAuditPort,
        transaction: RuntimeAssuranceActuationTransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self._repository = repository
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def create(
        self,
        *,
        recommendation_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceActuationRequest:
        """Create or replay one immutable pending approval request."""
        context = await self._load_context(recommendation_id, for_update=True)
        try:
            self._require_system_owner_or_admin(context, principal)
            action = self._derive_action(context)
        except ApplicationError:
            await self._transaction.rollback()
            raise

        existing = await self._repository.get_request_by_recommendation_action(
            recommendation_id,
            action,
        )
        if existing is not None:
            try:
                self._validate_existing(existing, context, action)
            except ApplicationError:
                await self._transaction.rollback()
                raise
            await self._transaction.commit()
            return existing

        if context.current_incident_status is IncidentStatus.CLOSED:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Cannot create an actuation request for a closed incident",
            )

        requested_at = self._clock()
        request_id = self._id_factory()
        state = RuntimeAssuranceActuationRequestState.PENDING
        try:
            request_digest = build_actuation_request_digest(
                request_id=request_id,
                recommendation_id=context.recommendation_id,
                recommendation_digest=context.recommendation_digest,
                promotion_id=context.promotion_id,
                evaluation_id=context.evaluation_id,
                incident_id=context.incident_id,
                agent_id=context.agent_id,
                ai_system_id=context.ai_system_id,
                action=action,
                state=state,
                requested_by=principal.user_id,
                requested_at=requested_at,
            )
        except RuntimeAssuranceActuationDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime Assurance actuation request evidence is invalid",
            ) from exc
        request = RuntimeAssuranceActuationRequest(
            id=request_id,
            schema_version=RUNTIME_ASSURANCE_ACTUATION_REQUEST_SCHEMA_VERSION,
            recommendation_id=context.recommendation_id,
            recommendation_digest=context.recommendation_digest,
            promotion_id=context.promotion_id,
            evaluation_id=context.evaluation_id,
            incident_id=context.incident_id,
            agent_id=context.agent_id,
            ai_system_id=context.ai_system_id,
            action=action,
            state=state,
            requested_by=principal.user_id,
            requested_at=requested_at,
            request_digest=request_digest,
        )

        try:
            stored = await self._repository.save_request(request)
            await self._audit.append(
                actor_id=principal.user_id,
                action="runtime_assurance.actuation_requested",
                entity_type="runtime_assurance_actuation_request",
                entity_id=stored.id,
                entity_version=stored.version,
                payload={
                    "recommendation_id": stored.recommendation_id,
                    "agent_id": stored.agent_id,
                    "ai_system_id": stored.ai_system_id,
                    "action": stored.action.value,
                    "request_digest": stored.request_digest,
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
        recommendation_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceActuationRequest:
        """Return immutable approval-request evidence to an authorized stakeholder."""
        context = await self._load_context(recommendation_id)
        self._require_system_owner_or_admin(context, principal)
        action = self._derive_action(context)
        request = await self._repository.get_request_by_recommendation_action(
            recommendation_id,
            action,
        )
        if request is None:
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime Assurance actuation request not found",
            )
        self._validate_existing(request, context, action)
        return request

    async def _load_context(
        self,
        recommendation_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceActuationSourceContext:
        try:
            context = await self._repository.get_context(
                recommendation_id,
                for_update=for_update,
            )
        except (RuntimeAssuranceActuationDomainError, ValueError) as exc:
            if for_update:
                await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime Assurance actuation source binding is inconsistent",
            ) from exc
        if context is None:
            if for_update:
                await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime response recommendation not found",
            )
        return context

    def _derive_action(
        self,
        context: RuntimeAssuranceActuationSourceContext,
    ) -> RuntimeAssuranceActuationAction:
        try:
            return derive_actuation_action(context)
        except RuntimeAssuranceActuationDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc

    @staticmethod
    def _validate_existing(
        request: RuntimeAssuranceActuationRequest,
        context: RuntimeAssuranceActuationSourceContext,
        action: RuntimeAssuranceActuationAction,
    ) -> None:
        try:
            validate_actuation_request_binding(request, context, action)
        except RuntimeAssuranceActuationDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc

    @staticmethod
    def _require_system_owner_or_admin(
        context: RuntimeAssuranceActuationSourceContext,
        principal: Principal,
    ) -> None:
        if principal.user_id != context.ai_system_owner_id and not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the AI system owner or an administrator can create actuation requests",
            )
