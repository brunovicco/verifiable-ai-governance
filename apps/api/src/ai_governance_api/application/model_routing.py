"""Governed model-routing use cases and consumer-owned integration ports."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.model_routing import (
    GovernedRoutingScope,
    ModelRoutingCommand,
    ModelRoutingDecisionRecord,
    PolicyModelRouterDecision,
    PolicyModelRouterRequest,
    RouterDecisionOutcome,
    RoutingBlock,
    RoutingBlockCode,
    RoutingDecisionSource,
    RoutingEnforcementOutcome,
    build_router_request,
    enforce_router_decision,
    evaluate_routing_scope,
    finalize_routing_record,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


class ModelRouterUnavailable(RuntimeError):
    """Raised when the external policy decision point cannot be trusted."""


class ModelRoutingScopeReaderPort(Protocol):
    """Read fresh runtime authorization facts from the governed registry."""

    async def get(self, agent_id: str) -> GovernedRoutingScope | None:
        """Return one agent's trusted routing scope or ``None`` when absent."""
        ...


class PolicyModelRouterPort(Protocol):
    """External policy decision point consumed by the routing use case."""

    async def decide(
        self,
        request: PolicyModelRouterRequest,
        *,
        correlation_id: str,
    ) -> PolicyModelRouterDecision:
        """Return a validated accepted or rejected policy decision."""
        ...


class ModelRoutingDecisionStorePort(Protocol):
    """Persist and query durable routing evidence."""

    async def save(
        self,
        record: ModelRoutingDecisionRecord,
    ) -> ModelRoutingDecisionRecord:
        """Insert or finalize one routing record without committing."""
        ...

    async def list_for_agent(self, agent_id: str) -> list[ModelRoutingDecisionRecord]:
        """Return routing evidence for one agent in reverse chronological order."""
        ...


class ModelRoutingAuditPort(Protocol):
    """Append content-minimized routing events to the audit chain."""

    async def append(
        self,
        *,
        actor_id: str,
        action: str,
        record: ModelRoutingDecisionRecord,
    ) -> None:
        """Append one lifecycle event in the surrounding transaction."""
        ...


class ModelRoutingTransactionPort(Protocol):
    """Transaction boundary for routing evidence and audit events."""

    async def commit(self) -> None:
        """Commit pending evidence and audit changes atomically."""
        ...

    async def rollback(self) -> None:
        """Discard pending changes after a persistence failure."""
        ...


class RequestModelRoutingDecision:
    """Enforce registry scope around one external model-routing decision."""

    def __init__(
        self,
        scope_reader: ModelRoutingScopeReaderPort,
        router: PolicyModelRouterPort,
        store: ModelRoutingDecisionStorePort,
        audit: ModelRoutingAuditPort,
        transaction: ModelRoutingTransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize the use case with explicit I/O boundaries and test seams."""
        self._scope_reader = scope_reader
        self._router = router
        self._store = store
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def execute(
        self,
        *,
        agent_id: str,
        command: ModelRoutingCommand,
        principal: Principal,
    ) -> ModelRoutingDecisionRecord:
        """Persist intent, obtain a policy decision, and enforce fresh registry scope."""
        scope = await self._require_authorized_scope(agent_id, principal)
        requested_at = self._clock()
        record = self._new_record(scope, command, principal, requested_at)
        await self._persist(record, action="model_routing.requested")

        block = evaluate_routing_scope(scope, command, now=requested_at)
        if block is not None:
            return await self._finalize(
                record,
                principal=principal,
                outcome=RoutingEnforcementOutcome.BLOCKED,
                source=RoutingDecisionSource.GOVERNANCE_REGISTRY,
                block=block,
            )

        request = build_router_request(scope, command, requested_at=requested_at)
        try:
            provider_decision = await self._router.decide(
                request,
                correlation_id=record.id,
            )
        except ModelRouterUnavailable:
            return await self._finalize(
                record,
                principal=principal,
                outcome=RoutingEnforcementOutcome.DEPENDENCY_UNAVAILABLE,
                source=RoutingDecisionSource.POLICY_MODEL_ROUTER,
                block=RoutingBlock(
                    RoutingBlockCode.ROUTER_UNAVAILABLE,
                    "Model routing dependency is unavailable or returned an untrusted response",
                ),
            )

        current_scope = await self._scope_reader.get(agent_id)
        block = (
            RoutingBlock(
                RoutingBlockCode.REGISTRY_SCOPE_CHANGED,
                "Governed registry scope disappeared while routing was in progress",
            )
            if current_scope is None
            else enforce_router_decision(
                current_scope,
                command,
                provider_decision,
                expected_scope_digest=record.scope_digest,
                now=self._clock(),
            )
        )
        return await self._finalize(
            record,
            principal=principal,
            outcome=(
                RoutingEnforcementOutcome.ALLOWED
                if block is None
                else RoutingEnforcementOutcome.BLOCKED
            ),
            source=(
                RoutingDecisionSource.POLICY_MODEL_ROUTER
                if provider_decision.outcome is RouterDecisionOutcome.REJECTED or block is None
                else RoutingDecisionSource.GOVERNANCE_REGISTRY
            ),
            block=block,
            provider_decision=provider_decision,
        )

    async def _require_authorized_scope(
        self,
        agent_id: str,
        principal: Principal,
    ) -> GovernedRoutingScope:
        """Require a registered agent and an owner-authorized caller."""
        scope = await self._scope_reader.get(agent_id)
        if scope is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Agent not found")
        if principal.user_id not in {
            scope.ai_system_owner_id,
            scope.agent_owner_id,
        } and not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the system owner, agent owner, or an administrator can request routing",
            )
        return scope

    def _new_record(
        self,
        scope: GovernedRoutingScope,
        command: ModelRoutingCommand,
        principal: Principal,
        now: datetime,
    ) -> ModelRoutingDecisionRecord:
        """Create the pending evidence persisted before external I/O."""
        return ModelRoutingDecisionRecord(
            id=self._id_factory(),
            ai_system_id=scope.ai_system_id,
            initiative_id=scope.initiative_id,
            agent_id=scope.agent_id,
            requested_by=principal.user_id,
            requested_at=now,
            scope_digest=scope.digest,
            command=command,
            risk_level=scope.risk_tier,
            data_classification=scope.data_classification,
            outcome=RoutingEnforcementOutcome.PENDING,
            decision_source=None,
            router_decision_id=None,
            router_outcome=None,
            decided_at=None,
            selected_model_group=None,
            rejected_model_group=None,
            reason=None,
            reason_code=None,
            observed_value=None,
            required_value=None,
            rejected_candidates=(),
            policy_id=None,
            policy_version=None,
            policy_digest=None,
            service_version=None,
            environment=None,
            version=1,
            created_at=now,
            updated_at=now,
        )

    async def _finalize(
        self,
        record: ModelRoutingDecisionRecord,
        *,
        principal: Principal,
        outcome: RoutingEnforcementOutcome,
        source: RoutingDecisionSource,
        block: RoutingBlock | None,
        provider_decision: PolicyModelRouterDecision | None = None,
    ) -> ModelRoutingDecisionRecord:
        """Finalize a pending attempt and append its enforcement audit event."""
        completed = finalize_routing_record(
            record,
            outcome=outcome,
            source=source,
            decided_at=self._clock(),
            block=block,
            provider_decision=provider_decision,
        )
        return await self._persist(
            completed,
            action=(
                "model_routing.allowed"
                if outcome is RoutingEnforcementOutcome.ALLOWED
                else "model_routing.blocked"
            ),
            actor_id=principal.user_id,
        )

    async def _persist(
        self,
        record: ModelRoutingDecisionRecord,
        *,
        action: str,
        actor_id: str | None = None,
    ) -> ModelRoutingDecisionRecord:
        """Persist record and audit atomically, rolling back on any failure."""
        try:
            stored = await self._store.save(record)
            await self._audit.append(
                actor_id=actor_id or record.requested_by,
                action=action,
                record=stored,
            )
            await self._transaction.commit()
            return stored
        except Exception:
            await self._transaction.rollback()
            raise


class ListModelRoutingDecisions:
    """List routing evidence after enforcing the same agent ownership boundary."""

    def __init__(
        self,
        scope_reader: ModelRoutingScopeReaderPort,
        store: ModelRoutingDecisionStorePort,
    ) -> None:
        """Initialize the query with replaceable read ports."""
        self._scope_reader = scope_reader
        self._store = store

    async def execute(
        self,
        *,
        agent_id: str,
        principal: Principal,
    ) -> list[ModelRoutingDecisionRecord]:
        """Return persisted attempts for an authorized agent stakeholder."""
        scope = await self._scope_reader.get(agent_id)
        if scope is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Agent not found")
        if principal.user_id not in {
            scope.ai_system_owner_id,
            scope.agent_owner_id,
        } and not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the system owner, agent owner, or an administrator can view routing",
            )
        return await self._store.list_for_agent(agent_id)
