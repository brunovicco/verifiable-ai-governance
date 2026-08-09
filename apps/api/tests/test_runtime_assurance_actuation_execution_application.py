from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ai_governance_api.application.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecutionService,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationRequestState,
    RuntimeAssuranceActuationSourceContext,
    build_actuation_request_digest,
)
from ai_governance_api.domain.runtime_assurance_actuation_decisions import (
    RuntimeAssuranceActuationDecision,
    RuntimeAssuranceActuationDecisionOutcome,
    build_actuation_decision_digest,
)
from ai_governance_api.domain.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecutionContext,
    build_actuation_execution_receipt,
    runtime_actuation_decision_evidence_reference,
)
from ai_governance_api.domain.runtime_assurance_responses import RuntimeAssuranceResponseAction
from ai_governance_api.domain.runtime_control import (
    RuntimeControlResult,
    RuntimeControlState,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
)
from ai_governance_api.errors import ApplicationError, ErrorKind
from governance_schemas import ApprovalArea

REQUESTED_AT = datetime(2026, 8, 9, 20, 0, tzinfo=UTC)
DECIDED_AT = datetime(2026, 8, 9, 20, 5, tzinfo=UTC)
APPLIED_AT = datetime(2026, 8, 9, 20, 10, tzinfo=UTC)


def make_context(
    *,
    outcome: RuntimeAssuranceActuationDecisionOutcome = (
        RuntimeAssuranceActuationDecisionOutcome.APPROVED
    ),
    incident_status: IncidentStatus = IncidentStatus.OPEN,
    engaged: bool = False,
    transition: RuntimeControlTransitionRecord | None = None,
) -> RuntimeAssuranceActuationExecutionContext:
    source = RuntimeAssuranceActuationSourceContext(
        recommendation_id="recommendation-1",
        recommendation_digest="a" * 64,
        promotion_id="promotion-1",
        evaluation_id="evaluation-1",
        incident_id="incident-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        ai_system_owner_id="system-owner",
        advisory_only=True,
        recommendation_actions=(RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH,),
        current_incident_status=incident_status,
    )
    action = RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH
    state = RuntimeAssuranceActuationRequestState.PENDING
    request_digest = build_actuation_request_digest(
        request_id="request-1",
        recommendation_id=source.recommendation_id,
        recommendation_digest=source.recommendation_digest,
        promotion_id=source.promotion_id,
        evaluation_id=source.evaluation_id,
        incident_id=source.incident_id,
        agent_id=source.agent_id,
        ai_system_id=source.ai_system_id,
        action=action,
        state=state,
        requested_by="system-owner",
        requested_at=REQUESTED_AT,
    )
    request = RuntimeAssuranceActuationRequest(
        id="request-1",
        schema_version="1.0",
        recommendation_id=source.recommendation_id,
        recommendation_digest=source.recommendation_digest,
        promotion_id=source.promotion_id,
        evaluation_id=source.evaluation_id,
        incident_id=source.incident_id,
        agent_id=source.agent_id,
        ai_system_id=source.ai_system_id,
        action=action,
        state=state,
        requested_by="system-owner",
        requested_at=REQUESTED_AT,
        request_digest=request_digest,
    )
    decision_digest = build_actuation_decision_digest(
        decision_id="decision-1",
        request_id=request.id,
        request_digest=request.request_digest,
        action=action,
        decision=outcome,
        approval_area=ApprovalArea.SECURITY,
        decided_by="security-approver",
        decided_at=DECIDED_AT,
        reason="Reviewed by Security.",
    )
    decision = RuntimeAssuranceActuationDecision(
        id="decision-1",
        schema_version="1.0",
        request_id=request.id,
        request_digest=request.request_digest,
        action=action,
        decision=outcome,
        approval_area=ApprovalArea.SECURITY,
        decided_by="security-approver",
        decided_at=DECIDED_AT,
        reason="Reviewed by Security.",
        decision_digest=decision_digest,
    )
    return RuntimeAssuranceActuationExecutionContext(
        decision=decision,
        request=request,
        source=source,
        agent_version=7,
        kill_switch_enabled=True,
        kill_switch_engaged=engaged,
        incident_status=incident_status,
        matching_transition=transition,
    )


def transition_for(
    context: RuntimeAssuranceActuationExecutionContext,
    *,
    status: RuntimeControlTransitionStatus = RuntimeControlTransitionStatus.APPLIED,
) -> RuntimeControlTransitionRecord:
    return RuntimeControlTransitionRecord(
        id="transition-1",
        agent_id=context.request.agent_id,
        ai_system_id=context.request.ai_system_id,
        control_epoch=3,
        previous_state=RuntimeControlState.INACTIVE,
        target_state=RuntimeControlState.ACTIVE,
        status=status,
        revoked_through_agent_version=7,
        reason="Governed Runtime Assurance actuation execution",
        requested_by="system-owner",
        requested_at=APPLIED_AT,
        applied_at=(APPLIED_AT if status is RuntimeControlTransitionStatus.APPLIED else None),
        incident_id=context.request.incident_id,
        evidence_reference=runtime_actuation_decision_evidence_reference(context.decision),
        version=2 if status is RuntimeControlTransitionStatus.APPLIED else 1,
    )


class Repository:
    def __init__(self, context: RuntimeAssuranceActuationExecutionContext) -> None:
        self.context = context
        self.execution = None
        self.saved = []

    async def get_context(self, decision_id: str):
        assert decision_id == self.context.decision.id
        return self.context

    async def get_execution_by_decision_id(self, decision_id: str):
        assert decision_id == self.context.decision.id
        return self.execution

    async def save_execution(self, execution):
        self.execution = execution
        self.saved.append(execution)
        return execution


class RuntimeControl:
    def __init__(self, result: RuntimeControlResult | None = None) -> None:
        self.result = result
        self.calls = []

    async def activate(self, **kwargs):
        self.calls.append(dict(kwargs))
        assert self.result is not None
        transition = replace(
            self.result.transition,
            requested_by=kwargs["principal"].user_id,
        )
        return replace(self.result, transition=transition)


class Audit:
    def __init__(self) -> None:
        self.events = []

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


def service_for(context: RuntimeAssuranceActuationExecutionContext):
    repository = Repository(context)
    transition = (
        transition_for(context)
        if context.decision.decision is RuntimeAssuranceActuationDecisionOutcome.APPROVED
        else None
    )
    result = (
        RuntimeControlResult(
            agent_id=context.request.agent_id,
            ai_system_id=context.request.ai_system_id,
            kill_switch_enabled=True,
            kill_switch_engaged=True,
            agent_version=8,
            transition=transition,
        )
        if transition is not None
        else None
    )
    runtime_control = RuntimeControl(result)
    audit = Audit()
    transaction = Transaction()
    service = RuntimeAssuranceActuationExecutionService(
        repository,
        runtime_control,
        audit,
        transaction,
        id_factory=lambda: "execution-1",
    )
    return service, repository, runtime_control, audit, transaction


async def test_approved_execution_calls_runtime_control_once_and_persists_receipt() -> None:
    context = make_context()
    service, repository, runtime_control, audit, transaction = service_for(context)

    receipt = await service.execute(
        decision_id=context.decision.id,
        principal=Principal(user_id="system-owner"),
    )

    assert receipt.execution_digest
    assert receipt.decision_digest == context.decision.decision_digest
    assert receipt.runtime_transition_id == "transition-1"
    assert receipt.resulting_agent_version == 8
    assert len(runtime_control.calls) == 1
    call = runtime_control.calls[0]
    assert call["expected_version"] == 7
    assert call["incident_id"] == "incident-1"
    assert context.decision.decision_digest in str(call["evidence_reference"])
    assert len(repository.saved) == 1
    assert audit.events[0]["action"] == "runtime_assurance.actuation_executed"
    assert transaction.commits >= 2


async def test_existing_receipt_is_idempotent_without_second_runtime_call() -> None:
    context = make_context()
    transition = transition_for(context)
    bound = replace(context, matching_transition=transition)
    service, repository, runtime_control, audit, _ = service_for(bound)
    repository.execution = build_actuation_execution_receipt(
        execution_id="execution-1",
        context=bound,
        transition=transition,
    )

    result = await service.execute(
        decision_id=context.decision.id,
        principal=Principal(user_id="system-owner"),
    )

    assert result == repository.execution
    assert runtime_control.calls == []
    assert audit.events == []


async def test_applied_transition_without_receipt_is_recovered_without_actuation() -> None:
    context = make_context()
    transition = transition_for(context)
    bound = replace(context, matching_transition=transition, kill_switch_engaged=True)
    service, repository, runtime_control, audit, _ = service_for(bound)

    receipt = await service.execute(
        decision_id=context.decision.id,
        principal=Principal(user_id="system-owner"),
    )

    assert receipt.runtime_transition_id == transition.id
    assert runtime_control.calls == []
    assert len(repository.saved) == 1
    assert audit.events[0]["action"] == "runtime_assurance.actuation_execution_recovered"


async def test_pending_transition_fails_closed_without_duplicate_actuation() -> None:
    context = make_context()
    pending = transition_for(context, status=RuntimeControlTransitionStatus.PENDING)
    bound = replace(context, matching_transition=pending)
    service, _, runtime_control, _, _ = service_for(bound)

    with pytest.raises(ApplicationError) as raised:
        await service.execute(
            decision_id=context.decision.id,
            principal=Principal(user_id="system-owner"),
        )

    assert raised.value.kind is ErrorKind.DEPENDENCY_UNAVAILABLE
    assert runtime_control.calls == []


async def test_rejected_decision_cannot_execute() -> None:
    context = make_context(outcome=RuntimeAssuranceActuationDecisionOutcome.REJECTED)
    service, _, runtime_control, _, transaction = service_for(context)

    with pytest.raises(ApplicationError) as raised:
        await service.execute(
            decision_id=context.decision.id,
            principal=Principal(user_id="system-owner"),
        )

    assert raised.value.kind is ErrorKind.CONFLICT
    assert runtime_control.calls == []
    assert transaction.rollbacks == 1


async def test_security_approver_without_operational_authority_cannot_execute() -> None:
    context = make_context()
    service, _, runtime_control, _, transaction = service_for(context)

    with pytest.raises(ApplicationError) as raised:
        await service.execute(
            decision_id=context.decision.id,
            principal=Principal(
                user_id="security-approver",
                approval_areas=frozenset({ApprovalArea.SECURITY}),
            ),
        )

    assert raised.value.kind is ErrorKind.FORBIDDEN
    assert runtime_control.calls == []
    assert transaction.rollbacks == 1


async def test_admin_can_execute_after_independent_security_approval() -> None:
    context = make_context()
    service, _, runtime_control, _, _ = service_for(context)

    receipt = await service.execute(
        decision_id=context.decision.id,
        principal=Principal(user_id="ops-admin", is_admin=True),
    )

    assert receipt.runtime_transition_id == "transition-1"
    assert len(runtime_control.calls) == 1
