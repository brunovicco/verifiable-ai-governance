"""PyJWT adapter for asymmetric OIDC access-token verification."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from ai_governance_api.application.authentication import (
    IdentityProviderUnavailable,
    InvalidAccessToken,
)


class SigningKey(Protocol):
    """Minimal signing-key value returned by a JWKS client."""

    key: Any


class SigningKeyProvider(Protocol):
    """Port implemented by a cached remote JWKS client."""

    def get_signing_key_from_jwt(self, token: str) -> SigningKey:
        """Return the key selected from the token identifier."""
        ...


class PyJwtOidcVerifier:
    """Verify signed OIDC access tokens against explicit trust configuration."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        algorithms: Sequence[str],
        jwks_url: str,
        jwks_timeout_seconds: float,
        jwks_cache_seconds: float,
        clock_skew_seconds: float,
        signing_keys: SigningKeyProvider | None = None,
    ) -> None:
        """Initialize strict claim validation and bounded JWKS retrieval."""
        self._issuer = issuer
        self._audience = audience
        self._algorithms = tuple(algorithms)
        self._clock_skew_seconds = clock_skew_seconds
        self._signing_keys = signing_keys or PyJWKClient(
            jwks_url,
            cache_keys=False,
            cache_jwk_set=True,
            lifespan=jwks_cache_seconds,
            timeout=jwks_timeout_seconds,
        )

    def verify(self, token: str) -> Mapping[str, object]:
        """Return claims only after signature and registered claims are valid."""
        try:
            signing_key = self._signing_keys.get_signing_key_from_jwt(token)
        except PyJWKClientConnectionError as exc:
            raise IdentityProviderUnavailable("OIDC signing keys are unavailable") from exc
        except jwt.PyJWTError as exc:
            raise InvalidAccessToken("OIDC signing key could not be selected") from exc
        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._clock_skew_seconds,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidAccessToken("OIDC token validation failed") from exc
        return {str(key): value for key, value in claims.items()}
