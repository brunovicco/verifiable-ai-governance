"""Provider-neutral access-token authentication use case."""

from collections.abc import Mapping
from typing import Protocol

from ai_governance_api.domain.identity import (
    CorporateIdentityPolicy,
    IdentityMappingError,
    Principal,
    principal_from_claims,
)


class AuthenticationError(Exception):
    """Base class for expected access-token authentication failures."""


class InvalidAccessToken(AuthenticationError):
    """Raised when a token or its identity claims are invalid."""


class IdentityProviderUnavailable(AuthenticationError):
    """Raised when signing keys cannot be obtained from the identity provider."""


class TokenVerifier(Protocol):
    """Port for cryptographic access-token validation."""

    def verify(self, token: str) -> Mapping[str, object]:
        """Return verified claims or raise a typed authentication error."""
        ...


class AuthenticateAccessToken:
    """Verify a bearer token and map its claims to a governance principal."""

    def __init__(
        self,
        verifier: TokenVerifier,
        *,
        areas_claim: str,
        admin_claim: str,
        max_token_length: int,
        corporate_policy: CorporateIdentityPolicy | None = None,
        corporate_roles_claim: str | None = None,
    ) -> None:
        """Initialize the use case with an external verifier and claim policy."""
        self._verifier = verifier
        self._areas_claim = areas_claim
        self._admin_claim = admin_claim
        self._max_token_length = max_token_length
        self._corporate_policy = corporate_policy
        self._corporate_roles_claim = corporate_roles_claim

    def execute(self, token: str) -> Principal:
        """Authenticate a non-empty token and return its least-privileged identity."""
        if not token.strip():
            raise InvalidAccessToken("Bearer token is empty")
        if len(token) > self._max_token_length:
            raise InvalidAccessToken("Bearer token exceeds the configured size limit")
        claims = self._verifier.verify(token)
        try:
            return principal_from_claims(
                claims,
                areas_claim=self._areas_claim,
                admin_claim=self._admin_claim,
                corporate_policy=self._corporate_policy,
                corporate_roles_claim=self._corporate_roles_claim,
            )
        except IdentityMappingError as exc:
            raise InvalidAccessToken(str(exc)) from exc
