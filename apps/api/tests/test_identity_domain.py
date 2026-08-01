import pytest
from ai_governance_api.domain.identity import (
    IdentityMappingError,
    parse_approval_areas,
    principal_from_claims,
)
from governance_schemas import ApprovalArea


def test_nested_provider_roles_map_only_governance_areas() -> None:
    principal = principal_from_claims(
        {
            "sub": "security-reviewer",
            "email": "reviewer@example.com",
            "realm_access": {
                "roles": ["security", "business", "offline_access", "uma_authorization"]
            },
            "governance_admin": False,
        },
        areas_claim="realm_access.roles",
        admin_claim="governance_admin",
    )

    assert principal.approval_areas == frozenset(
        {ApprovalArea.SECURITY, ApprovalArea.BUSINESS}
    )
    assert not principal.is_admin


@pytest.mark.parametrize("untrusted_value", ["true", "false", 1, [True]])
def test_admin_claim_requires_a_json_boolean_true(untrusted_value: object) -> None:
    principal = principal_from_claims(
        {"sub": "reviewer", "governance_admin": untrusted_value},
        areas_claim="governance_areas",
        admin_claim="governance_admin",
    )

    assert not principal.is_admin


def test_boolean_true_grants_explicit_admin_capability() -> None:
    principal = principal_from_claims(
        {"sub": "administrator", "governance_admin": True},
        areas_claim="governance_areas",
        admin_claim="governance_admin",
    )

    assert principal.is_admin


def test_comma_separated_areas_are_normalized() -> None:
    assert parse_approval_areas(" security,privacy,unrelated ") == frozenset(
        {ApprovalArea.SECURITY, ApprovalArea.PRIVACY}
    )


def test_missing_subject_is_rejected() -> None:
    with pytest.raises(IdentityMappingError, match="subject missing"):
        principal_from_claims(
            {"sub": "  "},
            areas_claim="governance_areas",
            admin_claim="governance_admin",
        )
