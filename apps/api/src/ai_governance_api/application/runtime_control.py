"""Emergency runtime-control commands, reconciliation, and issuance gating."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.runtime_control import (
    RuntimeControlAgentContext,
    RuntimeControlDomainError,
    RuntimeControlDurableState,
    RuntimeControlIncidentContext,
    RuntimeControlResult,
    RuntimeControlSnapshot,
    RuntimeControlState,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
    RuntimeControlUnavailable,
    validate_transition,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

Clock = Callable[[], datetime]
IdFactory = Callable[[], str]


class RuntimeControlRepositoryPort(Protocol):
    """Mutate durable transition and agent state inside caller-owned transactions."""

    async def get_agent_for_update(
        self,
        agent_id: str,
        *,
        incident_id: str | None,
    ) -> tuple[RuntimeControlAgentContext, RuntimeControlIncidentContext | None] | None:
        """Lock an agent and optionally validate an incident in the same AI system."""
        ...

    async def get_latest_transition_for_update(
        self,
        agent_id: str,
    ) -> RuntimeControlTransitionRecord | None:
        """Return the newest transition while the caller holds the agent lock."""
        ...

    async def get_transition(
        self,
        transition_id: str,
    ) -> RuntimeControlTransitionRecord | None:
        """Read one transition without changing the command lock order."""
        ...

    async def get_transition_for_update(
        self,
        transition_id: str,
    ) -> RuntimeControlTransitionRecord | None:
        """Lock one durable transition after its Agent row is locked."""
        ...

    async def save_transition(
        self,
        transition: RuntimeControlTransitionRecord,
    ) -> RuntimeControlTransitionRecord:
        """Insert or advance one transition without committing."""
        ...

    async def apply_agent_state(
        self,
        context: RuntimeControlAgentContext,
        *,
        engaged: bool,
        actor_id: str,
        changed_at: datetime,
    ) -> RuntimeControlAgentContext:
        """Apply the effective state and increment the agent optimistic version."""
        ...

    async def list_pending(self, *, limit: int) -> list[RuntimeControlTransitionRecord]:
        """Return pending transitions oldest first."""
        ...


class RuntimeControlStateReaderPort(Protocol):
    """Read authoritative state without retaining a DB session across network I/O."""

    async def get_durable_state(self, agent_id: str) -> RuntimeControlDurableState | None:
        """Return the expected runtime projection for one agent."""
        ...


class RuntimeControlProjectionPort(Protocol):
    """Maintain a monotonic shared runtime-control projection."""

    async def ping(self) -> None:
        """Require the projection backend to be reachable."""
        ...

    async def read(self, agent_id: str) -> RuntimeControlSnapshot | None:
        """Return the observed snapshot, if present."""
        ...

    async def project(self, snapshot: RuntimeControlSnapshot) -> None:
        """Apply a snapshot using monotonic control-epoch compare-and-set semantics."""
        ...

    async def close(self) -> None:
        """Release owned resources."""
        ...


class RuntimeControlAuditPort(Protocol):
    """Append content-minimized transition events to the audit chain."""

    async def append(
        self,
        *,
        actor_id: str,
        action: str,
        transition: RuntimeControlTransitionRecord,
    ) -> None:
        """Append one runtime-control event inside the surrounding transaction."""
        ...


class RuntimeControlTransactionPort(Protocol):
    """Transaction boundary shared by transition, agent, and audit writes."""

    async def commit(self) -> None:
        """Commit the current transaction."""
        ...

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        ...


class RuntimeControlGate:
    """Verify that DB state and runtime projection agree before authorization issuance."""

    def __init__(
        self,
        reader: RuntimeControlStateReaderPort,
        projection: RuntimeControlProjectionPort,
    ) -> None:
        """Bind the authoritative reader and shared projection."""
        self._reader = reader
        self._projection = projection

    async def state_for(self, agent_id: str) -> RuntimeControlState:
        """Return trusted state, repairing only provably stale or missing projections."""
        durable = await self._reader.get_durable_state(agent_id)
        if durable is None:
            raise RuntimeControlUnavailable("Runtime-control durable state is unavailable")
        if durable.pending_transition_id is not None or not durable.durable_consistent:
            raise RuntimeControlUnavailable("Runtime-control transition is not fully reconciled")

        expected = durable.snapshot
        observed = await self._projection.read(agent_id)
        if observed is None or observed.control_epoch < expected.control_epoch:
            await self._projection.project(expected)
            observed = await self._projection.read(agent_id)
        if observed != expected:
            raise RuntimeControlUnavailable("Runtime-control projection differs from durable state")
        return expected.state


class RuntimeControlService:
    """Create monotonic kill-switch transitions and repair incomplete projections."""

    def __init__(
        self,
        repository: RuntimeControlRepositoryPort,
        projection: RuntimeControlProjectionPort,
        audit: RuntimeControlAuditPort,
        transaction: RuntimeControlTransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize the service with explicit persistence and projection boundaries."""
        self._repository = repository
        self._projection = projection
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def activate(
        self,
        *,
        agent_id: str,
        expected_version: int,
        reason: str,
        principal: Principal,
        incident_id: str | None = None,
        evidence_reference: str | None = None,
    ) -> RuntimeControlResult:
        """Immediately request and project an emergency stop for one agent."""
        return await self._change(
            agent_id=agent_id,
            expected_version=expected_version,
            reason=reason,
            principal=principal,
            target_state=RuntimeControlState.ACTIVE,
            incident_id=incident_id,
            evidence_reference=evidence_reference,
        )

    async def deactivate(
        self,
        *,
        agent_id: str,
        expected_version: int,
        reason: str,
        principal: Principal,
        incident_id: str | None = None,
        evidence_reference: str | None = None,
    ) -> RuntimeControlResult:
        """Restore an agent while keeping all pre-restore authorizations revoked."""
        return await self._change(
            agent_id=agent_id,
            expected_version=expected_version,
            reason=reason,
            principal=principal,
            target_state=RuntimeControlState.INACTIVE,
            incident_id=incident_id,
            evidence_reference=evidence_reference,
        )

    async def reconcile_pending(
        self,
        *,
        principal: Principal,
        limit: int,
    ) -> list[RuntimeControlResult]:
        """Idempotently finish pending transitions after partial infrastructure failures."""
        if not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only an administrator can reconcile runtime-control transitions",
            )
        if not 1 <= limit <= 1000:
            raise ApplicationError(ErrorKind.UNPROCESSABLE, "Reconcile limit must be 1..1000")
        pending = await self._repository.list_pending(limit=limit)
        # Close the read transaction before any external projection call.
        await self._transaction.commit()
        results: list[RuntimeControlResult] = []
        for transition in pending:
            try:
                await self._projection.project(_snapshot_for_transition(transition))
            except RuntimeControlUnavailable as exc:
                raise _projection_unavailable_error() from exc
            result = await self._finalize_transition(
                transition.id,
                reconciled_by=principal.user_id,
            )
            results.append(result)
        return results

    async def _change(
        self,
        *,
        agent_id: str,
        expected_version: int,
        reason: str,
        principal: Principal,
        target_state: RuntimeControlState,
        incident_id: str | None,
        evidence_reference: str | None,
    ) -> RuntimeControlResult:
        normalized_reason = reason.strip()
        normalized_evidence = evidence_reference.strip() if evidence_reference else None
        if not normalized_reason or len(normalized_reason) > 1000:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                "Runtime-control reason must contain 1..1000 characters",
            )
        if normalized_evidence is not None and len(normalized_evidence) > 500:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                "Runtime-control evidence reference exceeds 500 characters",
            )
        try:
            await self._projection.ping()
        except RuntimeControlUnavailable as exc:
            raise _projection_unavailable_error() from exc

        loaded = await self._repository.get_agent_for_update(
            agent_id,
            incident_id=incident_id,
        )
        if loaded is None:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.NOT_FOUND, "Agent or incident not found")
        context, incident = loaded
        try:
            self._require_owner_or_admin(context, principal)
        except ApplicationError:
            await self._transaction.rollback()
            raise
        if context.agent_version != expected_version:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.CONFLICT, "Agent version conflict")
        latest = await self._repository.get_latest_transition_for_update(agent_id)
        if latest is not None and latest.status is RuntimeControlTransitionStatus.PENDING:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Agent already has a pending runtime-control transition",
            )
        try:
            validate_transition(context, target_state=target_state, incident=incident)
        except RuntimeControlDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc

        now = self._clock()
        transition = RuntimeControlTransitionRecord(
            id=self._id_factory(),
            agent_id=context.agent_id,
            ai_system_id=context.ai_system_id,
            control_epoch=(latest.control_epoch if latest is not None else 0) + 1,
            previous_state=context.state,
            target_state=target_state,
            status=RuntimeControlTransitionStatus.PENDING,
            revoked_through_agent_version=context.agent_version,
            reason=normalized_reason,
            requested_by=principal.user_id,
            requested_at=now,
            applied_at=None,
            incident_id=incident_id,
            evidence_reference=normalized_evidence,
            version=1,
        )
        try:
            saved = await self._repository.save_transition(transition)
            await self._audit.append(
                actor_id=principal.user_id,
                action=_requested_action(target_state),
                transition=saved,
            )
            await self._transaction.commit()
        except Exception:
            await self._transaction.rollback()
            raise

        try:
            await self._projection.project(_snapshot_for_transition(saved))
        except RuntimeControlUnavailable as exc:
            # The pending transition intentionally remains committed for reconciliation.
            raise _projection_unavailable_error() from exc
        return await self._finalize_transition(saved.id)

    async def _finalize_transition(
        self,
        transition_id: str,
        *,
        reconciled_by: str | None = None,
    ) -> RuntimeControlResult:
        observed = await self._repository.get_transition(transition_id)
        if observed is None:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.NOT_FOUND, "Runtime-control transition not found")

        # Every command path locks Agent before Transition. Keeping one lock order prevents
        # a projector/finalizer racing a new operator command from creating a DB deadlock.
        loaded = await self._repository.get_agent_for_update(
            observed.agent_id,
            incident_id=None,
        )
        if loaded is None:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.NOT_FOUND, "Agent not found")
        context, _ = loaded
        transition = await self._repository.get_transition_for_update(transition_id)
        if transition is None:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.NOT_FOUND, "Runtime-control transition not found")
        if transition.status is RuntimeControlTransitionStatus.APPLIED:
            await self._transaction.rollback()
            return _result(context, transition)
        if context.state is not transition.previous_state:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Agent state changed outside the pending runtime-control transition",
            )

        now = self._clock()
        try:
            updated_context = await self._repository.apply_agent_state(
                context,
                engaged=transition.target_state is RuntimeControlState.ACTIVE,
                actor_id=transition.requested_by,
                changed_at=now,
            )
            applied = replace(
                transition,
                status=RuntimeControlTransitionStatus.APPLIED,
                applied_at=now,
                version=transition.version + 1,
            )
            applied = await self._repository.save_transition(applied)
            await self._audit.append(
                actor_id=transition.requested_by,
                action=_applied_action(transition.target_state),
                transition=applied,
            )
            if reconciled_by is not None:
                await self._audit.append(
                    actor_id=reconciled_by,
                    action="runtime_control.projection_reconciled",
                    transition=applied,
                )
            await self._transaction.commit()
            return _result(updated_context, applied)
        except Exception:
            await self._transaction.rollback()
            raise

    @staticmethod
    def _require_owner_or_admin(
        context: RuntimeControlAgentContext,
        principal: Principal,
    ) -> None:
        if (
            principal.user_id not in {context.ai_system_owner_id, context.agent_owner_id}
            and not principal.is_admin
        ):
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the system owner, agent owner, or an administrator can change "
                "runtime control",
            )


def _snapshot_for_transition(transition: RuntimeControlTransitionRecord) -> RuntimeControlSnapshot:
    return RuntimeControlSnapshot(
        agent_id=transition.agent_id,
        control_epoch=transition.control_epoch,
        state=transition.target_state,
        revoked_through_agent_version=transition.revoked_through_agent_version,
        transition_id=transition.id,
    )


def _result(
    context: RuntimeControlAgentContext,
    transition: RuntimeControlTransitionRecord,
) -> RuntimeControlResult:
    return RuntimeControlResult(
        agent_id=context.agent_id,
        ai_system_id=context.ai_system_id,
        kill_switch_enabled=context.kill_switch_enabled,
        kill_switch_engaged=context.kill_switch_engaged,
        agent_version=context.agent_version,
        transition=transition,
    )


def _requested_action(target: RuntimeControlState) -> str:
    return (
        "runtime_control.activation_requested"
        if target is RuntimeControlState.ACTIVE
        else "runtime_control.deactivation_requested"
    )


def _applied_action(target: RuntimeControlState) -> str:
    return (
        "runtime_control.activated"
        if target is RuntimeControlState.ACTIVE
        else "runtime_control.deactivated"
    )


def _projection_unavailable_error() -> ApplicationError:
    return ApplicationError(
        ErrorKind.DEPENDENCY_UNAVAILABLE,
        {
            "code": "runtime_control_unavailable",
            "message": "Runtime-control projection is unavailable; fail-closed state is preserved",
        },
    )
