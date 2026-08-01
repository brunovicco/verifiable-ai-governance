"""Authentication adapter for OIDC and explicit local identities."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from ai_governance_api.adapters.oidc import PyJwtOidcVerifier
from ai_governance_api.application.authentication import (
    AuthenticateAccessToken,
    IdentityProviderUnavailable,
    InvalidAccessToken,
)
from ai_governance_api.config import AppEnvironment, Settings, get_settings
from ai_governance_api.domain.identity import Principal, parse_approval_areas

bearer = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


@lru_cache
def oidc_authenticator(
    issuer: str,
    audience: str,
    algorithms: tuple[str, ...],
    jwks_url: str,
    jwks_timeout_seconds: float,
    jwks_cache_seconds: float,
    clock_skew_seconds: float,
    groups_claim: str,
    admin_claim: str,
    max_token_length: int,
) -> AuthenticateAccessToken:
    """Compose and cache the OIDC authentication use case from immutable settings."""
    verifier = PyJwtOidcVerifier(
        issuer=issuer,
        audience=audience,
        algorithms=algorithms,
        jwks_url=jwks_url,
        jwks_timeout_seconds=jwks_timeout_seconds,
        jwks_cache_seconds=jwks_cache_seconds,
        clock_skew_seconds=clock_skew_seconds,
    )
    return AuthenticateAccessToken(
        verifier,
        areas_claim=groups_claim,
        admin_claim=admin_claim,
        max_token_length=max_token_length,
    )


async def _oidc_principal(
    credentials: HTTPAuthorizationCredentials | None, settings: Settings
) -> Principal:
    """Authenticate an HTTP bearer credential without blocking the event loop."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers=BEARER_CHALLENGE,
        )
    authenticator = oidc_authenticator(
        settings.oidc_issuer,
        settings.oidc_audience,
        tuple(settings.oidc_algorithm_list),
        settings.oidc_jwks_url,
        settings.oidc_jwks_timeout_seconds,
        settings.oidc_jwks_cache_seconds,
        settings.oidc_clock_skew_seconds,
        settings.oidc_groups_claim,
        settings.oidc_admin_claim,
        settings.oidc_max_token_length,
    )
    try:
        return await run_in_threadpool(authenticator.execute, credentials.credentials)
    except IdentityProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC provider unavailable",
        ) from exc
    except InvalidAccessToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OIDC token",
            headers=BEARER_CHALLENGE,
        ) from exc


async def get_principal(
    credentials: BearerCredentials,
    settings: SettingsDependency,
    x_user_id: Annotated[str | None, Header()] = None,
    x_user_email: Annotated[str | None, Header()] = None,
    x_user_areas: Annotated[str | None, Header()] = None,
) -> Principal:
    """Resolve the trusted principal for the current request."""
    if settings.oidc_enabled:
        return await _oidc_principal(credentials, settings)
    if (
        settings.app_env in {AppEnvironment.LOCAL, AppEnvironment.TEST}
        and settings.dev_auth_enabled
    ):
        if not x_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-User-Id is required in local development",
            )
        return Principal(
            user_id=x_user_id,
            email=x_user_email,
            approval_areas=parse_approval_areas(x_user_areas),
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No trusted authentication provider is configured",
    )
