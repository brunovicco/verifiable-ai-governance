from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ai_governance_api.application.runtime_assurance_actuation import (
    RuntimeAssuranceActuationRequestService,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationSourceContext,
)
from ai_governance_api.domain.runtime_assurance_responses import RuntimeAssuranceResponseAction
from ai_governance_api.errors import ApplicationError

NOW = datetime(2026, 8, 9, 20, 45, tzinfo=UTC)


def source_context(
    *,
    include_kill_switch: bool = True,
    status: IncidentStatus = IncidentStatus.OPEN,
) -> RuntimeAssuranceActuationSourceContext:
    actions = (RuntimeAssuranceResponseAction.INVESTIGATE_FAILURES,)
    if include_kill_switch:
        actions += (RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH,)
    return RuntimeAssuranceActuationSourceContext(
        recommendation_id="recommendation-1",
        recommendation_digest="a" * 64,
        promotion_id="promotion-1",
        evaluation_id="evaluation-1",
        incident_id="incident-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        ai_system_owner_id="system-owner",
        advisory_only=True,
        recommendation_actions=actions,
        current_incident_status=status,
    )


class Repository:
    def __init__(self) -> None:
        self.context = source_context()
        self.existing: RuntimeAssuranceActuationRequest | None = None
        self.saved: RuntimeAssuranceActuationRequest | None = None
        self.save_count = 0

    async def get_context(self, recommendation_id: str, *, for_update: bool = False):
        assert recommendation_id == "recommendation-1"
        return self.context

    async def get_request_by_recommendation_action(self, recommendation_id: str, action):
        assert recommendation_id == "recommendation-1"
        assert action is RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH
        return self.existing

    async def save_request(self, request):
        self.saved = request
        self.existing = request
        self.save_count += 1
        return request


class Audit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def append(self, **kwargs) -> None:
        self.events.append(kwargs)


class Transaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def service(repository: Repository, audit: Audit, transaction: Transaction):
    return RuntimeAssuranceActuationRequestService(
        repository,
        audit,
        transaction,
        clock=lambda: NOW,
        id_factory=lambda: "request-1",
    )


async def test_create_pending_request_with_strong_binding_and_minimized_audit() -> None:
    repository = Repository()
    original_context = repository.context
    audit = Audit()
    transaction = Transaction()

    result = await service(repository, audit, transaction).create(
        recommendation_id="recommendation-1",
        principal=Principal(user_id="system-owner"),
    )

    assert result.id == "request-1"
    assert result.action is RuntimeAssuranceActuationAction.ENGAGE_KILL_SWITCH
    assert result.state.value == "pending"
    assert result.recommendation_id == original_context.recommendation_id
    assert result.promotion_id == original_context.promotion_id
    assert result.evaluation_id == original_context.evaluation_id
    assert result.incident_id == original_context.incident_id
    assert result.agent_id == original_context.agent_id
    assert result.ai_system_id == original_context.ai_system_id
    assert repository.context == original_context
    assert repository.save_count == 1
    assert transaction.commits == 1

    event = audit.events[0]
    assert event["action"] == "runtime_assurance.actuation_requested"
    assert set(event["payload"]) == {
        "recommendation_id",
        "agent_id",
        "ai_system_id",
        "action",
        "request_digest",
    }
    forbidden = {
        "rationale_codes",
        "telemetry",
        "prompt",
        "model_output",
        "credentials",
        "authorization",
        "token",
    }
    assert forbidden.isdisjoint(event["payload"])


async def test_create_is_idempotent_per_recommendation_and_action() -> None:
    repository = Repository()
    audit = Audit()
    transaction = Transaction()
    use_case = service(repository, audit, transaction)

    first = await use_case.create(
        recommendation_id="recommendation-1",
        principal=Principal(user_id="system-owner"),
    )
    audit.events.clear()
    replay = await use_case.create(
        recommendation_id="recommendation-1",
        principal=Principal(user_id="system-owner"),
    )

    assert replay == first
    assert repository.save_count == 1
    assert audit.events == []
    assert transaction.commits == 2


async def test_recommendation_without_consider_kill_switch_fails_closed() -> None:
    repository = Repository()
    repository.context = source_context(include_kill_switch=False)
    audit = Audit()
    transaction = Transaction()

    with pytest.raises(ApplicationError, match="does not support"):
        await service(repository, audit, transaction).create(
            recommendation_id="recommendation-1",
            principal=Principal(user_id="system-owner"),
        )

    assert repository.saved is None
    assert audit.events == []
    assert transaction.rollbacks == 1


async def test_unauthorized_principal_cannot_create_request() -> None:
    repository = Repository()
    audit = Audit()
    transaction = Transaction()

    with pytest.raises(ApplicationError, match="AI system owner"):
        await service(repository, audit, transaction).create(
            recommendation_id="recommendation-1",
            principal=Principal(user_id="agent-owner"),
        )

    assert repository.saved is None
    assert audit.events == []
    assert transaction.rollbacks == 1


async def test_admin_can_create_request() -> None:
    repository = Repository()
    audit = Audit()
    transaction = Transaction()

    result = await service(repository, audit, transaction).create(
        recommendation_id="recommendation-1",
        principal=Principal(user_id="governance-admin", is_admin=True),
    )
    assert result.requested_by == "governance-admin"


async def test_closed_incident_cannot_create_new_request() -> None:
    repository = Repository()
    repository.context = source_context(status=IncidentStatus.CLOSED)
    audit = Audit()
    transaction = Transaction()

    with pytest.raises(ApplicationError, match="closed incident"):
        await service(repository, audit, transaction).create(
            recommendation_id="recommendation-1",
            principal=Principal(user_id="system-owner"),
        )
    assert repository.saved is None
    assert transaction.rollbacks == 1


async def test_existing_request_with_cross_agent_binding_fails_closed() -> None:
    repository = Repository()
    audit = Audit()
    transaction = Transaction()
    first = await service(repository, audit, transaction).create(
        recommendation_id="recommendation-1",
        principal=Principal(user_id="system-owner"),
    )
    repository.existing = replace(first, agent_id="agent-2")

    with pytest.raises(ApplicationError, match="binding"):
        await service(repository, audit, transaction).create(
            recommendation_id="recommendation-1",
            principal=Principal(user_id="system-owner"),
        )
