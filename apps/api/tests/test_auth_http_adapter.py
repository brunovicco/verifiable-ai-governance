import pytest
from ai_governance_api import auth
from ai_governance_api.application.authentication import (
    IdentityProviderUnavailable,
    InvalidAccessToken,
)
from ai_governance_api.application.corporate_directory import (
    CorporateDirectoryProfile,
    CorporateDirectoryResponseInvalid,
    CorporateDirectoryUnavailable,
)
from ai_governance_api.config import OidcIdentityMode, Settings
from ai_governance_api.dependencies import (
    CorporateDirectoryRequestSnapshot,
    get_authorized_principal,
    get_corporate_directory_profile,
)
from ai_governance_api.domain.identity import (
    DirectoryGroupClaims,
    DirectoryGroupClaimState,
    DirectoryGroupResolutionSource,
    Principal,
)
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


class FixedAuthenticator:
    def __init__(self, result: Principal | Exception) -> None:
        self._result = result

    def execute(self, token: str) -> Principal:
        assert token == "access-token"
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FixedDirectoryResolver:
    def __init__(self, result: CorporateDirectoryProfile | Exception) -> None:
        self._result = result

    async def execute(
        self,
        principal: Principal,
        user_assertion: str,
    ) -> CorporateDirectoryProfile:
        assert principal.user_id == "corporate-reviewer"
        assert user_assertion == "access-token"
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class CapturingAuthorizationResolver:
    """Capture the group snapshot selected by the HTTP composition boundary."""

    def __init__(self) -> None:
        self.group_object_ids: frozenset[str] | None = None
        self.group_resolution_source: DirectoryGroupResolutionSource | None = None

    def execute(
        self,
        principal: Principal,
        *,
        group_object_ids: frozenset[str],
        group_resolution_source: DirectoryGroupResolutionSource,
    ) -> Principal:
        """Return the principal after recording minimized authorization inputs."""
        self.group_object_ids = group_object_ids
        self.group_resolution_source = group_resolution_source
        return principal


class CacheMiss:
    """Return no reusable authorization snapshot."""

    async def execute(self, principal: Principal, *, catalog_digest: str) -> None:
        assert catalog_digest == "a" * 64
        return None


class PassThroughCacheCommand:
    """Return the live authorization result unchanged."""

    async def execute(
        self,
        principal: Principal,
        *,
        resolved_at: object = None,
    ) -> Principal:
        assert resolved_at is not None
        return principal


class FixedCatalog:
    """Expose the digest required by the dependency orchestration."""

    catalog_digest = "a" * 64


TENANT_ID = "11111111-1111-4111-8111-111111111111"
GROUP_ID = "22222222-2222-4222-8222-222222222222"


def oidc_settings(**overrides: object) -> Settings:
    """Return explicit OIDC settings for the HTTP adapter tests."""
    values: dict[str, object] = {
        "oidc_enabled": True,
        "dev_auth_enabled": False,
        "oidc_issuer": "http://localhost:8081/realms/ai-governance",
        "oidc_jwks_url": (
            "http://localhost:8081/realms/ai-governance/protocol/openid-connect/certs"
        ),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (InvalidAccessToken("sensitive-token-validation-context"), 401),
        (IdentityProviderUnavailable("identity.private DNS failure"), 503),
    ],
)
async def test_oidc_errors_have_safe_http_mapping(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    monkeypatch.setattr(
        auth,
        "oidc_authenticator",
        lambda *args, **kwargs: FixedAuthenticator(error),
    )

    with pytest.raises(HTTPException) as caught:
        await auth._oidc_principal(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token"),
            oidc_settings(),
        )

    assert caught.value.status_code == expected_status
    assert str(error) not in str(caught.value.detail)
    if expected_status == 401:
        assert caught.value.headers == {"WWW-Authenticate": "Bearer"}


async def test_oidc_http_adapter_returns_domain_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = Principal(user_id="reviewer")
    monkeypatch.setattr(
        auth,
        "oidc_authenticator",
        lambda *args, **kwargs: FixedAuthenticator(principal),
    )

    result = await auth._oidc_principal(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token"),
        oidc_settings(),
    )

    assert result is principal


async def test_oidc_http_adapter_requires_bearer_credentials() -> None:
    with pytest.raises(HTTPException) as caught:
        await auth._oidc_principal(None, oidc_settings())

    assert caught.value.status_code == 401
    assert caught.value.headers == {"WWW-Authenticate": "Bearer"}


async def test_oidc_http_adapter_propagates_corporate_identity_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def factory(**kwargs: object) -> FixedAuthenticator:
        captured.update(kwargs)
        return FixedAuthenticator(Principal(user_id="corporate-reviewer"))

    monkeypatch.setattr(auth, "oidc_authenticator", factory)
    settings = oidc_settings(
        oidc_identity_mode="entra",
        oidc_allowed_tenant_ids=TENANT_ID,
        oidc_guest_approvals_enabled=True,
        oidc_issuer=f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        oidc_jwks_url=(
            f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
        ),
    )

    await auth._oidc_principal(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token"),
        settings,
    )

    assert captured["identity_mode"] is OidcIdentityMode.ENTRA
    assert captured["allowed_tenant_ids"] == (TENANT_ID,)
    assert captured["issuer_tenant_id"] == TENANT_ID
    assert captured["guest_approvals_enabled"] is True
    assert captured["entra_app_roles_claim"] == "roles"
    assert captured["entra_groups_claim"] == "groups"


async def test_disabled_directory_enrichment_does_not_require_bearer() -> None:
    result = await get_corporate_directory_profile(
        Principal(user_id="local-user"),
        None,
        None,
        CorporateDirectoryRequestSnapshot(),
    )

    assert result is None


async def test_complete_token_groups_are_used_without_graph_snapshot() -> None:
    resolver = CapturingAuthorizationResolver()
    principal = Principal(
        user_id="corporate-reviewer",
        directory_group_claims=DirectoryGroupClaims(
            state=DirectoryGroupClaimState.COMPLETE,
            object_ids=frozenset({GROUP_ID}),
        ),
    )

    result = await get_authorized_principal(
        principal,
        None,
        None,
        CorporateDirectoryRequestSnapshot(),
        resolver,
        CacheMiss(),
        PassThroughCacheCommand(),
        FixedCatalog(),
    )

    assert result is principal
    assert resolver.group_object_ids == frozenset({GROUP_ID})
    assert resolver.group_resolution_source is DirectoryGroupResolutionSource.TOKEN


async def test_graph_snapshot_supersedes_overage_token_groups() -> None:
    resolver = CapturingAuthorizationResolver()
    principal = Principal(
        user_id="corporate-reviewer",
        directory_group_claims=DirectoryGroupClaims(
            state=DirectoryGroupClaimState.OVERAGE,
        ),
    )
    profile = CorporateDirectoryProfile(
        tenant_id=TENANT_ID,
        object_id="33333333-3333-4333-8333-333333333333",
        group_object_ids=frozenset({GROUP_ID}),
    )

    result = await get_authorized_principal(
        principal,
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token"),
        FixedDirectoryResolver(profile),
        CorporateDirectoryRequestSnapshot(),
        resolver,
        CacheMiss(),
        PassThroughCacheCommand(),
        FixedCatalog(),
    )

    assert result is principal
    assert resolver.group_object_ids == frozenset({GROUP_ID})
    assert (
        resolver.group_resolution_source
        is DirectoryGroupResolutionSource.MICROSOFT_GRAPH
    )


@pytest.mark.parametrize(
    "error",
    [
        CorporateDirectoryUnavailable(retry_after_seconds=45),
        CorporateDirectoryResponseInvalid("sensitive Graph response"),
    ],
)
async def test_directory_errors_have_safe_http_mapping(error: Exception) -> None:
    with pytest.raises(HTTPException) as caught:
        await get_corporate_directory_profile(
            Principal(user_id="corporate-reviewer"),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token"),
            FixedDirectoryResolver(error),
            CorporateDirectoryRequestSnapshot(),
        )

    assert caught.value.status_code == 503
    if isinstance(error, CorporateDirectoryUnavailable):
        assert caught.value.detail == "Corporate directory unavailable"
        assert caught.value.headers == {"Retry-After": "45"}
    else:
        assert "sensitive Graph response" not in str(caught.value.detail)
