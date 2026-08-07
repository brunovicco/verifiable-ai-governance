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
        "domain/incidents.py",
        "application/authentication.py",
        "application/corporate_directory.py",
        "application/directory_authorization.py",
        "application/directory_access.py",
        "application/directory_authorization_cache.py",
        "application/backups.py",
        "application/evidence.py",
        "application/model_routing.py",
        "application/incidents.py",
        "application/dashboard.py",
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
