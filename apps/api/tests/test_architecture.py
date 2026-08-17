import ast
from pathlib import Path
from typing import Any

import pytest
from ai_governance_api.config import AppEnvironment, Settings
from ai_governance_api.dependencies import get_policy_evaluator
from ai_governance_api.main import app
from governance_schemas import PolicyContext, PolicyDecision, RiskBreakdown, RiskTier
from httpx import AsyncClient
from pydantic import ValidationError

USER_HEADERS = {"X-User-Id": "architecture-test-owner"}
API_SOURCE = Path(__file__).parents[1] / "src" / "ai_governance_api"
GOVERNANCE_INTELLIGENCE_SCHEMA_SOURCE = (
    Path(__file__).parents[3]
    / "packages/governance-schemas/src/governance_schemas/governance_intelligence.py"
)
GOVERNANCE_INTELLIGENCE_APPLICATION_SOURCE = (
    API_SOURCE / "application/governance_intelligence.py"
)
GOVERNANCE_INTELLIGENCE_AUDIT_ADAPTER_SOURCE = (
    API_SOURCE / "adapters/governance_intelligence_audit.py"
)
VERIFIED_EVIDENCE_KNOWLEDGE_ADAPTER_SOURCE = (
    API_SOURCE / "adapters/governance_knowledge_evidence.py"
)


class FixedPolicyEvaluator:
    def __init__(self) -> None:
        self.evaluated_context: PolicyContext | None = None

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        self.evaluated_context = context
        return PolicyDecision(
            policy_id="test-policy",
            policy_version="2026.07",
            score=17,
            tier=RiskTier.LOW,
            breakdown=RiskBreakdown(impact=3, data=5, autonomy=4, exposure=5, regulatory=0),
            approvals=[],
            required_documents=["test-assessment"],
        )


def initiative_payload() -> dict[str, Any]:
    return {
        "name": "Iniciativa com porta injetada",
        "description": "Valida que o caso de uso depende do contrato de política.",
        "business_area": "Arquitetura",
        "intended_users": "Equipe interna de arquitetura",
        "decision_impact": "informational",
        "data_classification": "internal",
        "autonomy_level": "a1_recommendation",
        "hosting_model": "self_hosted",
    }


async def test_policy_evaluator_can_be_replaced_at_composition_root(
    client: AsyncClient,
) -> None:
    evaluator = FixedPolicyEvaluator()
    app.dependency_overrides[get_policy_evaluator] = lambda: evaluator
    try:
        response = await client.post(
            "/api/v1/initiatives",
            json=initiative_payload(),
            headers=USER_HEADERS,
        )
    finally:
        app.dependency_overrides.pop(get_policy_evaluator, None)

    assert response.status_code == 201
    assert response.json()["policy_id"] == "test-policy"
    assert response.json()["required_documents"] == ["test-assessment"]
    assert evaluator.evaluated_context is not None


async def test_application_error_is_mapped_by_http_adapter(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/initiatives/does-not-exist",
        headers=USER_HEADERS,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Initiative not found"}


def test_production_rejects_development_authentication() -> None:
    with pytest.raises(ValidationError, match="DEV_AUTH_ENABLED must be false"):
        Settings(
            app_env=AppEnvironment.PRODUCTION,
            oidc_enabled=True,
            oidc_issuer="https://identity.example.com",
            oidc_jwks_url="https://identity.example.com/jwks",
            dev_auth_enabled=True,
            auto_create_schema=False,
            audit_hash_salt="production-secret",
        )


def test_production_accepts_explicit_fail_closed_configuration() -> None:
    settings = Settings(
        app_env=AppEnvironment.PRODUCTION,
        app_version="2026.07.31",
        oidc_enabled=True,
        oidc_issuer="https://identity.example.com",
        oidc_jwks_url="https://identity.example.com/jwks",
        dev_auth_enabled=False,
        auto_create_schema=False,
        audit_hash_salt="production-secret",
        cors_origins="https://governance.example.com",
        object_storage_auto_create_bucket=False,
        object_storage_server_side_encryption="AES256",
        object_storage_endpoint_url="https://s3.example.com",
    )

    assert settings.app_version == "2026.07.31"
    assert settings.cors_origin_list == ["https://governance.example.com"]


def test_policy_model_router_requires_explicit_per_agent_credentials() -> None:
    settings = Settings(
        policy_model_router_enabled=True,
        policy_model_router_base_url="https://router.example.com",
        policy_model_router_api_keys_json='{"Knowledge agent":"secret"}',
    )

    assert settings.policy_model_router_api_key_map == {"Knowledge agent": "secret"}
    assert "secret" not in repr(settings)

    with pytest.raises(ValidationError, match="API_KEYS_JSON is required"):
        Settings(
            policy_model_router_enabled=True,
            policy_model_router_base_url="https://router.example.com",
            policy_model_router_api_keys_json="{}",
        )


@pytest.mark.parametrize(
    "relative_path",
    [
        "domain/assessments.py",
        "domain/reviews.py",
        "application/assessments.py",
        "application/controls.py",
        "domain/evidence.py",
        "domain/identity.py",
        "domain/asset_registry.py",
        "domain/directory_authorization.py",
        "domain/directory_access.py",
        "domain/directory_authorization_cache.py",
        "domain/backups.py",
        "domain/model_routing.py",
        "domain/runtime_assurance.py",
        "domain/runtime_assurance_incidents.py",
        "domain/runtime_assurance_responses.py",
        "domain/runtime_telemetry.py",
        "domain/incidents.py",
        "application/authentication.py",
        "application/corporate_directory.py",
        "application/directory_authorization.py",
        "application/directory_access.py",
        "application/directory_authorization_cache.py",
        "application/backups.py",
        "application/evidence.py",
        "application/model_routing.py",
        "application/runtime_assurance.py",
        "application/runtime_assurance_incidents.py",
        "application/runtime_assurance_responses.py",
        "application/runtime_telemetry.py",
        "application/incidents.py",
        "application/dashboard.py",
        "application/governance_intelligence.py",
        "application/governance_knowledge.py",
    ],
)
def test_application_core_does_not_import_delivery_or_persistence_frameworks(
    relative_path: str,
) -> None:
    source = (API_SOURCE / relative_path).read_text(encoding="utf-8")
    imports = {
        node.module.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imports.update(
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert imports.isdisjoint({"fastapi", "sqlalchemy", "pydantic"})


def test_governance_intelligence_core_has_no_agentic_framework_dependencies() -> None:
    sources = (
        (API_SOURCE / "application/governance_intelligence.py").read_text(encoding="utf-8"),
        (API_SOURCE / "application/governance_knowledge.py").read_text(encoding="utf-8"),
        GOVERNANCE_INTELLIGENCE_SCHEMA_SOURCE.read_text(encoding="utf-8"),
    )
    for source in sources:
        imports = {
            node.module.split(".")[0]
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imports.update(
            alias.name.split(".")[0]
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Import)
            for alias in node.names
        )

        assert imports.isdisjoint(
            {
                "anthropic",
                "asago",
                "chromadb",
                "deep_agents",
                "deepagents",
                "langchain",
                "langgraph",
                "llama_index",
                "openai",
                "pinecone",
                "qdrant_client",
                "weaviate",
            }
        )


def test_governance_intelligence_port_exposes_advisory_capabilities_only() -> None:
    source = (API_SOURCE / "application/governance_intelligence.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    port = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GovernanceIntelligencePort"
    )
    methods = {
        node.name for node in port.body if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }

    assert methods == {
        "analyze_evidence",
        "analyze_policy",
        "assist_intake",
        "identify_risks",
        "suggest_controls",
    }
    assert methods.isdisjoint(
        {
            "activate_kill_switch",
            "approve",
            "approve_control",
            "authorize",
            "expand_scope",
            "modify_runtime_policy",
            "release_model",
            "release_tool",
            "restore_runtime",
            "sign_authorization",
        }
    )


def test_governance_intelligence_port_requires_verified_knowledge_sources() -> None:
    source = (API_SOURCE / "application/governance_intelligence.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    port = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GovernanceIntelligencePort"
    )
    port_source = ast.get_source_segment(source, port)

    assert port_source is not None
    assert "VerifiedGovernanceKnowledgeSource" in port_source
    assert "GovernanceSourceReference" not in port_source


def test_verified_evidence_knowledge_adapter_has_no_probabilistic_dependencies() -> None:
    source = VERIFIED_EVIDENCE_KNOWLEDGE_ADAPTER_SOURCE.read_text(encoding="utf-8")
    imports = {
        node.module.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imports.update(
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert imports.isdisjoint(
        {
            "anthropic",
            "chromadb",
            "deep_agents",
            "deepagents",
            "langchain",
            "langgraph",
            "llama_index",
            "openai",
            "pinecone",
            "qdrant_client",
            "weaviate",
        }
    )


def test_verified_evidence_knowledge_adapter_exposes_resolution_only() -> None:
    source = VERIFIED_EVIDENCE_KNOWLEDGE_ADAPTER_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    adapter = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "VerifiedEvidenceKnowledgeAdapter"
    )
    methods = {
        node.name for node in adapter.body if isinstance(node, ast.AsyncFunctionDef)
    }

    assert methods == {"can_read", "resolve"}
    assert "GovernanceFindingCandidate" not in source


def test_governed_analysis_orchestration_has_no_probabilistic_dependencies() -> None:
    source = GOVERNANCE_INTELLIGENCE_APPLICATION_SOURCE.read_text(encoding="utf-8")
    imports = {
        node.module.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imports.update(
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert imports.isdisjoint(
        {
            "anthropic",
            "chromadb",
            "deep_agents",
            "deepagents",
            "langchain",
            "langgraph",
            "llama_index",
            "openai",
            "pinecone",
            "qdrant_client",
            "weaviate",
        }
    )


def test_governed_analysis_orchestration_exposes_advisory_execution_only() -> None:
    source = GOVERNANCE_INTELLIGENCE_APPLICATION_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    use_case = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RunGovernanceIntelligenceAnalysis"
    )
    public_async_methods = {
        node.name
        for node in use_case.body
        if isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith("_")
    }

    assert public_async_methods == {"execute"}
    assert "GovernanceFindingEnvelope" in source
    assert "VerifiedGovernanceKnowledgeSource" in source
    assert "SignedRuntimeAuthorization" not in source
    assert "RuntimeControl" not in source
    assert "Approval" not in source


def test_governance_intelligence_audit_adapter_cannot_persist_content_fields() -> None:
    source = GOVERNANCE_INTELLIGENCE_AUDIT_ADAPTER_SOURCE.read_text(encoding="utf-8")

    assert "source.content" not in source
    assert "finding.statement" not in source
    assert "full_prompt" not in source
    assert "chain_of_thought" not in source
    assert "storage_bucket" not in source
    assert "storage_key" not in source
