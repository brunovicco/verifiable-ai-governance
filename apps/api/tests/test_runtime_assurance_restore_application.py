from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.application.runtime_assurance_restore import (
    RuntimeAssuranceRestoreDecisionService,
    RuntimeAssuranceRestoreExecutionService,
    RuntimeAssuranceRestoreRequestService,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import RuntimeAssuranceActuationAction
from ai_governance_api.domain.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecution,
)
from ai_governance_api.domain.runtime_assurance_restore import (
    RuntimeAssuranceRestoreAction,
    RuntimeAssuranceRestoreDecision,
    RuntimeAssuranceRestoreDecisionOutcome,
    RuntimeAssuranceRestoreExecution,
    RuntimeAssuranceRestoreExecutionContext,
    RuntimeAssuranceRestoreRequest,
    RuntimeAssuranceRestoreRequestState,
    RuntimeAssuranceRestoreSourceContext,
    build_remediation_digest,
    build_restore_decision_digest,
    build_restore_request_digest,
    restore_decision_evidence_reference,
)
from ai_governance_api.domain.runtime_control import (
    RuntimeControlResult,
    RuntimeControlState,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
)
from ai_governance_api.errors import ApplicationError, ErrorKind
from governance_schemas import ApprovalArea

NOW = datetime(2026, 8, 9, 22, 30, tzinfo=UTC)


def source_context() -> RuntimeAssuranceRestoreSourceContext:
    execution = RuntimeAssuranceActuationExecution(
        id="engage-execution-1",
        schema_version="1.0",
        decision_id="engage-decision-1",
        decision_digest="a" * 64,
        request_id="engage-request-1",
        request_digest="b" * 64,
        action=RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH,
        agent_id="agent-1",
        ai_system_id="system-1",
        incident_id="incident-1",
        runtime_transition_id="engage-transition-1",
        control_epoch=4,
        previous_state=RuntimeControlState.INACTIVE,
        target_state=RuntimeControlState.ACTIVE,
        revoked_through_agent_version=7,
        resulting_agent_version=8,
        executed_by="system-owner",
        executed_at=NOW,
        execution_digest="c" * 64,
    )
    transition = RuntimeControlTransitionRecord(
        id="engage-transition-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        control_epoch=4,
        previous_state=RuntimeControlState.INACTIVE,
        target_state=RuntimeControlState.ACTIVE,
        status=RuntimeControlTransitionStatus.APPLIED,
        revoked_through_agent_version=7,
        reason="engage",
        requested_by="system-owner",
        requested_at=NOW,
        applied_at=NOW,
        incident_id="incident-1",
        evidence_reference="engage-reference",
        version=2,
    )
    return RuntimeAssuranceRestoreSourceContext(
        source_execution=execution,
        ai_system_owner_id="system-owner",
        agent_version=8,
        kill_switch_enabled=True,
        kill_switch_engaged=True,
        incident_status=IncidentStatus.REMEDIATING,
        incident_version=3,
        remediation_owner_id="remediation-owner",
        remediation_description="Fix validated.",
        remediation_due_at=NOW + timedelta(days=1),
        resolved_at=None,
        latest_transition=transition,
    )


def make_request(source: RuntimeAssuranceRestoreSourceContext) -> RuntimeAssuranceRestoreRequest:
    remediation_digest = build_remediation_digest(source)
    digest = build_restore_request_digest(
        request_id="restore-request-1",
        source_execution_id=source.source_execution.id,
        source_execution_digest=source.source_execution.execution_digest,
        agent_id=source.source_execution.agent_id,
        ai_system_id=source.source_execution.ai_system_id,
        incident_id=source.source_execution.incident_id,
        action=RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH,
        state=RuntimeAssuranceRestoreRequestState.PENDING,
        remediation_digest=remediation_digest,
        incident_status=source.incident_status,
        incident_version=source.incident_version,
        requested_by="system-owner",
        requested_at=NOW,
    )
    return RuntimeAssuranceRestoreRequest(
        id="restore-request-1",
        schema_version="1.0",
        source_execution_id=source.source_execution.id,
        source_execution_digest=source.source_execution.execution_digest,
        agent_id=source.source_execution.agent_id,
        ai_system_id=source.source_execution.ai_system_id,
        incident_id=source.source_execution.incident_id,
        action=RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH,
        state=RuntimeAssuranceRestoreRequestState.PENDING,
        remediation_digest=remediation_digest,
        incident_status=source.incident_status,
        incident_version=source.incident_version,
        requested_by="system-owner",
        requested_at=NOW,
        request_digest=digest,
    )


def make_decision(
    request: RuntimeAssuranceRestoreRequest,
    *,
    outcome: RuntimeAssuranceRestoreDecisionOutcome = (
        RuntimeAssuranceRestoreDecisionOutcome.APPROVED
    ),
) -> RuntimeAssuranceRestoreDecision:
    digest = build_restore_decision_digest(
        decision_id="restore-decision-1",
        request_id=request.id,
        request_digest=request.request_digest,
        source_execution_id=request.source_execution_id,
        source_execution_digest=request.source_execution_digest,
        action=request.action,
        decision=outcome,
        approval_area=ApprovalArea.SECURITY,
        decided_by="security-approver",
        decided_at=NOW,
        reason="Recovery evidence reviewed.",
    )
    return RuntimeAssuranceRestoreDecision(
        id="restore-decision-1",
        schema_version="1.0",
        request_id=request.id,
        request_digest=request.request_digest,
        source_execution_id=request.source_execution_id,
        source_execution_digest=request.source_execution_digest,
        action=request.action,
        decision=outcome,
        approval_area=ApprovalArea.SECURITY,
        decided_by="security-approver",
        decided_at=NOW,
        reason="Recovery evidence reviewed.",
        decision_digest=digest,
    )


class Repository:
    def __init__(self, source: RuntimeAssuranceRestoreSourceContext) -> None:
        self.source = source
        self.request: RuntimeAssuranceRestoreRequest | None = None
        self.decision: RuntimeAssuranceRestoreDecision | None = None
        self.execution: RuntimeAssuranceRestoreExecution | None = None
        self.matching_transition: RuntimeControlTransitionRecord | None = None

    async def get_source_context(self, source_execution_id: str, *, for_update: bool = False):
        del for_update
        return self.source if source_execution_id == self.source.source_execution.id else None

    async def get_request_by_execution_remediation(
        self, source_execution_id: str, remediation_digest: str
    ):
        if (
            self.request is not None
            and self.request.source_execution_id == source_execution_id
            and self.request.remediation_digest == remediation_digest
        ):
            return self.request
        return None

    async def get_request_context(self, request_id: str, *, for_update: bool = False):
        del for_update
        if self.request is None or self.request.id != request_id:
            return None
        return self.request, self.source

    async def save_request(self, request: RuntimeAssuranceRestoreRequest):
        self.request = request
        return request

    async def get_decision_by_request_id(self, request_id: str):
        if self.decision is not None and self.decision.request_id == request_id:
            return self.decision
        return None

    async def get_decision_context(self, decision_id: str):
        if self.decision is None or self.decision.id != decision_id or self.request is None:
            return None
        return RuntimeAssuranceRestoreExecutionContext(
            decision=self.decision,
            request=self.request,
            source=self.source,
            matching_transition=self.matching_transition,
        )

    async def save_decision(self, decision: RuntimeAssuranceRestoreDecision):
        self.decision = decision
        return decision

    async def get_execution_by_decision_id(self, decision_id: str):
        if self.execution is not None and self.execution.decision_id == decision_id:
            return self.execution
        return None

    async def save_execution(self, execution: RuntimeAssuranceRestoreExecution):
        self.execution = execution
        return execution


class Audit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def append(self, **kwargs) -> None:
        self.events.append(dict(kwargs))


class Transaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class RuntimeControl:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def deactivate(self, **kwargs) -> RuntimeControlResult:
        self.calls.append(dict(kwargs))
        transition = RuntimeControlTransitionRecord(
            id="restore-transition-1",
            agent_id="agent-1",
            ai_system_id="system-1",
            control_epoch=5,
            previous_state=RuntimeControlState.ACTIVE,
            target_state=RuntimeControlState.INACTIVE,
            status=RuntimeControlTransitionStatus.APPLIED,
            revoked_through_agent_version=kwargs["expected_version"],
            reason=kwargs["reason"],
            requested_by=kwargs["principal"].user_id,
            requested_at=NOW,
            applied_at=NOW,
            incident_id=kwargs["incident_id"],
            evidence_reference=kwargs["evidence_reference"],
            version=2,
        )
        return RuntimeControlResult(
            agent_id="agent-1",
            ai_system_id="system-1",
            kill_switch_enabled=True,
            kill_switch_engaged=False,
            agent_version=kwargs["expected_version"] + 1,
            transition=transition,
        )


def owner() -> Principal:
    return Principal(user_id="system-owner")


def security() -> Principal:
    return Principal(
        user_id="security-approver",
        approval_areas=frozenset({ApprovalArea.SECURITY}),
    )


async def test_restore_request_is_created_from_remediation_snapshot() -> None:
    repo = Repository(source_context())
    audit = Audit()
    transaction = Transaction()
    service = RuntimeAssuranceRestoreRequestService(
        repo,
        audit,
        transaction,
        clock=lambda: NOW,
        id_factory=lambda: "restore-request-1",
    )
    result = await service.create(source_execution_id="engage-execution-1", principal=owner())
    assert result.action is RuntimeAssuranceRestoreAction.RESTORE_KILL_SWITCH
    assert result.remediation_digest == build_remediation_digest(repo.source)
    assert len(audit.events) == 1


async def test_restore_request_replay_is_idempotent() -> None:
    repo = Repository(source_context())
    repo.request = make_request(repo.source)
    audit = Audit()
    service = RuntimeAssuranceRestoreRequestService(repo, audit, Transaction(), clock=lambda: NOW)
    result = await service.create(source_execution_id="engage-execution-1", principal=owner())
    assert result.id == "restore-request-1"
    assert audit.events == []


async def test_restore_requester_cannot_approve_own_request() -> None:
    repo = Repository(source_context())
    repo.request = make_request(repo.source)
    service = RuntimeAssuranceRestoreDecisionService(
        repo, Audit(), Transaction(), clock=lambda: NOW
    )
    principal = Principal(
        user_id="system-owner",
        approval_areas=frozenset({ApprovalArea.SECURITY}),
    )
    with pytest.raises(ApplicationError) as exc:
        await service.decide(
            request_id=repo.request.id,
            decision=RuntimeAssuranceRestoreDecisionOutcome.APPROVED,
            reason="Self approval.",
            principal=principal,
        )
    assert exc.value.kind is ErrorKind.FORBIDDEN


async def test_security_approver_cannot_approve_stale_remediation() -> None:
    repo = Repository(source_context())
    repo.request = make_request(repo.source)
    repo.source = replace(repo.source, remediation_description="Remediation changed.")
    service = RuntimeAssuranceRestoreDecisionService(
        repo, Audit(), Transaction(), clock=lambda: NOW
    )
    with pytest.raises(ApplicationError) as exc:
        await service.decide(
            request_id=repo.request.id,
            decision=RuntimeAssuranceRestoreDecisionOutcome.APPROVED,
            reason="Approve stale request.",
            principal=security(),
        )
    assert exc.value.kind is ErrorKind.CONFLICT


async def test_rejected_restore_decision_cannot_execute() -> None:
    repo = Repository(source_context())
    repo.request = make_request(repo.source)
    repo.decision = make_decision(
        repo.request,
        outcome=RuntimeAssuranceRestoreDecisionOutcome.REJECTED,
    )
    service = RuntimeAssuranceRestoreExecutionService(
        repo, RuntimeControl(), Audit(), Transaction()
    )
    with pytest.raises(ApplicationError) as exc:
        await service.execute(decision_id=repo.decision.id, principal=owner())
    assert exc.value.kind is ErrorKind.CONFLICT


async def test_approved_restore_executes_only_deactivate_and_persists_receipt() -> None:
    repo = Repository(source_context())
    repo.request = make_request(repo.source)
    repo.decision = make_decision(repo.request)
    runtime_control = RuntimeControl()
    audit = Audit()
    service = RuntimeAssuranceRestoreExecutionService(
        repo,
        runtime_control,
        audit,
        Transaction(),
        id_factory=lambda: "restore-execution-1",
    )
    result = await service.execute(decision_id=repo.decision.id, principal=owner())
    assert result.previous_state is RuntimeControlState.ACTIVE
    assert result.target_state is RuntimeControlState.INACTIVE
    assert len(runtime_control.calls) == 1
    assert runtime_control.calls[0]["evidence_reference"] == restore_decision_evidence_reference(
        repo.decision
    )
    assert repo.execution == result
    assert audit.events[0]["action"] == "runtime_assurance.restore_executed"


async def test_pending_restore_transition_fails_closed_without_duplicate_deactivation() -> None:
    repo = Repository(source_context())
    repo.request = make_request(repo.source)
    repo.decision = make_decision(repo.request)
    repo.matching_transition = RuntimeControlTransitionRecord(
        id="restore-transition-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        control_epoch=5,
        previous_state=RuntimeControlState.ACTIVE,
        target_state=RuntimeControlState.INACTIVE,
        status=RuntimeControlTransitionStatus.PENDING,
        revoked_through_agent_version=8,
        reason="restore",
        requested_by="system-owner",
        requested_at=NOW,
        applied_at=None,
        incident_id="incident-1",
        evidence_reference=restore_decision_evidence_reference(repo.decision),
        version=1,
    )
    runtime_control = RuntimeControl()
    service = RuntimeAssuranceRestoreExecutionService(repo, runtime_control, Audit(), Transaction())
    with pytest.raises(ApplicationError) as exc:
        await service.execute(decision_id=repo.decision.id, principal=owner())
    assert exc.value.kind is ErrorKind.DEPENDENCY_UNAVAILABLE
    assert runtime_control.calls == []
