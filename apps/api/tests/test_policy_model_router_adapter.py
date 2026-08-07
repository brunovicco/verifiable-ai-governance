"""Contract tests for the bounded policy-model-router HTTP adapter."""

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from ai_governance_api.adapters.policy_model_router import PolicyModelRouterHttpAdapter
from ai_governance_api.application.model_routing import ModelRouterUnavailable
from ai_governance_api.domain.model_routing import (
    PolicyModelRouterRequest,
    RouterDecisionOutcome,
    RoutingWorkload,
)
from governance_schemas import DataClassification, RiskTier

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
AGENT_NAME = "Knowledge agent"
POLICY_DIGEST = "a" * 64


def router_request() -> PolicyModelRouterRequest:
    """Return the exact trusted request expected by the external contract."""
    return PolicyModelRouterRequest(
        schema_version="1.0",
        requested_at=NOW,
        workflow_id="workflow-1",
        task_id="task-1",
        agent_name=AGENT_NAME,
        workload=RoutingWorkload.DOCUMENT_EXTRACTION,
        risk_level=RiskTier.MEDIUM,
        data_classification=DataClassification.INTERNAL,
        context_tokens_estimated=1000,
        max_output_tokens_estimated=500,
        structured_output_required=True,
        max_latency_ms=3000,
        max_cost_usd=Decimal("0.25"),
    )


def adapter(handler: httpx.MockTransport) -> PolicyModelRouterHttpAdapter:
    """Build the adapter with deterministic credentials and network transport."""
    return PolicyModelRouterHttpAdapter(
        base_url="https://router.example.com",
        api_keys={AGENT_NAME: "agent-secret"},
        timeout_seconds=1,
        max_response_bytes=8192,
        transport=handler,
    )


async def test_adapter_sends_minimized_request_and_parses_accepted_decision() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://router.example.com/route"
        assert request.headers["X-API-Key"] == "agent-secret"
        assert request.headers["X-Correlation-Id"] == "attempt-1"
        payload = json.loads(request.read())
        assert "prompt" not in payload
        assert "document_content" not in payload
        assert payload["risk_level"] == "medium"
        return httpx.Response(
            200,
            json={
                "schema_version": "1.0",
                "routing_decision_id": "router-decision-1",
                "decided_at": NOW.isoformat(),
                "workflow_id": "workflow-1",
                "task_id": "task-1",
                "selected_model_group": "fast-small",
                "reason": "Mapped workload to configured group",
                "rejected_candidates": [
                    {
                        "model_group": "reasoning-medium",
                        "reason": "Workload maps elsewhere",
                        "reason_code": "workload_mapped_elsewhere",
                        "observed_value": "document_extraction",
                        "required_value": "cashflow_analysis",
                    }
                ],
                "policy_id": "router-policy",
                "policy_version": "2026.08",
                "policy_digest": POLICY_DIGEST,
                "service_version": "1.0.0",
                "environment": "test",
            },
        )

    decision = await adapter(httpx.MockTransport(handler)).decide(
        router_request(),
        correlation_id="attempt-1",
    )

    assert decision.outcome is RouterDecisionOutcome.ACCEPTED
    assert decision.selected_model_group == "fast-small"
    assert decision.policy_digest == POLICY_DIGEST
    assert decision.rejected_candidates[0].reason_code == "workload_mapped_elsewhere"


async def test_adapter_preserves_auditable_hard_rejection() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "no_viable_model_group",
                    "message": "No viable model group",
                },
                "decision": {
                    "schema_version": "1.0",
                    "routing_decision_id": "router-rejection-1",
                    "decided_at": NOW.isoformat(),
                    "workflow_id": "workflow-1",
                    "task_id": "task-1",
                    "workload": "document_extraction",
                    "rejected_model_group": "fast-small",
                    "reason": "Internal data is not authorized",
                    "reason_code": "data_classification_not_authorized",
                    "observed_value": "internal",
                    "required_value": "public",
                    "policy_id": "router-policy",
                    "policy_version": "2026.08",
                    "policy_digest": POLICY_DIGEST,
                    "service_version": "1.0.0",
                    "environment": "test",
                },
            },
        )

    decision = await adapter(httpx.MockTransport(handler)).decide(
        router_request(),
        correlation_id="attempt-1",
    )

    assert decision.outcome is RouterDecisionOutcome.REJECTED
    assert decision.rejected_model_group == "fast-small"
    assert decision.reason_code == "data_classification_not_authorized"


async def test_adapter_rejects_unbound_or_oversized_responses() -> None:
    def mismatched(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "schema_version": "1.0",
                "routing_decision_id": "router-decision-1",
                "decided_at": NOW.isoformat(),
                "workflow_id": "another-workflow",
                "task_id": "task-1",
                "selected_model_group": "fast-small",
                "reason": "Mismatch",
                "rejected_candidates": [],
                "policy_id": "router-policy",
                "policy_version": "2026.08",
                "policy_digest": POLICY_DIGEST,
                "service_version": "1.0.0",
                "environment": "test",
            },
        )

    with pytest.raises(ModelRouterUnavailable, match="does not match"):
        await adapter(httpx.MockTransport(mismatched)).decide(
            router_request(),
            correlation_id="attempt-1",
        )

    oversized = PolicyModelRouterHttpAdapter(
        base_url="https://router.example.com",
        api_keys={AGENT_NAME: "agent-secret"},
        timeout_seconds=1,
        max_response_bytes=1024,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 1025)),
    )
    with pytest.raises(ModelRouterUnavailable, match="too large"):
        await oversized.decide(router_request(), correlation_id="attempt-1")


async def test_adapter_maps_transport_failure_to_unavailable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(ModelRouterUnavailable, match="request failed"):
        await adapter(httpx.MockTransport(handler)).decide(
            router_request(),
            correlation_id="attempt-1",
        )


async def test_adapter_fails_before_network_without_agent_credential() -> None:
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = PolicyModelRouterHttpAdapter(
        base_url="https://router.example.com",
        api_keys={},
        timeout_seconds=1,
        max_response_bytes=8192,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelRouterUnavailable, match="credential"):
        await client.decide(router_request(), correlation_id="attempt-1")
    assert not called
