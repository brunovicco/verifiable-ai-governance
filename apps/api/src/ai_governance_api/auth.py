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
from ai_governance_api.config import AppEnvironment, OidcIdentityMode, Settings, get_settings
from ai_governance_api.domain.identity import (
    CorporateIdentityPolicy,
    Principal,
    parse_approval_areas,
)

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
    identity_mode: OidcIdentityMode,
    allowed_tenant_ids: tuple[str, ...],
    issuer_tenant_id: str | None,
    guest_approvals_enabled: bool,
    entra_app_roles_claim: str,
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
        corporate_policy=(
            CorporateIdentityPolicy(
                allowed_tenant_ids=frozenset(allowed_tenant_ids),
                issuer_tenant_id=issuer_tenant_id or "",
                guest_approvals_enabled=guest_approvals_enabled,
            )
            if identity_mode is OidcIdentityMode.ENTRA
            else None
        ),
        corporate_roles_claim=(
            entra_app_roles_claim
            if identity_mode is OidcIdentityMode.ENTRA
            else None
        ),
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
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
        algorithms=tuple(settings.oidc_algorithm_list),
        jwks_url=settings.oidc_jwks_url,
        jwks_timeout_seconds=settings.oidc_jwks_timeout_seconds,
        jwks_cache_seconds=settings.oidc_jwks_cache_seconds,
        clock_skew_seconds=settings.oidc_clock_skew_seconds,
        groups_claim=settings.oidc_groups_claim,
        admin_claim=settings.oidc_admin_claim,
        max_token_length=settings.oidc_max_token_length,
        identity_mode=settings.oidc_identity_mode,
        allowed_tenant_ids=(
            tuple(sorted(settings.oidc_allowed_tenant_id_set))
            if settings.oidc_identity_mode is OidcIdentityMode.ENTRA
            else ()
        ),
        issuer_tenant_id=(
            settings.oidc_entra_issuer_tenant_id
            if settings.oidc_identity_mode is OidcIdentityMode.ENTRA
            else None
        ),
        guest_approvals_enabled=settings.oidc_guest_approvals_enabled,
        entra_app_roles_claim=settings.oidc_entra_app_roles_claim,
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
