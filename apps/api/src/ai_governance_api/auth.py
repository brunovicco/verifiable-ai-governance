from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from governance_schemas import ApprovalArea
from jwt import PyJWKClient
from pydantic import BaseModel

from ai_governance_api.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


class Principal(BaseModel):
    user_id: str
    email: str | None = None
    approval_areas: frozenset[ApprovalArea] = frozenset()
    is_admin: bool = False


@lru_cache
def jwks_client(issuer: str) -> PyJWKClient:
    return PyJWKClient(f"{issuer.rstrip('/')}/.well-known/jwks.json")


def _parse_areas(raw_areas: object) -> frozenset[ApprovalArea]:
    if isinstance(raw_areas, str):
        values = raw_areas.split(",")
    elif isinstance(raw_areas, list):
        values = [str(item) for item in raw_areas]
    else:
        values = []
    parsed: set[ApprovalArea] = set()
    for value in values:
        try:
            parsed.add(ApprovalArea(value.strip().lower()))
        except ValueError:
            continue
    return frozenset(parsed)


def _oidc_principal(
    credentials: HTTPAuthorizationCredentials | None, settings: Settings
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required"
        )
    try:
        signing_key = jwks_client(settings.oidc_issuer).get_signing_key_from_jwt(
            credentials.credentials
        )
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=[item.strip() for item in settings.oidc_algorithms.split(",")],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OIDC token"
        ) from exc
    subject = claims.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC subject missing")
    return Principal(
        user_id=str(subject),
        email=claims.get("email"),
        approval_areas=_parse_areas(claims.get(settings.oidc_groups_claim)),
        is_admin=bool(claims.get("governance_admin", False)),
    )


async def get_principal(
    credentials: BearerCredentials,
    settings: SettingsDependency,
    x_user_id: Annotated[str | None, Header()] = None,
    x_user_email: Annotated[str | None, Header()] = None,
    x_user_areas: Annotated[str | None, Header()] = None,
) -> Principal:
    if settings.oidc_enabled:
        return _oidc_principal(credentials, settings)
    if settings.app_env == "local" and settings.dev_auth_enabled:
        if not x_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-User-Id is required in local development",
            )
        return Principal(
            user_id=x_user_id,
            email=x_user_email,
            approval_areas=_parse_areas(x_user_areas),
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No trusted authentication provider is configured",
    )
