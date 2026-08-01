import pytest
from ai_governance_api.config import AppEnvironment, Settings
from httpx import AsyncClient
from pydantic import ValidationError


def oidc_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": AppEnvironment.LOCAL,
        "oidc_enabled": True,
        "oidc_issuer": "http://localhost:8081/realms/ai-governance",
        "oidc_jwks_url": (
            "http://localhost:8081/realms/ai-governance/protocol/openid-connect/certs"
        ),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize("algorithms", ["HS256", "none", "RS256,HS256", ""])
def test_symmetric_or_untrusted_algorithms_are_rejected(algorithms: str) -> None:
    with pytest.raises(ValidationError, match="trusted asymmetric algorithms"):
        oidc_settings(oidc_algorithms=algorithms)


def test_jwks_url_is_required_when_oidc_is_enabled() -> None:
    with pytest.raises(ValidationError, match="OIDC_JWKS_URL is required"):
        oidc_settings(oidc_jwks_url="")


def test_oidc_urls_cannot_embed_credentials() -> None:
    with pytest.raises(ValidationError, match="must not contain credentials"):
        oidc_settings(oidc_jwks_url="https://user:secret@identity.example.com/jwks")


def test_shared_environment_requires_tls_for_oidc_trust() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        oidc_settings(
            app_env=AppEnvironment.PRODUCTION,
            dev_auth_enabled=False,
            auto_create_schema=False,
            audit_hash_salt="production-secret",
            cors_origins="https://governance.example.com",
            object_storage_auto_create_bucket=False,
            object_storage_server_side_encryption="AES256",
            object_storage_endpoint_url="https://s3.example.com",
        )


async def test_current_identity_exposes_local_mapping(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/auth/me",
        headers={"X-User-Id": "security-reviewer", "X-User-Areas": "security,business"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "security-reviewer",
        "email": None,
        "approval_areas": ["business", "security"],
        "is_admin": False,
    }
