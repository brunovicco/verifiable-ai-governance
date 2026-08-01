from collections.abc import Mapping

import pytest
from ai_governance_api.application.authentication import (
    AuthenticateAccessToken,
    InvalidAccessToken,
)
from governance_schemas import ApprovalArea


class FixedVerifier:
    def __init__(self, claims: Mapping[str, object]) -> None:
        self.claims = claims
        self.received_token: str | None = None

    def verify(self, token: str) -> Mapping[str, object]:
        self.received_token = token
        return self.claims


def authenticator(verifier: FixedVerifier, *, limit: int = 1024) -> AuthenticateAccessToken:
    return AuthenticateAccessToken(
        verifier,
        areas_claim="governance_areas",
        admin_claim="governance_admin",
        max_token_length=limit,
    )


def test_authentication_maps_verified_claims() -> None:
    verifier = FixedVerifier({"sub": "reviewer", "governance_areas": ["security"]})

    principal = authenticator(verifier).execute("signed-token")

    assert verifier.received_token == "signed-token"
    assert principal.user_id == "reviewer"
    assert principal.approval_areas == frozenset({ApprovalArea.SECURITY})


def test_empty_token_is_rejected_before_verification() -> None:
    verifier = FixedVerifier({"sub": "unused"})

    with pytest.raises(InvalidAccessToken, match="empty"):
        authenticator(verifier).execute("  ")

    assert verifier.received_token is None


def test_oversized_token_is_rejected_before_verification() -> None:
    verifier = FixedVerifier({"sub": "unused"})

    with pytest.raises(InvalidAccessToken, match="size limit"):
        authenticator(verifier, limit=5).execute("too-long")

    assert verifier.received_token is None


def test_missing_verified_subject_is_an_invalid_token() -> None:
    with pytest.raises(InvalidAccessToken, match="subject missing"):
        authenticator(FixedVerifier({})).execute("signed-token")
