"""Race tests for Runtime Control around the external model-routing call."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_governance_api.application.model_routing import RequestModelRoutingDecision
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.model_routing import (
    GovernedRoutingModel,
    GovernedRoutingScope,
    ModelRoutingCommand,
    PolicyModelRouterDecision,
    RouterDecisionOutcome,
    RoutingEnforcementOutcome,
    RoutingWorkload,
)
from ai_governance_api.domain.runtime_control import RuntimeControlState
from governance_schemas import DataClassification, EntityStatus, RiskTier

NOW = datetime(2026, 8, 8, 21, 0, tzinfo=UTC)


def _scope() -> GovernedRoutingScope:
    return GovernedRoutingScope(
        ai_system_id="system-1",
        ai_system_version=1,
        ai_system_owner_id="system-owner",
        ai_system_status=EntityStatus.ACTIVE,
        risk_tier=RiskTier.MEDIUM,
        data_classification=DataClassification.INTERNAL,
        initiative_id="initiative-1",
        agent_id="agent-1",
        agent_version=2,
        agent_name="Knowledge agent",
        agent_owner_id="agent-owner",
        agent_status=EntityStatus.APPROVED,
        agent_approved_scope_digest="b" * 64,
        agent_next_review_at=NOW + timedelta(days=20),
        agent_allowed_model_ids=("model-1",),
        agent_max_cost=Decimal("0.50"),
        models=(
            GovernedRoutingModel(
                id="model-1",
                version=2,
                status=EntityStatus.APPROVED,
                routing_group="fast-small",
                allowed_data_classes=("internal",),
                approved_scope_digest="a" * 64,
                next_review_at=NOW + timedelta(days=30),
            ),
        ),
    )


def _command() -> ModelRoutingCommand:
    return ModelRoutingCommand(
        workflow_id="workflow-1",
        task_id="task-1",
        workload=RoutingWorkload.DOCUMENT_EXTRACTION,
        context_tokens_estimated=1000,
        max_output_tokens_estimated=500,
        structured_output_required=True,
        max_latency_ms=3000,
        max_cost_usd=Decimal("0.25"),
    )


class _ScopeReader:
    def __init__(self) -> None:
        self.reads = 0

    async def get(self, agent_id: str) -> GovernedRoutingScope | None:
        assert agent_id == "agent-1"
        self.reads += 1
        return _scope()


class _Router:
    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, request, *, correlation_id: str) -> PolicyModelRouterDecision:
        assert request.agent_name == "Knowledge agent"
        assert correlation_id == "attempt-1"
        self.calls += 1
        return PolicyModelRouterDecision(
            outcome=RouterDecisionOutcome.ACCEPTED,
            schema_version="1.0",
            routing_decision_id="router-decision-1",
            decided_at=NOW,
            workflow_id="workflow-1",
            task_id="task-1",
            selected_model_group="fast-small",
            rejected_model_group=None,
            reason="Mapped workload",
            reason_code=None,
            observed_value=None,
            required_value=None,
            rejected_candidates=(),
            policy_id="router-policy",
            policy_version="2026.08",
            policy_digest="c" * 64,
            service_version="1.0.0",
            environment="test",
        )


class _Store:
    def __init__(self) -> None:
        self.saved = []

    async def save(self, record):
        self.saved.append(record)
        return record

    async def list_for_agent(self, agent_id: str):
        return [record for record in self.saved if record.agent_id == agent_id]


class _Audit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def append(self, *, actor_id: str, action: str, record) -> None:
        assert actor_id == "agent-owner"
        self.actions.append(action)


class _Transaction:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        raise AssertionError("unexpected rollback")


class _SequenceGate:
    def __init__(self, states: list[RuntimeControlState]) -> None:
        self.states = states
        self.calls = 0

    async def state_for(self, agent_id: str) -> RuntimeControlState:
        assert agent_id == "agent-1"
        state = self.states[self.calls]
        self.calls += 1
        return state


def _case(states: list[RuntimeControlState]):
    reader = _ScopeReader()
    router = _Router()
    store = _Store()
    audit = _Audit()
    transaction = _Transaction()
    gate = _SequenceGate(states)
    case = RequestModelRoutingDecision(
        reader,
        router,
        store,
        audit,
        transaction,
        runtime_control_gate=gate,
        clock=lambda: NOW,
        id_factory=lambda: "attempt-1",
    )
    return case, reader, router, store, audit, transaction, gate


async def test_active_runtime_control_blocks_before_router_call() -> None:
    case, reader, router, store, audit, transaction, gate = _case([RuntimeControlState.ACTIVE])

    result = await case.execute(
        agent_id="agent-1",
        command=_command(),
        principal=Principal("agent-owner"),
    )

    assert result.outcome is RoutingEnforcementOutcome.BLOCKED
    assert result.reason_code == "kill_switch_engaged"
    assert reader.reads == 1
    assert router.calls == 0
    assert gate.calls == 1
    assert store.saved[-1] == result
    assert audit.actions[-1] == "model_routing.blocked"
    assert transaction.commits == 2


async def test_runtime_control_is_rechecked_after_router_before_allowing_result() -> None:
    case, reader, router, store, audit, transaction, gate = _case(
        [RuntimeControlState.INACTIVE, RuntimeControlState.ACTIVE]
    )

    result = await case.execute(
        agent_id="agent-1",
        command=_command(),
        principal=Principal("agent-owner"),
    )

    assert router.calls == 1
    assert result.outcome is RoutingEnforcementOutcome.BLOCKED
    assert result.reason_code == "kill_switch_engaged"
    assert result.router_decision_id == "router-decision-1"
    assert reader.reads == 1
    assert gate.calls == 2
    assert store.saved[-1] == result
    assert audit.actions[-1] == "model_routing.blocked"
    assert transaction.commits == 2
