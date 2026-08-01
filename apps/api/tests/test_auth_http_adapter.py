import pytest
from ai_governance_api import auth
from ai_governance_api.application.authentication import (
    IdentityProviderUnavailable,
    InvalidAccessToken,
)
from ai_governance_api.config import OidcIdentityMode, Settings
from ai_governance_api.domain.identity import Principal
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


TENANT_ID = "11111111-1111-4111-8111-111111111111"


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
