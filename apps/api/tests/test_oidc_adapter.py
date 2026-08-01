from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from ai_governance_api.adapters.oidc import PyJwtOidcVerifier
from ai_governance_api.application.authentication import (
    IdentityProviderUnavailable,
    InvalidAccessToken,
)
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import PyJWKClientConnectionError

ISSUER = "https://identity.example.com/realms/governance"
AUDIENCE = "ai-governance-api"


@dataclass(frozen=True, slots=True)
class FixedSigningKey:
    key: Any


class FixedSigningKeyProvider:
    def __init__(self, key: Any) -> None:
        self._key = key

    def get_signing_key_from_jwt(self, token: str) -> FixedSigningKey:
        assert token
        return FixedSigningKey(self._key)


class UnavailableSigningKeyProvider:
    def get_signing_key_from_jwt(self, token: str) -> FixedSigningKey:
        raise PyJWKClientConnectionError("provider unavailable")


@pytest.fixture
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def verifier(
    private_key: rsa.RSAPrivateKey,
    *,
    signing_keys: FixedSigningKeyProvider | UnavailableSigningKeyProvider | None = None,
) -> PyJwtOidcVerifier:
    return PyJwtOidcVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        algorithms=("RS256",),
        jwks_url=f"{ISSUER}/protocol/openid-connect/certs",
        jwks_timeout_seconds=1,
        jwks_cache_seconds=60,
        clock_skew_seconds=0,
        signing_keys=signing_keys or FixedSigningKeyProvider(private_key.public_key()),
    )


def token(private_key: rsa.RSAPrivateKey, **overrides: object) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": "security-reviewer",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "governance_areas": ["security"],
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def test_valid_token_returns_verified_claims(private_key: rsa.RSAPrivateKey) -> None:
    claims = verifier(private_key).verify(token(private_key))

    assert claims["sub"] == "security-reviewer"
    assert claims["governance_areas"] == ["security"]


def test_wrong_audience_is_rejected(private_key: rsa.RSAPrivateKey) -> None:
    with pytest.raises(InvalidAccessToken, match="validation failed"):
        verifier(private_key).verify(token(private_key, aud="another-api"))


def test_expired_token_is_rejected(private_key: rsa.RSAPrivateKey) -> None:
    with pytest.raises(InvalidAccessToken, match="validation failed"):
        verifier(private_key).verify(
            token(private_key, exp=datetime.now(UTC) - timedelta(minutes=1))
        )


def test_unavailable_jwks_is_a_dependency_failure(private_key: rsa.RSAPrivateKey) -> None:
    with pytest.raises(IdentityProviderUnavailable, match="unavailable"):
        verifier(private_key, signing_keys=UnavailableSigningKeyProvider()).verify(
            token(private_key)
        )
