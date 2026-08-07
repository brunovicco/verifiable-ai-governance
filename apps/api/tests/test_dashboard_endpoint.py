"""HTTP and persistence tests for the portfolio-wide governance dashboard."""

from datetime import UTC, datetime, timedelta

from ai_governance_api.database import SessionFactory
from ai_governance_api.domain.incidents import ExceptionStatus, IncidentStatus
from ai_governance_api.models import (
    Agent,
    AISystem,
    Assessment,
    Incident,
    Initiative,
    ModelAsset,
    ModelRoutingDecisionEntry,
    PolicyException,
    ReviewSubmission,
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

NOW = datetime.now(UTC)
ANY_USER_HEADERS = {"X-User-Id": "any-authenticated-user"}


async def seed_dashboard_fixtures() -> None:
    """Persist one instance of each metric source the dashboard aggregates."""
    async with SessionFactory() as session:
        initiative = Initiative(
            id="dashboard-initiative",
            name="Dashboard fixture initiative",
            description="Exercise the portfolio-wide dashboard aggregation end to end.",
            business_owner_id="dashboard-owner",
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
            risk_score=60,
            risk_tier=RiskTier.HIGH,
            policy_id="governance-policy",
            policy_version="2026.08",
            required_documents=["ai-impact-assessment", "ripd"],
        )
        ai_system = AISystem(
            id="dashboard-system",
            initiative=initiative,
            name="Dashboard fixture system",
            purpose="Exercise the dashboard aggregation.",
            owner_id="dashboard-owner",
            status=EntityStatus.ACTIVE,
            risk_tier=RiskTier.HIGH,
            production=True,
            metadata_json={},
        )
        model = ModelAsset(
            id="dashboard-model",
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
            approved_scope_digest="a" * 64,
            reviewed_by="architecture-reviewer",
            reviewed_at=NOW - timedelta(days=100),
            next_review_at=NOW - timedelta(days=1),
            review_reference="ARCH-2026-300",
        )
        agent = Agent(
            id="dashboard-agent",
            ai_system=ai_system,
            name="Knowledge agent",
            purpose="Extract structured facts from approved internal documents.",
            owner_id="dashboard-owner",
            agent_version="1.0.0",
            deployment_region="Brazil South",
            autonomy_level=AutonomyLevel.A1_RECOMMENDATION,
            allowed_models=[model.id],
            tools=[],
            permissions=[],
            human_approval_points=[],
            kill_switch_enabled=True,
            status=EntityStatus.APPROVED,
            approved_scope_digest="b" * 64,
            reviewed_by="security-reviewer",
            reviewed_at=NOW - timedelta(days=10),
            next_review_at=NOW + timedelta(days=10),
            review_reference="SEC-2026-300",
        )
        routing_decision = ModelRoutingDecisionEntry(
            id="dashboard-routing-decision",
            ai_system_id=ai_system.id,
            initiative_id=initiative.id,
            agent_id=agent.id,
            requested_by="dashboard-owner",
            requested_at=NOW,
            scope_digest="c" * 64,
            workflow_id="workflow-1",
            task_id="task-1",
            workload="document_extraction",
            risk_level="high",
            data_classification="internal",
            context_tokens_estimated=1000,
            max_output_tokens_estimated=500,
            structured_output_required=True,
            max_latency_ms=3000,
            max_cost_usd="0.75",
            outcome="blocked",
            decision_source="governance_registry",
            reason="Requested cost ceiling exceeds the reviewed agent limit",
            reason_code="cost_limit_exceeded",
            rejected_candidates=[],
            version=2,
            created_at=NOW,
            updated_at=NOW,
        )
        incident = Incident(
            id="dashboard-incident",
            ai_system_id=ai_system.id,
            title="Agent exceeded declared cost ceiling repeatedly",
            severity=RiskTier.HIGH,
            status=IncidentStatus.REMEDIATING,
            description="Agent requested invocations above its reviewed cost limit.",
            detected_at=NOW - timedelta(days=5),
            owner_id="dashboard-owner",
            remediation_owner_id="dashboard-owner",
            remediation_description="Lower the agent's declared cost ceiling.",
            remediation_due_at=NOW - timedelta(days=1),
            version=2,
        )
        assessment = Assessment(
            id="dashboard-assessment",
            initiative_id=initiative.id,
            assessment_type="ai-impact-assessment",
            schema_version="1.0",
            status=EntityStatus.UNDER_REVIEW,
            answers={},
            risk_score=60,
            risk_tier=RiskTier.HIGH,
            assessed_by="dashboard-owner",
        )
        review_submission = ReviewSubmission(
            id="dashboard-review-submission",
            initiative_id=initiative.id,
            review_round=1,
            status=EntityStatus.APPROVED,
            submitted_by="dashboard-owner",
            submitted_at=NOW - timedelta(hours=48),
            resolved_at=NOW - timedelta(hours=24),
            revision_summary="Initial submission.",
            policy_id="governance-policy",
            policy_version="2026.08",
            risk_score=60,
            risk_tier=RiskTier.HIGH,
            initiative_snapshot={},
            assessment_snapshots=[],
        )
        exception = PolicyException(
            id="dashboard-exception",
            incident_id=incident.id,
            ai_system_id=ai_system.id,
            requested_by="dashboard-owner",
            requested_at=NOW,
            purpose="Keep serving cached results while remediation is in progress.",
            scope_description="Bypass real-time verification for read-only queries.",
            compensating_controls="Manual spot-check every hour by Security.",
            expires_at=NOW + timedelta(days=2),
            status=ExceptionStatus.APPROVED,
            decided_by="admin-1",
            decided_at=NOW,
        )
        session.add_all(
            [
                initiative,
                ai_system,
                model,
                agent,
                routing_decision,
                incident,
                assessment,
                review_submission,
                exception,
            ]
        )
        await session.commit()


async def test_dashboard_aggregates_every_metric_source(client: AsyncClient) -> None:
    await seed_dashboard_fixtures()

    response = await client.get("/api/v1/dashboard", headers=ANY_USER_HEADERS)

    assert response.status_code == 200
    body = response.json()

    assert body["routing_outcomes"]["blocked"] == 1
    assert body["routing_outcomes"]["cost_limit_exceeded"] == 1
    assert ["cost_limit_exceeded", 1] in body["routing_outcomes"]["top_blocked_reason_codes"]

    high_tier_review = body["review_status_by_risk_tier"]["high"]
    assert high_tier_review["expired"] == 1
    assert high_tier_review["current"] == 1

    assert body["incidents"]["remediating"] == 1
    assert body["incidents"]["overdue_remediation"] == 1

    assert body["exceptions_by_state"]["active"] == 1

    assert body["residual_risk_by_tier"]["high"] == 1

    assert body["assessment_coverage"]["required"] == 2
    assert body["assessment_coverage"]["submitted"] == 1
    assert body["assessment_coverage"]["ratio"] == 0.5

    assert body["cycle_times"]["review_round_avg_hours"] == 24.0
    assert body["cycle_times"]["review_round_samples"] == 1
    assert body["cycle_times"]["incident_remediation_avg_hours"] is None
    assert body["cycle_times"]["incident_remediation_samples"] == 0

    assert body["drift_available"] is False
    assert body["control_effectiveness_available"] is False


async def test_dashboard_requires_only_authentication_not_ownership(
    client: AsyncClient,
) -> None:
    await seed_dashboard_fixtures()

    response = await client.get("/api/v1/dashboard", headers={"X-User-Id": "someone-unrelated"})

    assert response.status_code == 200
