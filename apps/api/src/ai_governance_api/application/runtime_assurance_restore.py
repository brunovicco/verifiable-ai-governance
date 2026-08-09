"""Governed request, approval, and execution services for kill-switch restoration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.runtime_assurance_restore import (
    RUNTIME_ASSURANCE_RESTORE_APPROVAL_AREA,
    RUNTIME_ASSURANCE_RESTORE_RUNTIME_REASON,
    RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION,
    RuntimeAssuranceRestoreAction,
    RuntimeAssuranceRestoreDecision,
    RuntimeAssuranceRestoreDecisionOutcome,
    RuntimeAssuranceRestoreDomainError,
    RuntimeAssuranceRestoreExecution,
    RuntimeAssuranceRestoreExecutionContext,
    RuntimeAssuranceRestoreRequest,
    RuntimeAssuranceRestoreRequestState,
    RuntimeAssuranceRestoreSourceContext,
    build_remediation_digest,
    build_restore_decision_digest,
    build_restore_execution_receipt,
    build_restore_request_digest,
    normalize_restore_reason,
    restore_decision_evidence_reference,
    validate_new_restore_execution_preconditions,
    validate_restore_decision_binding,
    validate_restore_execution_binding,
    validate_restore_request_binding,
    validate_restore_request_current,
    validate_restore_source_eligibility,
    validate_restore_transition_binding,
)
from ai_governance_api.domain.runtime_control import (
    RuntimeControlResult,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


class RuntimeAssuranceRestoreRepositoryPort(Protocol):
    """Persistence boundary for independent restore evidence and fresh runtime state."""

    async def get_source_context(
        self,
        source_execution_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceRestoreSourceContext | None:
        """Return a validated engage execution plus fresh recovery state."""
        ...

    async def get_request_by_execution_remediation(
        self,
        source_execution_id: str,
        remediation_digest: str,
    ) -> RuntimeAssuranceRestoreRequest | None:
        """Return the idempotent request for one execution/remediation snapshot."""
        ...

    async def get_request_context(
        self,
        request_id: str,
        *,
        for_update: bool = False,
    ) -> tuple[RuntimeAssuranceRestoreRequest, RuntimeAssuranceRestoreSourceContext] | None:
        """Return immutable request evidence plus fresh source context."""
        ...

    async def save_request(
        self,
        request: RuntimeAssuranceRestoreRequest,
    ) -> RuntimeAssuranceRestoreRequest:
        """Persist one immutable restore request without committing."""
        ...

    async def get_decision_by_request_id(
        self,
        request_id: str,
    ) -> RuntimeAssuranceRestoreDecision | None:
        """Return the terminal decision for one restore request."""
        ...

    async def get_decision_context(
        self,
        decision_id: str,
    ) -> RuntimeAssuranceRestoreExecutionContext | None:
        """Return approved restore lineage plus fresh execution-time state."""
        ...

    async def save_decision(
        self,
        decision: RuntimeAssuranceRestoreDecision,
    ) -> RuntimeAssuranceRestoreDecision:
        """Persist one terminal restore decision without committing."""
        ...

    async def get_execution_by_decision_id(
        self,
        decision_id: str,
    ) -> RuntimeAssuranceRestoreExecution | None:
        """Return the immutable applied restore receipt for one decision."""
        ...

    async def save_execution(
        self,
        execution: RuntimeAssuranceRestoreExecution,
    ) -> RuntimeAssuranceRestoreExecution:
        """Persist one immutable applied restore receipt without committing."""
        ...


class RuntimeAssuranceRestoreAuditPort(Protocol):
    """Append content-minimized restore workflow evidence to the shared audit chain."""

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
        """Append one restore event inside the surrounding transaction."""
        ...


class RuntimeAssuranceRestoreTransactionPort(Protocol):
    """Transaction boundary shared by restore evidence writes."""

    async def commit(self) -> None:
        """Commit the current transaction."""
        ...

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        ...


class RuntimeAssuranceRestoreRuntimeControlPort(Protocol):
    """Exactly bounded Runtime Control restore command consumed by P1.9d."""

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
        """Restore the existing Runtime Control kill-switch path."""
        ...


class RuntimeAssuranceRestoreRequestService:
    """Create restore intent only; this service cannot mutate Runtime Control."""

    def __init__(
        self,
        repository: RuntimeAssuranceRestoreRepositoryPort,
        audit: RuntimeAssuranceRestoreAuditPort,
        transaction: RuntimeAssuranceRestoreTransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize request creation with evidence-only ports."""
        self._repository = repository
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def create(
        self,
        *,
        source_execution_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceRestoreRequest:
        """Create or replay a restore request for the current remediation snapshot."""
        source = await self._load_source(source_execution_id, for_update=True)
        try:
            _require_owner_or_admin(source, principal, action="request restore")
            validate_restore_source_eligibility(source)
            remediation_digest = build_remediation_digest(source)
        except RuntimeAssuranceRestoreDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        except ApplicationError:
            await self._transaction.rollback()
            raise

        existing = await self._repository.get_request_by_execution_remediation(
            source_execution_id,
            remediation_digest,
        )
        if existing is not None:
            try:
                validate_restore_request_binding(existing, source.source_execution)
            except RuntimeAssuranceRestoreDomainError as exc:
                await self._transaction.rollback()
                raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
            await self._transaction.commit()
            return existing

        requested_at = self._clock()
        request_id = self._id_factory()
        action = RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH
        state = RuntimeAssuranceRestoreRequestState.PENDING
        execution = source.source_execution
        try:
            request_digest = build_restore_request_digest(
                request_id=request_id,
                source_execution_id=execution.id,
                source_execution_digest=execution.execution_digest,
                agent_id=execution.agent_id,
                ai_system_id=execution.ai_system_id,
                incident_id=execution.incident_id,
                action=action,
                state=state,
                remediation_digest=remediation_digest,
                incident_status=source.incident_status,
                incident_version=source.incident_version,
                requested_by=principal.user_id,
                requested_at=requested_at,
            )
        except RuntimeAssuranceRestoreDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        request = RuntimeAssuranceRestoreRequest(
            id=request_id,
            schema_version=RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION,
            source_execution_id=execution.id,
            source_execution_digest=execution.execution_digest,
            agent_id=execution.agent_id,
            ai_system_id=execution.ai_system_id,
            incident_id=execution.incident_id,
            action=action,
            state=state,
            remediation_digest=remediation_digest,
            incident_status=source.incident_status,
            incident_version=source.incident_version,
            requested_by=principal.user_id,
            requested_at=requested_at,
            request_digest=request_digest,
        )
        try:
            stored = await self._repository.save_request(request)
            await self._audit.append(
                actor_id=principal.user_id,
                action="runtime_assurance.restore_requested",
                entity_type="runtime_assurance_restore_request",
                entity_id=stored.id,
                entity_version=stored.version,
                payload={
                    "source_execution_id": stored.source_execution_id,
                    "agent_id": stored.agent_id,
                    "ai_system_id": stored.ai_system_id,
                    "incident_id": stored.incident_id,
                    "remediation_digest": stored.remediation_digest,
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
        source_execution_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceRestoreRequest:
        """Return the request matching the current remediation snapshot."""
        source = await self._load_source(source_execution_id)
        _require_restore_viewer(source, None, principal)
        try:
            remediation_digest = build_remediation_digest(source)
        except RuntimeAssuranceRestoreDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        request = await self._repository.get_request_by_execution_remediation(
            source_execution_id,
            remediation_digest,
        )
        if request is None:
            raise ApplicationError(
                ErrorKind.NOT_FOUND, "Runtime Assurance restore request not found"
            )
        try:
            validate_restore_request_binding(request, source.source_execution)
        except RuntimeAssuranceRestoreDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        return request

    async def _load_source(
        self,
        source_execution_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceRestoreSourceContext:
        try:
            source = await self._repository.get_source_context(
                source_execution_id,
                for_update=for_update,
            )
        except ValueError as exc:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime Assurance restore source binding is inconsistent",
            ) from exc
        if source is None:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime Assurance actuation execution not found",
            )
        return source


class RuntimeAssuranceRestoreDecisionService:
    """Record independent Security approval or rejection without restoring runtime state."""

    def __init__(
        self,
        repository: RuntimeAssuranceRestoreRepositoryPort,
        audit: RuntimeAssuranceRestoreAuditPort,
        transaction: RuntimeAssuranceRestoreTransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize decision handling with evidence-only ports."""
        self._repository = repository
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def decide(
        self,
        *,
        request_id: str,
        decision: RuntimeAssuranceRestoreDecisionOutcome,
        reason: str,
        principal: Principal,
    ) -> RuntimeAssuranceRestoreDecision:
        """Create or replay one terminal independent restore decision."""
        request, source = await self._load_context(request_id, for_update=True)
        try:
            _require_independent_security_approver(request, principal)
            canonical_reason = normalize_restore_reason(reason)
        except RuntimeAssuranceRestoreDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.UNPROCESSABLE, str(exc)) from exc
        except ApplicationError:
            await self._transaction.rollback()
            raise

        existing = await self._load_existing(request_id)
        if existing is not None:
            try:
                validate_restore_decision_binding(existing, request)
                _require_idempotent_decision(existing, decision, canonical_reason, principal)
            except RuntimeAssuranceRestoreDomainError as exc:
                await self._transaction.rollback()
                raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
            except ApplicationError:
                await self._transaction.rollback()
                raise
            await self._transaction.commit()
            return existing

        if decision is RuntimeAssuranceRestoreDecisionOutcome.APPROVED:
            try:
                validate_restore_request_current(request, source)
            except RuntimeAssuranceRestoreDomainError as exc:
                await self._transaction.rollback()
                raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc

        decided_at = self._clock()
        decision_id = self._id_factory()
        try:
            decision_digest = build_restore_decision_digest(
                decision_id=decision_id,
                request_id=request.id,
                request_digest=request.request_digest,
                source_execution_id=request.source_execution_id,
                source_execution_digest=request.source_execution_digest,
                action=request.action,
                decision=decision,
                approval_area=RUNTIME_ASSURANCE_RESTORE_APPROVAL_AREA,
                decided_by=principal.user_id,
                decided_at=decided_at,
                reason=canonical_reason,
            )
        except RuntimeAssuranceRestoreDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        record = RuntimeAssuranceRestoreDecision(
            id=decision_id,
            schema_version=RUNTIME_ASSURANCE_RESTORE_SCHEMA_VERSION,
            request_id=request.id,
            request_digest=request.request_digest,
            source_execution_id=request.source_execution_id,
            source_execution_digest=request.source_execution_digest,
            action=request.action,
            decision=decision,
            approval_area=RUNTIME_ASSURANCE_RESTORE_APPROVAL_AREA,
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
                    "runtime_assurance.restore_approved"
                    if stored.decision is RuntimeAssuranceRestoreDecisionOutcome.APPROVED
                    else "runtime_assurance.restore_rejected"
                ),
                entity_type="runtime_assurance_restore_decision",
                entity_id=stored.id,
                entity_version=stored.version,
                payload={
                    "request_id": stored.request_id,
                    "source_execution_id": stored.source_execution_id,
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
    ) -> RuntimeAssuranceRestoreDecision:
        """Return terminal restore decision evidence to an authorized stakeholder."""
        request, source = await self._load_context(request_id)
        _require_restore_viewer(source, request, principal)
        decision = await self._load_existing(request_id)
        if decision is None:
            raise ApplicationError(
                ErrorKind.NOT_FOUND, "Runtime Assurance restore decision not found"
            )
        try:
            validate_restore_decision_binding(decision, request)
        except RuntimeAssuranceRestoreDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        return decision

    async def _load_context(
        self,
        request_id: str,
        *,
        for_update: bool = False,
    ) -> tuple[RuntimeAssuranceRestoreRequest, RuntimeAssuranceRestoreSourceContext]:
        try:
            loaded = await self._repository.get_request_context(
                request_id,
                for_update=for_update,
            )
        except ValueError as exc:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT, "Restore request binding is inconsistent"
            ) from exc
        if loaded is None:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.NOT_FOUND, "Runtime Assurance restore request not found"
            )
        return loaded

    async def _load_existing(self, request_id: str) -> RuntimeAssuranceRestoreDecision | None:
        try:
            return await self._repository.get_decision_by_request_id(request_id)
        except ValueError as exc:
            raise ApplicationError(
                ErrorKind.CONFLICT, "Restore decision evidence is invalid"
            ) from exc


class RuntimeAssuranceRestoreExecutionService:
    """Execute only approved restore intent through Runtime Control deactivation."""

    def __init__(
        self,
        repository: RuntimeAssuranceRestoreRepositoryPort,
        runtime_control: RuntimeAssuranceRestoreRuntimeControlPort,
        audit: RuntimeAssuranceRestoreAuditPort,
        transaction: RuntimeAssuranceRestoreTransactionPort,
        *,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize the execution path with exactly one restore actuator."""
        self._repository = repository
        self._runtime_control = runtime_control
        self._audit = audit
        self._transaction = transaction
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def execute(
        self,
        *,
        decision_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceRestoreExecution:
        """Execute or recover one approved restore without reusing engage approval."""
        context = await self._load_context(decision_id)
        try:
            _require_owner_or_admin(context.source, principal, action="execute restore")
            _require_approved_restore(context)
        except ApplicationError:
            await self._transaction.rollback()
            raise

        existing = await self._load_existing(decision_id)
        if existing is not None:
            self._validate_existing(existing, context)
            await self._transaction.commit()
            return existing

        if context.matching_transition is not None:
            return await self._recover_or_wait(context, principal)

        try:
            validate_new_restore_execution_preconditions(context)
            evidence_reference = restore_decision_evidence_reference(context.decision)
        except RuntimeAssuranceRestoreDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        expected_agent_version = context.source.agent_version

        # End the governance read transaction before Runtime Control performs projection I/O.
        await self._transaction.commit()
        try:
            result = await self._runtime_control.deactivate(
                agent_id=context.request.agent_id,
                expected_version=expected_agent_version,
                reason=RUNTIME_ASSURANCE_RESTORE_RUNTIME_REASON,
                principal=principal,
                incident_id=context.request.incident_id,
                evidence_reference=evidence_reference,
            )
        except ApplicationError as exc:
            return await self._recover_after_runtime_error(
                decision_id=decision_id,
                principal=principal,
                original=exc,
            )

        self._validate_runtime_result(
            context,
            result,
            expected_agent_version=expected_agent_version,
            principal=principal,
        )
        return await self._persist_receipt(
            context,
            result.transition,
            audit_actor=principal.user_id,
            audit_action="runtime_assurance.restore_executed",
        )

    async def get(
        self,
        *,
        decision_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceRestoreExecution:
        """Return immutable applied restore evidence to an authorized stakeholder."""
        context = await self._load_context(decision_id)
        _require_restore_viewer(context.source, context.request, principal)
        execution = await self._load_existing(decision_id)
        if execution is None:
            raise ApplicationError(
                ErrorKind.NOT_FOUND, "Runtime Assurance restore execution not found"
            )
        self._validate_existing(execution, context)
        return execution

    async def _recover_or_wait(
        self,
        context: RuntimeAssuranceRestoreExecutionContext,
        principal: Principal,
    ) -> RuntimeAssuranceRestoreExecution:
        transition = context.matching_transition
        assert transition is not None
        try:
            validate_restore_transition_binding(context, transition)
        except RuntimeAssuranceRestoreDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        if transition.status is RuntimeControlTransitionStatus.PENDING:
            await self._transaction.rollback()
            raise _pending_restore_reconciliation_error()
        return await self._persist_receipt(
            context,
            transition,
            audit_actor=principal.user_id,
            audit_action="runtime_assurance.restore_execution_recovered",
        )

    async def _recover_after_runtime_error(
        self,
        *,
        decision_id: str,
        principal: Principal,
        original: ApplicationError,
    ) -> RuntimeAssuranceRestoreExecution:
        try:
            fresh = await self._load_context(decision_id)
            _require_owner_or_admin(fresh.source, principal, action="execute restore")
            _require_approved_restore(fresh)
            existing = await self._load_existing(decision_id)
            if existing is not None:
                self._validate_existing(existing, fresh)
                await self._transaction.commit()
                return existing
            if fresh.matching_transition is not None:
                return await self._recover_or_wait(fresh, principal)
        except ApplicationError as recovery_error:
            if recovery_error.kind in {
                ErrorKind.FORBIDDEN,
                ErrorKind.CONFLICT,
                ErrorKind.DEPENDENCY_UNAVAILABLE,
            }:
                raise recovery_error from original
            await self._transaction.rollback()
            raise original from recovery_error
        await self._transaction.rollback()
        raise original

    async def _persist_receipt(
        self,
        context: RuntimeAssuranceRestoreExecutionContext,
        transition: RuntimeControlTransitionRecord,
        *,
        audit_actor: str,
        audit_action: str,
    ) -> RuntimeAssuranceRestoreExecution:
        try:
            execution = build_restore_execution_receipt(
                execution_id=self._id_factory(),
                context=context,
                transition=transition,
            )
        except RuntimeAssuranceRestoreDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        try:
            stored = await self._repository.save_execution(execution)
            await self._audit.append(
                actor_id=audit_actor,
                action=audit_action,
                entity_type="runtime_assurance_restore_execution",
                entity_id=stored.id,
                entity_version=stored.version,
                payload={
                    "decision_id": stored.decision_id,
                    "request_id": stored.request_id,
                    "source_execution_id": stored.source_execution_id,
                    "agent_id": stored.agent_id,
                    "ai_system_id": stored.ai_system_id,
                    "runtime_transition_id": stored.runtime_transition_id,
                    "execution_digest": stored.execution_digest,
                },
            )
            await self._transaction.commit()
            return stored
        except Exception:
            await self._transaction.rollback()
            raise

    async def _load_context(
        self,
        decision_id: str,
    ) -> RuntimeAssuranceRestoreExecutionContext:
        try:
            context = await self._repository.get_decision_context(decision_id)
        except ValueError as exc:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT, "Restore execution binding is inconsistent"
            ) from exc
        if context is None:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.NOT_FOUND, "Runtime Assurance restore decision not found"
            )
        return context

    async def _load_existing(
        self,
        decision_id: str,
    ) -> RuntimeAssuranceRestoreExecution | None:
        try:
            return await self._repository.get_execution_by_decision_id(decision_id)
        except ValueError as exc:
            raise ApplicationError(
                ErrorKind.CONFLICT, "Restore execution evidence is invalid"
            ) from exc

    @staticmethod
    def _validate_existing(
        execution: RuntimeAssuranceRestoreExecution,
        context: RuntimeAssuranceRestoreExecutionContext,
    ) -> None:
        try:
            validate_restore_execution_binding(execution, context)
        except RuntimeAssuranceRestoreDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc

    @staticmethod
    def _validate_runtime_result(
        context: RuntimeAssuranceRestoreExecutionContext,
        result: RuntimeControlResult,
        *,
        expected_agent_version: int,
        principal: Principal,
    ) -> None:
        try:
            validate_restore_transition_binding(context, result.transition)
        except RuntimeAssuranceRestoreDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        transition = result.transition
        if (
            transition.status is not RuntimeControlTransitionStatus.APPLIED
            or transition.revoked_through_agent_version != expected_agent_version
            or transition.requested_by != principal.user_id
            or result.agent_id != context.request.agent_id
            or result.ai_system_id != context.request.ai_system_id
            or not result.kill_switch_enabled
            or result.kill_switch_engaged
            or result.agent_version != expected_agent_version + 1
        ):
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime Control result does not match the approved restore command",
            )


def _require_owner_or_admin(
    source: RuntimeAssuranceRestoreSourceContext,
    principal: Principal,
    *,
    action: str,
) -> None:
    if principal.user_id != source.ai_system_owner_id and not principal.is_admin:
        raise ApplicationError(
            ErrorKind.FORBIDDEN,
            f"Only the AI system owner or an administrator can {action}",
        )


def _require_independent_security_approver(
    request: RuntimeAssuranceRestoreRequest,
    principal: Principal,
) -> None:
    if principal.user_id == request.requested_by:
        raise ApplicationError(
            ErrorKind.FORBIDDEN, "Restore requester cannot decide their own request"
        )
    if RUNTIME_ASSURANCE_RESTORE_APPROVAL_AREA not in principal.approval_areas:
        raise ApplicationError(
            ErrorKind.FORBIDDEN,
            "Security approval capability is required for Runtime Assurance restore decisions",
        )


def _require_restore_viewer(
    source: RuntimeAssuranceRestoreSourceContext,
    request: RuntimeAssuranceRestoreRequest | None,
    principal: Principal,
) -> None:
    if (
        principal.user_id != source.ai_system_owner_id
        and (request is None or principal.user_id != request.requested_by)
        and not principal.is_admin
        and RUNTIME_ASSURANCE_RESTORE_APPROVAL_AREA not in principal.approval_areas
    ):
        raise ApplicationError(
            ErrorKind.FORBIDDEN, "Principal is not authorized to view restore evidence"
        )


def _require_idempotent_decision(
    existing: RuntimeAssuranceRestoreDecision,
    decision: RuntimeAssuranceRestoreDecisionOutcome,
    reason: str,
    principal: Principal,
) -> None:
    if (
        existing.decision is not decision
        or existing.reason != reason
        or existing.decided_by != principal.user_id
        or existing.approval_area is not RUNTIME_ASSURANCE_RESTORE_APPROVAL_AREA
    ):
        raise ApplicationError(
            ErrorKind.CONFLICT,
            "Restore request already has a different terminal decision",
        )


def _require_approved_restore(context: RuntimeAssuranceRestoreExecutionContext) -> None:
    if context.decision.decision is not RuntimeAssuranceRestoreDecisionOutcome.APPROVED:
        raise ApplicationError(
            ErrorKind.CONFLICT, "Only an approved restore decision can be executed"
        )


def _pending_restore_reconciliation_error() -> ApplicationError:
    return ApplicationError(
        ErrorKind.DEPENDENCY_UNAVAILABLE,
        {
            "code": "governed_restore_pending_reconciliation",
            "message": (
                "The approved Runtime Control restore transition is pending reconciliation; "
                "no duplicate transition was created"
            ),
        },
    )
