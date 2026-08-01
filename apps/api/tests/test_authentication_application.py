from collections.abc import Mapping

import pytest
from ai_governance_api.application.authentication import (
    AuthenticateAccessToken,
    InvalidAccessToken,
)
from ai_governance_api.domain.identity import CorporateIdentityPolicy
from governance_schemas import ApprovalArea


class FixedVerifier:
    def __init__(self, claims: Mapping[str, object]) -> None:
        self.claims = claims
        self.received_token: str | None = None

    def verify(self, token: str) -> Mapping[str, object]:
        self.received_token = token
        return self.claims


def authenticator(
    verifier: FixedVerifier,
    *,
    limit: int = 1024,
    corporate_policy: CorporateIdentityPolicy | None = None,
) -> AuthenticateAccessToken:
    """Compose the use case with deterministic test policies."""
    return AuthenticateAccessToken(
        verifier,
        areas_claim="governance_areas",
        admin_claim="governance_admin",
        max_token_length=limit,
        corporate_policy=corporate_policy,
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


def test_corporate_claim_mapping_failure_is_an_invalid_token() -> None:
    policy = CorporateIdentityPolicy(
        allowed_tenant_ids=frozenset({"11111111-1111-4111-8111-111111111111"}),
        issuer_tenant_id="11111111-1111-4111-8111-111111111111",
    )

    with pytest.raises(InvalidAccessToken, match="tenant is not allowed"):
        authenticator(
            FixedVerifier(
                {
                    "tid": "22222222-2222-4222-8222-222222222222",
                    "oid": "33333333-3333-4333-8333-333333333333",
                    "acct": 0,
                }
            ),
            corporate_policy=policy,
        ).execute("signed-token")
