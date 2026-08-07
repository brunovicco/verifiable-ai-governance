"""HTTP and persistence tests for runtime model-routing enforcement."""

from datetime import UTC, datetime, timedelta

from ai_governance_api.application.model_routing import ModelRouterUnavailable
from ai_governance_api.database import SessionFactory
from ai_governance_api.dependencies import get_policy_model_router
from ai_governance_api.domain.asset_registry import (
    AgentReviewCandidate,
    ModelReviewCandidate,
    agent_scope_digest,
    model_scope_digest,
)
from ai_governance_api.domain.model_routing import (
    PolicyModelRouterDecision,
    PolicyModelRouterRequest,
    RouterDecisionOutcome,
)
from ai_governance_api.main import app
from ai_governance_api.models import (
    Agent,
    AISystem,
    AuditEvent,
    Initiative,
    ModelAsset,
    ModelRoutingDecisionEntry,
)
from governance_schemas import (
    AutonomyLevel,
    DataClassification,
    DecisionImpact,
    EntityStatus,
    HostingModel,
    RiskTier,
)
from httpx import AsyncClient
from sqlalchemy import select

OWNER_HEADERS = {"X-User-Id": "agent-owner"}


class AcceptedRouter:
    """Return an accepted decision for a configured logical model group."""

    def __init__(self, selected_group: str = "fast-small") -> None:
        self.selected_group = selected_group

    async def decide(
        self,
        request: PolicyModelRouterRequest,
        *,
        correlation_id: str,
    ) -> PolicyModelRouterDecision:
        assert correlation_id
        return PolicyModelRouterDecision(
            outcome=RouterDecisionOutcome.ACCEPTED,
            schema_version="1.0",
            routing_decision_id=f"router-{correlation_id}",
            decided_at=datetime.now(UTC),
            workflow_id=request.workflow_id,
            task_id=request.task_id,
            selected_model_group=self.selected_group,
            rejected_model_group=None,
            reason="Mapped workload to configured group",
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


class RejectingRouter:
    """Return an explicit hard rejection for every requested workload."""

    async def decide(
        self,
        request: PolicyModelRouterRequest,
        *,
        correlation_id: str,
    ) -> PolicyModelRouterDecision:
        assert correlation_id
        return PolicyModelRouterDecision(
            outcome=RouterDecisionOutcome.REJECTED,
            schema_version="1.0",
            routing_decision_id=f"router-{correlation_id}",
            decided_at=datetime.now(UTC),
            workflow_id=request.workflow_id,
            task_id=request.task_id,
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


class UnavailableRouter:
    """Simulate a policy-model-router dependency that cannot be trusted."""

    async def decide(
        self,
        request: PolicyModelRouterRequest,
        *,
        correlation_id: str,
    ) -> PolicyModelRouterDecision:
        assert correlation_id
        raise ModelRouterUnavailable("Policy model router request failed")


async def seed_reviewed_agent() -> str:
    """Persist a current reviewed model and agent without exercising unrelated workflows."""
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        initiative = Initiative(
            id="initiative-routing",
            name="Runtime routing initiative",
            description="Exercise durable policy-model-router enforcement evidence.",
            business_owner_id="initiative-owner",
            business_area="AI Platform",
            intended_users="Internal platform services",
            decision_impact=DecisionImpact.INFORMATIONAL,
            data_classification=DataClassification.INTERNAL,
            autonomy_level=AutonomyLevel.A1_RECOMMENDATION,
            hosting_model=HostingModel.SELF_HOSTED,
            affects_rights=False,
            executes_actions=False,
            personal_data=False,
            sensitive_data=False,
            children_data=False,
            external_facing=False,
            regulated_context=False,
            international_processing=False,
            inference_countries=[],
            uses_rag=False,
            uses_agents=True,
            uses_mcp=False,
            uses_custom_model=False,
            status=EntityStatus.APPROVED,
            risk_score=20,
            risk_tier=RiskTier.MEDIUM,
            policy_id="governance-policy",
            policy_version="2026.08",
            required_documents=[],
        )
        ai_system = AISystem(
            id="system-routing",
            initiative=initiative,
            name="Runtime routing system",
            purpose="Request model decisions before every governed model invocation.",
            owner_id="system-owner",
            status=EntityStatus.ACTIVE,
            risk_tier=RiskTier.MEDIUM,
            production=True,
            metadata_json={},
        )
        model_digest = model_scope_digest(
            ModelReviewCandidate(
                provider="Example AI",
                model_name="governed-small",
                model_version="2026-08-01",
                routing_group="fast-small",
                deployment_region="Brazil South",
                approved_use_cases=("document extraction",),
                prohibited_use_cases=(),
                allowed_data_classes=("internal",),
                evaluation_baseline={"dataset": "document-eval-v1"},
                deprecation_date=None,
            )
        )
        model = ModelAsset(
            id="model-routing",
            ai_system=ai_system,
            provider="Example AI",
            model_name="governed-small",
            model_version="2026-08-01",
            routing_group="fast-small",
            deployment_region="Brazil South",
            approved_use_cases=["document extraction"],
            prohibited_use_cases=[],
            allowed_data_classes=["internal"],
            status=EntityStatus.APPROVED,
            evaluation_baseline={"dataset": "document-eval-v1"},
            approved_scope_digest=model_digest,
            reviewed_by="architecture-reviewer",
            reviewed_at=now,
            next_review_at=now + timedelta(days=30),
            review_reference="ARCH-2026-200",
        )
        agent_digest = agent_scope_digest(
            AgentReviewCandidate(
                name="Knowledge agent",
                purpose="Extract structured facts from approved internal documents.",
                owner_id="agent-owner",
                agent_version="1.0.0",
                deployment_region="Brazil South",
                autonomy_level=AutonomyLevel.A1_RECOMMENDATION,
                allowed_models=(model.id,),
                tools=(),
                permissions=(),
                max_cost=0.50,
                max_runtime_seconds=30,
                human_approval_points=(),
                kill_switch_enabled=True,
            )
        )
        agent = Agent(
            id="agent-routing",
            ai_system=ai_system,
            name="Knowledge agent",
            purpose="Extract structured facts from approved internal documents.",
            owner_id="agent-owner",
            agent_version="1.0.0",
            deployment_region="Brazil South",
            autonomy_level=AutonomyLevel.A1_RECOMMENDATION,
            allowed_models=[model.id],
            tools=[],
            permissions=[],
            max_cost=0.50,
            max_runtime_seconds=30,
            human_approval_points=[],
            kill_switch_enabled=True,
            status=EntityStatus.APPROVED,
            approved_scope_digest=agent_digest,
            reviewed_by="security-reviewer",
            reviewed_at=now,
            next_review_at=now + timedelta(days=20),
            review_reference="SEC-2026-200",
        )
        session.add_all([initiative, ai_system, model, agent])
        await session.commit()
    return agent.id


def request_payload() -> dict[str, object]:
    """Return a valid public routing command."""
    return {
        "workflow_id": "workflow-1",
        "task_id": "task-1",
        "workload": "document_extraction",
        "context_tokens_estimated": 1000,
        "max_output_tokens_estimated": 500,
        "structured_output_required": True,
        "max_latency_ms": 3000,
        "max_cost_usd": "0.25",
    }


async def test_endpoint_persists_allowed_decision_and_audit_provenance(
    client: AsyncClient,
) -> None:
    agent_id = await seed_reviewed_agent()
    app.dependency_overrides[get_policy_model_router] = lambda: AcceptedRouter()
    try:
        response = await client.post(
            f"/api/v1/agents/{agent_id}/routing-decisions",
            json=request_payload(),
            headers=OWNER_HEADERS,
        )
        history = await client.get(
            f"/api/v1/agents/{agent_id}/routing-decisions",
            headers=OWNER_HEADERS,
        )
    finally:
        app.dependency_overrides.pop(get_policy_model_router, None)

    assert response.status_code == 200
    decision = response.json()
    assert decision["outcome"] == "allowed"
    assert decision["selected_model_group"] == "fast-small"
    assert decision["policy_digest"] == "c" * 64
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [decision["id"]]

    async with SessionFactory() as session:
        persisted = await session.scalar(select(ModelRoutingDecisionEntry))
        audit_events = list(
            await session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "model_routing_decision")
                .order_by(AuditEvent.entity_version)
            )
        )
    assert persisted is not None
    assert persisted.outcome == "allowed"
    assert [event.action for event in audit_events] == [
        "model_routing.requested",
        "model_routing.allowed",
    ]
    assert audit_events[-1].payload["policy_digest"] == "c" * 64


async def test_endpoint_blocks_router_group_outside_current_registry_scope(
    client: AsyncClient,
) -> None:
    agent_id = await seed_reviewed_agent()
    app.dependency_overrides[get_policy_model_router] = lambda: AcceptedRouter("reasoning-strong")
    try:
        response = await client.post(
            f"/api/v1/agents/{agent_id}/routing-decisions",
            json=request_payload(),
            headers=OWNER_HEADERS,
        )
    finally:
        app.dependency_overrides.pop(get_policy_model_router, None)

    assert response.status_code == 422
    assert response.json()["outcome"] == "blocked"
    assert response.json()["reason_code"] == "selected_model_group_not_approved"


async def test_endpoint_blocks_explicit_router_rejection(client: AsyncClient) -> None:
    agent_id = await seed_reviewed_agent()
    app.dependency_overrides[get_policy_model_router] = lambda: RejectingRouter()
    try:
        response = await client.post(
            f"/api/v1/agents/{agent_id}/routing-decisions",
            json=request_payload(),
            headers=OWNER_HEADERS,
        )
    finally:
        app.dependency_overrides.pop(get_policy_model_router, None)

    assert response.status_code == 422
    body = response.json()
    assert body["outcome"] == "blocked"
    assert body["decision_source"] == "policy_model_router"
    assert body["reason_code"] == "data_classification_not_authorized"


async def test_endpoint_returns_503_when_router_dependency_is_unavailable(
    client: AsyncClient,
) -> None:
    agent_id = await seed_reviewed_agent()
    app.dependency_overrides[get_policy_model_router] = lambda: UnavailableRouter()
    try:
        response = await client.post(
            f"/api/v1/agents/{agent_id}/routing-decisions",
            json=request_payload(),
            headers=OWNER_HEADERS,
        )
    finally:
        app.dependency_overrides.pop(get_policy_model_router, None)

    assert response.status_code == 503
    body = response.json()
    assert body["outcome"] == "dependency_unavailable"
    assert body["reason_code"] == "router_unavailable"

    async with SessionFactory() as session:
        persisted = await session.scalar(select(ModelRoutingDecisionEntry))
    assert persisted is not None
    assert persisted.outcome == "dependency_unavailable"
