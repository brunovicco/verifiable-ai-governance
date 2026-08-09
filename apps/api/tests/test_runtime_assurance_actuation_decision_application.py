from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ai_governance_api.application.runtime_assurance_actuation_decisions import (
    RuntimeAssuranceActuationDecisionService,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationRequestState,
    RuntimeAssuranceActuationSourceContext,
)
from ai_governance_api.domain.runtime_assurance_actuation_decisions import (
    RuntimeAssuranceActuationDecision,
    RuntimeAssuranceActuationDecisionContext,
    RuntimeAssuranceActuationDecisionOutcome,
)
from ai_governance_api.domain.runtime_assurance_responses import RuntimeAssuranceResponseAction
from ai_governance_api.errors import ApplicationError, ErrorKind
from governance_schemas import ApprovalArea

NOW = datetime(2026, 8, 9, 21, 15, tzinfo=UTC)


class _Repository:
    def __init__(self, context: RuntimeAssuranceActuationDecisionContext | None) -> None:
        self.context = context
        self.existing: RuntimeAssuranceActuationDecision | None = None
        self.saved: RuntimeAssuranceActuationDecision | None = None
        self.for_update_values: list[bool] = []

    async def get_context(
        self,
        request_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceActuationDecisionContext | None:
        del request_id
        self.for_update_values.append(for_update)
        return self.context

    async def get_decision_by_request_id(
        self,
        request_id: str,
    ) -> RuntimeAssuranceActuationDecision | None:
        del request_id
        return self.existing

    async def save_decision(
        self,
        decision: RuntimeAssuranceActuationDecision,
    ) -> RuntimeAssuranceActuationDecision:
        self.saved = decision
        self.existing = decision
        return decision


class _Audit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def append(self, **kwargs: object) -> None:
        self.events.append(dict(kwargs))


class _Transaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _context(
    *,
    status: IncidentStatus = IncidentStatus.OPEN,
) -> RuntimeAssuranceActuationDecisionContext:
    request = RuntimeAssuranceActuationRequest(
        id="request-1",
        schema_version="1.0",
        recommendation_id="recommendation-1",
        recommendation_digest="a" * 64,
        promotion_id="promotion-1",
        evaluation_id="evaluation-1",
        incident_id="incident-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        action=RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH,
        state=RuntimeAssuranceActuationRequestState.PENDING,
        requested_by="requester-1",
        requested_at=NOW,
        request_digest="b" * 64,
    )
    source = RuntimeAssuranceActuationSourceContext(
        recommendation_id=request.recommendation_id,
        recommendation_digest=request.recommendation_digest,
        promotion_id=request.promotion_id,
        evaluation_id=request.evaluation_id,
        incident_id=request.incident_id,
        agent_id=request.agent_id,
        ai_system_id=request.ai_system_id,
        ai_system_owner_id="owner-1",
        advisory_only=True,
        recommendation_actions=(RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH,),
        current_incident_status=status,
    )
    return RuntimeAssuranceActuationDecisionContext(request=request, source=source)


def _security_principal(user_id: str = "security-approver") -> Principal:
    return Principal(
        user_id=user_id,
        approval_areas=frozenset({ApprovalArea.SECURITY}),
    )


def _service(
    context: RuntimeAssuranceActuationDecisionContext | None = None,
) -> tuple[
    RuntimeAssuranceActuationDecisionService,
    _Repository,
    _Audit,
    _Transaction,
]:
    repository = _Repository(context if context is not None else _context())
    audit = _Audit()
    transaction = _Transaction()
    service = RuntimeAssuranceActuationDecisionService(
        repository,
        audit,
        transaction,
        clock=lambda: NOW,
        id_factory=lambda: "decision-1",
    )
    return service, repository, audit, transaction


@pytest.mark.asyncio
async def test_security_approver_can_approve_without_runtime_mutation() -> None:
    context = _context()
    original_request = context.request
    service, repository, audit, transaction = _service(context)

    decision = await service.decide(
        request_id=context.request.id,
        decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
        reason="Reviewed evidence and approved containment.",
        principal=_security_principal(),
    )

    assert decision.decision is RuntimeAssuranceActuationDecisionOutcome.APPROVED
    assert decision.approval_area is ApprovalArea.SECURITY
    assert decision.request_digest == context.request.request_digest
    assert context.request == original_request
    assert repository.saved == decision
    assert repository.for_update_values == [True]
    assert transaction.commits == 1
    assert transaction.rollbacks == 0
    assert len(audit.events) == 1
    event = audit.events[0]
    assert event["action"] == "runtime_assurance.actuation_approved"
    payload = event["payload"]
    assert isinstance(payload, dict)
    assert set(payload) == {
        "request_id",
        "agent_id",
        "ai_system_id",
        "action",
        "approval_area",
        "decision_digest",
    }
    assert "reason" not in payload


@pytest.mark.asyncio
async def test_security_approver_can_reject_closed_incident() -> None:
    service, _, audit, _ = _service(_context(status=IncidentStatus.CLOSED))
    decision = await service.decide(
        request_id="request-1",
        decision=RuntimeAssuranceActuationDecisionOutcome.REJECTED,
        reason="Incident is already closed; actuation is unnecessary.",
        principal=_security_principal(),
    )
    assert decision.decision is RuntimeAssuranceActuationDecisionOutcome.REJECTED
    assert audit.events[0]["action"] == "runtime_assurance.actuation_rejected"


@pytest.mark.asyncio
async def test_requester_cannot_decide_own_request_even_with_security_capability() -> None:
    service, _, _, transaction = _service()
    with pytest.raises(ApplicationError) as exc_info:
        await service.decide(
            request_id="request-1",
            decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
            reason="Self approval must fail.",
            principal=_security_principal("requester-1"),
        )
    assert exc_info.value.kind is ErrorKind.FORBIDDEN
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_generic_admin_cannot_bypass_security_capability() -> None:
    service, _, _, transaction = _service()
    with pytest.raises(ApplicationError) as exc_info:
        await service.decide(
            request_id="request-1",
            decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
            reason="Admin without security approval area.",
            principal=Principal(user_id="admin-1", is_admin=True),
        )
    assert exc_info.value.kind is ErrorKind.FORBIDDEN
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_admin_with_security_capability_still_respects_sod() -> None:
    service, _, _, _ = _service()
    principal = Principal(
        user_id="admin-security",
        is_admin=True,
        approval_areas=frozenset({ApprovalArea.SECURITY}),
    )
    decision = await service.decide(
        request_id="request-1",
        decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
        reason="Independent security review completed.",
        principal=principal,
    )
    assert decision.decided_by == "admin-security"


@pytest.mark.asyncio
async def test_cannot_approve_closed_incident() -> None:
    service, _, _, transaction = _service(_context(status=IncidentStatus.CLOSED))
    with pytest.raises(ApplicationError) as exc_info:
        await service.decide(
            request_id="request-1",
            decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
            reason="This approval should fail closed.",
            principal=_security_principal(),
        )
    assert exc_info.value.kind is ErrorKind.CONFLICT
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_identical_replay_returns_same_evidence_without_second_audit() -> None:
    service, repository, audit, transaction = _service()
    principal = _security_principal()
    first = await service.decide(
        request_id="request-1",
        decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
        reason="Reviewed evidence and approved containment.",
        principal=principal,
    )
    second = await service.decide(
        request_id="request-1",
        decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
        reason="  Reviewed evidence and approved containment.  ",
        principal=principal,
    )
    assert second == first
    assert repository.saved == first
    assert len(audit.events) == 1
    assert transaction.commits == 2


@pytest.mark.asyncio
async def test_conflicting_second_decision_returns_conflict() -> None:
    service, _, _, transaction = _service()
    principal = _security_principal()
    await service.decide(
        request_id="request-1",
        decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
        reason="Approved after security review.",
        principal=principal,
    )
    with pytest.raises(ApplicationError) as exc_info:
        await service.decide(
            request_id="request-1",
            decision=RuntimeAssuranceActuationDecisionOutcome.REJECTED,
            reason="Changed decision.",
            principal=principal,
        )
    assert exc_info.value.kind is ErrorKind.CONFLICT
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_same_outcome_with_different_reason_is_not_idempotent() -> None:
    service, _, _, _ = _service()
    principal = _security_principal()
    await service.decide(
        request_id="request-1",
        decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
        reason="Reason A.",
        principal=principal,
    )
    with pytest.raises(ApplicationError) as exc_info:
        await service.decide(
            request_id="request-1",
            decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
            reason="Reason B.",
            principal=principal,
        )
    assert exc_info.value.kind is ErrorKind.CONFLICT


@pytest.mark.asyncio
async def test_different_actor_cannot_claim_idempotent_replay() -> None:
    service, _, _, _ = _service()
    await service.decide(
        request_id="request-1",
        decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
        reason="Approved after security review.",
        principal=_security_principal("security-a"),
    )
    with pytest.raises(ApplicationError) as exc_info:
        await service.decide(
            request_id="request-1",
            decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
            reason="Approved after security review.",
            principal=_security_principal("security-b"),
        )
    assert exc_info.value.kind is ErrorKind.CONFLICT


@pytest.mark.asyncio
async def test_get_allows_requester_to_view_decision() -> None:
    service, repository, _, _ = _service()
    created = await service.decide(
        request_id="request-1",
        decision=RuntimeAssuranceActuationDecisionOutcome.REJECTED,
        reason="Rejected by security review.",
        principal=_security_principal(),
    )
    repository.existing = created
    result = await service.get(
        request_id="request-1",
        principal=Principal(user_id="requester-1"),
    )
    assert result == created


@pytest.mark.asyncio
async def test_tampered_existing_decision_fails_closed() -> None:
    service, repository, _, _ = _service()
    created = await service.decide(
        request_id="request-1",
        decision=RuntimeAssuranceActuationDecisionOutcome.APPROVED,
        reason="Approved after security review.",
        principal=_security_principal(),
    )
    repository.existing = replace(created, request_digest="c" * 64)
    with pytest.raises(ApplicationError) as exc_info:
        await service.get(
            request_id="request-1",
            principal=Principal(user_id="requester-1"),
        )
    assert exc_info.value.kind is ErrorKind.CONFLICT
