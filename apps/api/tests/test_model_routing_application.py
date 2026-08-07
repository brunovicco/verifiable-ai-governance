"""Application tests for model-routing orchestration and durable intent."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_governance_api.application.model_routing import (
    ModelRouterUnavailable,
    RequestModelRoutingDecision,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.model_routing import (
    GovernedRoutingModel,
    GovernedRoutingScope,
    ModelRoutingCommand,
    ModelRoutingDecisionRecord,
    PolicyModelRouterDecision,
    PolicyModelRouterRequest,
    RouterDecisionOutcome,
    RoutingDecisionSource,
    RoutingEnforcementOutcome,
    RoutingWorkload,
)
from governance_schemas import DataClassification, EntityStatus, RiskTier

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def scope(*, review_deadline: datetime | None = None) -> GovernedRoutingScope:
    """Return a currently approved runtime scope unless a deadline is supplied."""
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
        agent_next_review_at=review_deadline or NOW + timedelta(days=20),
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


def command() -> ModelRoutingCommand:
    """Return valid operational constraints."""
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


def accepted_decision() -> PolicyModelRouterDecision:
    """Return a policy decision compatible with the governed model scope."""
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


def rejected_decision() -> PolicyModelRouterDecision:
    """Return a policy decision that hard-rejects the requested workload."""
    return PolicyModelRouterDecision(
        outcome=RouterDecisionOutcome.REJECTED,
        schema_version="1.0",
        routing_decision_id="router-decision-1",
        decided_at=NOW,
        workflow_id="workflow-1",
        task_id="task-1",
        selected_model_group=None,
        rejected_model_group="fast-small",
        reason="Internal data is not authorized for this group",
        reason_code="data_classification_not_authorized",
        observed_value="internal",
        required_value="public",
        rejected_candidates=(),
        policy_id="router-policy",
        policy_version="2026.08",
        policy_digest="c" * 64,
        service_version="1.0.0",
        environment="test",
    )


class ScopeReader:
    """Return a configured scope and count freshness reads."""

    def __init__(self, value: GovernedRoutingScope) -> None:
        self.value = value
        self.reads = 0

    async def get(self, agent_id: str) -> GovernedRoutingScope | None:
        assert agent_id == "agent-1"
        self.reads += 1
        return self.value


class Router:
    """Return a configured decision or typed dependency failure."""

    def __init__(self, *, unavailable: bool = False, rejected: bool = False) -> None:
        self.unavailable = unavailable
        self.rejected = rejected
        self.requests: list[PolicyModelRouterRequest] = []

    async def decide(
        self,
        request: PolicyModelRouterRequest,
        *,
        correlation_id: str,
    ) -> PolicyModelRouterDecision:
        assert correlation_id == "attempt-1"
        self.requests.append(request)
        if self.unavailable:
            raise ModelRouterUnavailable("unavailable")
        if self.rejected:
            return rejected_decision()
        return accepted_decision()


class Store:
    """Capture each pending and completed persistence projection."""

    def __init__(self) -> None:
        self.saved: list[ModelRoutingDecisionRecord] = []

    async def save(
        self,
        record: ModelRoutingDecisionRecord,
    ) -> ModelRoutingDecisionRecord:
        self.saved.append(record)
        return record

    async def list_for_agent(self, agent_id: str) -> list[ModelRoutingDecisionRecord]:
        return [record for record in self.saved if record.agent_id == agent_id]


class Audit:
    """Capture routing lifecycle events."""

    def __init__(self) -> None:
        self.actions: list[str] = []

    async def append(
        self,
        *,
        actor_id: str,
        action: str,
        record: ModelRoutingDecisionRecord,
    ) -> None:
        assert actor_id == "agent-owner"
        assert record.id == "attempt-1"
        self.actions.append(action)


class Transaction:
    """Count application transaction boundaries."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def use_case(
    governed_scope: GovernedRoutingScope,
    *,
    router: Router | None = None,
) -> tuple[RequestModelRoutingDecision, ScopeReader, Router, Store, Audit, Transaction]:
    """Build the use case with deterministic in-memory ports."""
    reader = ScopeReader(governed_scope)
    actual_router = router or Router()
    store = Store()
    audit = Audit()
    transaction = Transaction()
    return (
        RequestModelRoutingDecision(
            reader,
            actual_router,
            store,
            audit,
            transaction,
            clock=lambda: NOW,
            id_factory=lambda: "attempt-1",
        ),
        reader,
        actual_router,
        store,
        audit,
        transaction,
    )


async def test_allowed_decision_persists_intent_before_external_call_and_provenance() -> None:
    case, reader, router, store, audit, transaction = use_case(scope())

    result = await case.execute(
        agent_id="agent-1",
        command=command(),
        principal=Principal("agent-owner"),
    )

    assert [record.outcome for record in store.saved] == [
        RoutingEnforcementOutcome.PENDING,
        RoutingEnforcementOutcome.ALLOWED,
    ]
    assert result.policy_digest == "c" * 64
    assert result.selected_model_group == "fast-small"
    assert reader.reads == 2
    assert len(router.requests) == 1
    assert audit.actions == ["model_routing.requested", "model_routing.allowed"]
    assert transaction.commits == 2
    assert transaction.rollbacks == 0


async def test_local_expired_review_blocks_without_calling_router() -> None:
    case, reader, router, store, _, transaction = use_case(scope(review_deadline=NOW))

    result = await case.execute(
        agent_id="agent-1",
        command=command(),
        principal=Principal("agent-owner"),
    )

    assert result.outcome is RoutingEnforcementOutcome.BLOCKED
    assert result.reason_code == "agent_review_not_current"
    assert reader.reads == 1
    assert router.requests == []
    assert len(store.saved) == 2
    assert transaction.commits == 2


async def test_dependency_failure_is_persisted_as_fail_closed_result() -> None:
    case, _, router, store, audit, _ = use_case(scope(), router=Router(unavailable=True))

    result = await case.execute(
        agent_id="agent-1",
        command=command(),
        principal=Principal("agent-owner"),
    )

    assert len(router.requests) == 1
    assert result.outcome is RoutingEnforcementOutcome.DEPENDENCY_UNAVAILABLE
    assert result.reason_code == "router_unavailable"
    assert store.saved[-1] == result
    assert audit.actions[-1] == "model_routing.blocked"


async def test_router_rejection_blocks_with_provider_source_and_reason() -> None:
    case, reader, router, store, audit, transaction = use_case(
        scope(), router=Router(rejected=True)
    )

    result = await case.execute(
        agent_id="agent-1",
        command=command(),
        principal=Principal("agent-owner"),
    )

    assert len(router.requests) == 1
    assert result.outcome is RoutingEnforcementOutcome.BLOCKED
    assert result.decision_source is RoutingDecisionSource.POLICY_MODEL_ROUTER
    assert result.reason_code == "data_classification_not_authorized"
    assert result.router_decision_id == "router-decision-1"
    assert reader.reads == 2
    assert store.saved[-1] == result
    assert audit.actions == ["model_routing.requested", "model_routing.blocked"]
    assert transaction.commits == 2
    assert transaction.rollbacks == 0
