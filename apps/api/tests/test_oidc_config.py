import pytest
from ai_governance_api.application.corporate_directory import CorporateDirectoryProfile
from ai_governance_api.config import AppEnvironment, Settings
from ai_governance_api.domain.identity import (
    AuthorizationProvenance,
    DirectoryAccountType,
    DirectoryIdentity,
    Principal,
)
from ai_governance_api.routers.authentication import current_identity
from httpx import AsyncClient
from pydantic import ValidationError

TENANT_ID = "11111111-1111-4111-8111-111111111111"


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


def test_entra_identity_mode_accepts_tenant_specific_allowlisted_issuer() -> None:
    settings = oidc_settings(
        oidc_identity_mode="entra",
        oidc_allowed_tenant_ids=TENANT_ID.upper(),
        oidc_issuer=f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        oidc_jwks_url=(
            f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
        ),
    )

    assert settings.oidc_allowed_tenant_id_set == frozenset({TENANT_ID})
    assert settings.oidc_entra_issuer_tenant_id == TENANT_ID


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"oidc_allowed_tenant_ids": ""}, "ALLOWED_TENANT_IDS is required"),
        ({"oidc_allowed_tenant_ids": "not-a-uuid"}, "contain only UUIDs"),
        (
            {
                "oidc_allowed_tenant_ids": TENANT_ID,
                "oidc_issuer": "https://login.microsoftonline.com/common/v2.0",
            },
            "explicit Microsoft Entra tenant UUID",
        ),
        (
            {
                "oidc_allowed_tenant_ids": TENANT_ID,
                "oidc_issuer": (
                    "https://login.microsoftonline.com/"
                    "22222222-2222-4222-8222-222222222222/v2.0"
                ),
            },
            "tenant must be present",
        ),
    ],
)
def test_entra_identity_mode_rejects_ambiguous_trust_configuration(
    overrides: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "oidc_identity_mode": "entra",
        "oidc_issuer": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        "oidc_jwks_url": (
            f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
        ),
    }
    values.update(overrides)

    with pytest.raises(ValidationError, match=message):
        oidc_settings(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"oidc_allowed_tenant_ids": TENANT_ID},
        {"oidc_guest_approvals_enabled": True},
    ],
)
def test_subject_mode_rejects_unused_entra_policy(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="require OIDC_IDENTITY_MODE=entra"):
        oidc_settings(**overrides)


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
        "tenant_id": None,
        "object_id": None,
        "account_type": None,
        "authorization_provenance": None,
        "directory_profile": None,
    }


async def test_current_identity_exposes_minimal_directory_provenance() -> None:
    principal = Principal(
        user_id=(
            f"{TENANT_ID}:22222222-2222-4222-8222-222222222222"
        ),
        directory_identity=DirectoryIdentity(
            tenant_id=TENANT_ID,
            object_id="22222222-2222-4222-8222-222222222222",
            account_type=DirectoryAccountType.MEMBER,
        ),
        authorization_provenance=AuthorizationProvenance(
            catalog_id="enterprise-entra-authorization",
            catalog_version="2026.08.1",
            catalog_digest="a" * 64,
        ),
    )

    response = await current_identity(principal, None)

    assert response.tenant_id == TENANT_ID
    assert response.object_id == "22222222-2222-4222-8222-222222222222"
    assert response.account_type is DirectoryAccountType.MEMBER
    assert response.authorization_provenance is not None
    assert response.authorization_provenance.catalog_id == (
        "enterprise-entra-authorization"
    )
    assert response.authorization_provenance.catalog_digest == "a" * 64
    assert response.authorization_provenance.group_resolution_source.value == "none"


async def test_current_identity_exposes_minimized_graph_profile() -> None:
    principal = Principal(
        user_id=f"{TENANT_ID}:22222222-2222-4222-8222-222222222222",
        directory_identity=DirectoryIdentity(
            tenant_id=TENANT_ID,
            object_id="22222222-2222-4222-8222-222222222222",
            account_type=DirectoryAccountType.MEMBER,
        ),
    )
    graph_profile = CorporateDirectoryProfile(
        tenant_id=TENANT_ID,
        object_id="22222222-2222-4222-8222-222222222222",
        display_name="Revisora de Segurança",
        email_or_upn="reviewer@example.com",
        department="Cyber Security",
        user_type="Member",
        group_object_ids=frozenset(
            {
                "33333333-3333-4333-8333-333333333333",
                "44444444-4444-4444-8444-444444444444",
            }
        ),
    )

    response = await current_identity(principal, graph_profile)

    assert response.directory_profile is not None
    assert response.directory_profile.department == "Cyber Security"
    assert "33333333-3333-4333-8333-333333333333" not in response.model_dump_json()
    assert "group_count" not in response.model_dump_json()


def test_graph_enrichment_requires_entra_oidc_and_confidential_client() -> None:
    with pytest.raises(ValidationError, match="OIDC_ENABLED=true"):
        Settings(microsoft_graph_enabled=True)

    entra_values = {
        "oidc_enabled": True,
        "oidc_identity_mode": "entra",
        "oidc_allowed_tenant_ids": TENANT_ID,
        "oidc_issuer": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        "oidc_jwks_url": (
            f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
        ),
    }
    with pytest.raises(ValidationError, match="CLIENT_ID must be a UUID"):
        Settings(**entra_values, microsoft_graph_enabled=True)
    with pytest.raises(ValidationError, match="CLIENT_SECRET is required"):
        Settings(
            **entra_values,
            microsoft_graph_enabled=True,
            microsoft_graph_client_id="55555555-5555-4555-8555-555555555555",
        )


def test_graph_secret_is_excluded_from_settings_representation() -> None:
    settings = Settings(
        oidc_enabled=True,
        oidc_identity_mode="entra",
        oidc_allowed_tenant_ids=TENANT_ID,
        oidc_issuer=f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        oidc_jwks_url=(
            f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
        ),
        microsoft_graph_enabled=True,
        microsoft_graph_client_id="55555555-5555-4555-8555-555555555555",
        microsoft_graph_client_secret="super-secret-value",
    )

    assert "super-secret-value" not in repr(settings)


@pytest.mark.parametrize(
    "claim_override",
    [
        {"oidc_entra_app_roles_claim": ""},
        {"oidc_entra_groups_claim": ""},
    ],
)
def test_entra_claim_paths_must_be_explicit(
    claim_override: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="Entra claim paths must not be empty"):
        oidc_settings(
            oidc_identity_mode="entra",
            oidc_allowed_tenant_ids=TENANT_ID,
            oidc_issuer=f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
            oidc_jwks_url=(
                f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
            ),
            **claim_override,
        )
