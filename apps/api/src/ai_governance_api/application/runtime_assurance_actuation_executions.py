"""Governed Runtime Assurance execution over approved human decision evidence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

from governance_schemas import ApprovalArea

from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.runtime_assurance_actuation_decisions import (
    RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA,
    RuntimeAssuranceActuationDecisionOutcome,
)
from ai_governance_api.domain.runtime_assurance_actuation_executions import (
    RUNTIME_ASSURANCE_ACTUATION_RUNTIME_REASON,
    RuntimeAssuranceActuationExecution,
    RuntimeAssuranceActuationExecutionContext,
    RuntimeAssuranceActuationExecutionDomainError,
    build_actuation_execution_receipt,
    runtime_actuation_decision_evidence_reference,
    validate_actuation_execution_binding,
    validate_new_execution_preconditions,
    validate_runtime_transition_binding,
)
from ai_governance_api.domain.runtime_control import (
    RuntimeControlResult,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type IdFactory = Callable[[], str]


class RuntimeAssuranceActuationExecutionRepositoryPort(Protocol):
    """Persistence boundary for approved lineage, runtime evidence, and receipts."""

    async def get_context(
        self,
        decision_id: str,
    ) -> RuntimeAssuranceActuationExecutionContext | None:
        """Return validated approval lineage and a fresh runtime preflight snapshot."""
        ...

    async def get_execution_by_decision_id(
        self,
        decision_id: str,
    ) -> RuntimeAssuranceActuationExecution | None:
        """Return the immutable receipt for one approved decision, when present."""
        ...

    async def save_execution(
        self,
        execution: RuntimeAssuranceActuationExecution,
    ) -> RuntimeAssuranceActuationExecution:
        """Persist one immutable applied execution receipt without committing."""
        ...


class RuntimeAssuranceActuationRuntimeControlPort(Protocol):
    """Exactly bounded Runtime Control command consumed by P1.9c."""

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
        """Engage the existing Runtime Control kill-switch transition path."""
        ...


class RuntimeAssuranceActuationExecutionAuditPort(Protocol):
    """Append content-minimized execution receipts to the shared audit chain."""

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
        """Append one governed execution event in the surrounding transaction."""
        ...


class RuntimeAssuranceActuationExecutionTransactionPort(Protocol):
    """Transaction boundary for execution receipt and audit persistence."""

    async def commit(self) -> None:
        """Commit the current transaction."""
        ...

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        ...


class RuntimeAssuranceActuationExecutionService:
    """Execute only approved kill-switch intent through the existing Runtime Control path."""

    def __init__(
        self,
        repository: RuntimeAssuranceActuationExecutionRepositoryPort,
        runtime_control: RuntimeAssuranceActuationRuntimeControlPort,
        audit: RuntimeAssuranceActuationExecutionAuditPort,
        transaction: RuntimeAssuranceActuationExecutionTransactionPort,
        *,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize governed execution with one explicit actuator and evidence ports."""
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
    ) -> RuntimeAssuranceActuationExecution:
        """Execute or idempotently recover one approved engage-kill-switch decision."""
        context = await self._load_context(decision_id)
        try:
            self._require_executor(context, principal)
            self._require_approved(context)
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
            validate_new_execution_preconditions(context)
        except RuntimeAssuranceActuationExecutionDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc

        evidence_reference = self._evidence_reference(context)
        expected_agent_version = context.agent_version

        # End the governance read transaction before Runtime Control performs projection I/O.
        await self._transaction.commit()
        try:
            result = await self._runtime_control.activate(
                agent_id=context.request.agent_id,
                expected_version=expected_agent_version,
                reason=RUNTIME_ASSURANCE_ACTUATION_RUNTIME_REASON,
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
            audit_action="runtime_assurance.actuation_executed",
        )

    async def get(
        self,
        *,
        decision_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceActuationExecution:
        """Return immutable execution evidence to an authorized governance stakeholder."""
        context = await self._load_context(decision_id)
        self._require_viewer(context, principal)
        execution = await self._load_existing(decision_id)
        if execution is None:
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime Assurance actuation execution not found",
            )
        self._validate_existing(execution, context)
        return execution

    async def _recover_or_wait(
        self,
        context: RuntimeAssuranceActuationExecutionContext,
        principal: Principal,
    ) -> RuntimeAssuranceActuationExecution:
        transition = context.matching_transition
        assert transition is not None
        try:
            validate_runtime_transition_binding(context, transition)
        except RuntimeAssuranceActuationExecutionDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        if transition.status is RuntimeControlTransitionStatus.PENDING:
            await self._transaction.rollback()
            raise _pending_reconciliation_error()
        return await self._persist_receipt(
            context,
            transition,
            audit_actor=principal.user_id,
            audit_action="runtime_assurance.actuation_execution_recovered",
        )

    async def _recover_after_runtime_error(
        self,
        *,
        decision_id: str,
        principal: Principal,
        original: ApplicationError,
    ) -> RuntimeAssuranceActuationExecution:
        try:
            fresh = await self._load_context(decision_id)
            self._require_executor(fresh, principal)
            self._require_approved(fresh)
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
        context: RuntimeAssuranceActuationExecutionContext,
        transition: RuntimeControlTransitionRecord,
        *,
        audit_actor: str,
        audit_action: str,
    ) -> RuntimeAssuranceActuationExecution:
        try:
            execution = build_actuation_execution_receipt(
                execution_id=self._id_factory(),
                context=context,
                transition=transition,
            )
        except RuntimeAssuranceActuationExecutionDomainError as exc:
            await self._transaction.rollback()
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        try:
            stored = await self._repository.save_execution(execution)
            await self._audit.append(
                actor_id=audit_actor,
                action=audit_action,
                entity_type="runtime_assurance_actuation_execution",
                entity_id=stored.id,
                entity_version=stored.version,
                payload={
                    "decision_id": stored.decision_id,
                    "request_id": stored.request_id,
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
    ) -> RuntimeAssuranceActuationExecutionContext:
        try:
            context = await self._repository.get_context(decision_id)
        except ValueError as exc:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime Assurance actuation execution binding is inconsistent",
            ) from exc
        if context is None:
            await self._transaction.rollback()
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime Assurance actuation decision not found",
            )
        return context

    async def _load_existing(
        self,
        decision_id: str,
    ) -> RuntimeAssuranceActuationExecution | None:
        try:
            return await self._repository.get_execution_by_decision_id(decision_id)
        except ValueError as exc:
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime Assurance actuation execution evidence is invalid",
            ) from exc

    @staticmethod
    def _require_approved(context: RuntimeAssuranceActuationExecutionContext) -> None:
        if context.decision.decision is not RuntimeAssuranceActuationDecisionOutcome.APPROVED:
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Only an approved actuation decision can be executed",
            )

    @staticmethod
    def _require_executor(
        context: RuntimeAssuranceActuationExecutionContext,
        principal: Principal,
    ) -> None:
        if principal.user_id != context.source.ai_system_owner_id and not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the AI system owner or an administrator can execute approved actuation",
            )

    @staticmethod
    def _require_viewer(
        context: RuntimeAssuranceActuationExecutionContext,
        principal: Principal,
    ) -> None:
        if (
            principal.user_id != context.request.requested_by
            and principal.user_id != context.source.ai_system_owner_id
            and principal.user_id != context.decision.decided_by
            and not principal.is_admin
            and RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA not in principal.approval_areas
        ):
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Principal is not authorized to view this actuation execution",
            )

    @staticmethod
    def _validate_existing(
        execution: RuntimeAssuranceActuationExecution,
        context: RuntimeAssuranceActuationExecutionContext,
    ) -> None:
        try:
            validate_actuation_execution_binding(execution, context)
        except RuntimeAssuranceActuationExecutionDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc

    @staticmethod
    def _validate_runtime_result(
        context: RuntimeAssuranceActuationExecutionContext,
        result: RuntimeControlResult,
        *,
        expected_agent_version: int,
        principal: Principal,
    ) -> None:
        try:
            validate_runtime_transition_binding(context, result.transition)
        except RuntimeAssuranceActuationExecutionDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc
        transition = result.transition
        if (
            transition.status is not RuntimeControlTransitionStatus.APPLIED
            or transition.revoked_through_agent_version != expected_agent_version
            or transition.requested_by != principal.user_id
            or result.agent_id != context.request.agent_id
            or result.ai_system_id != context.request.ai_system_id
            or not result.kill_switch_enabled
            or not result.kill_switch_engaged
            or result.agent_version != expected_agent_version + 1
        ):
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime Control result does not match the approved execution command",
            )

    @staticmethod
    def _evidence_reference(context: RuntimeAssuranceActuationExecutionContext) -> str:
        try:
            return runtime_actuation_decision_evidence_reference(context.decision)
        except RuntimeAssuranceActuationExecutionDomainError as exc:
            raise ApplicationError(ErrorKind.CONFLICT, str(exc)) from exc


def _pending_reconciliation_error() -> ApplicationError:
    return ApplicationError(
        ErrorKind.DEPENDENCY_UNAVAILABLE,
        {
            "code": "governed_actuation_pending_reconciliation",
            "message": (
                "The approved Runtime Control transition is pending reconciliation; "
                "no duplicate transition was created"
            ),
        },
    )


def required_runtime_actuation_execution_view_area() -> ApprovalArea:
    """Expose the existing Security capability used by execution evidence viewers."""
    return RUNTIME_ASSURANCE_ACTUATION_APPROVAL_AREA
