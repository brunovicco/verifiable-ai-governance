import pytest
from ai_governance_api.domain.identity import (
    CorporateIdentityPolicy,
    DirectoryAccountType,
    DirectoryGroupClaims,
    DirectoryGroupClaimState,
    IdentityMappingError,
    parse_approval_areas,
    principal_from_claims,
)
from governance_schemas import ApprovalArea

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "22222222-2222-4222-8222-222222222222"
GROUP_ID = "33333333-3333-4333-8333-333333333333"


def corporate_policy(*, guest_approvals_enabled: bool = False) -> CorporateIdentityPolicy:
    """Return the explicit tenant policy used by corporate identity tests."""
    return CorporateIdentityPolicy(
        allowed_tenant_ids=frozenset({TENANT_ID}),
        issuer_tenant_id=TENANT_ID,
        guest_approvals_enabled=guest_approvals_enabled,
    )


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


def test_member_uses_stable_tenant_and_object_identity() -> None:
    principal = principal_from_claims(
        {
            "sub": "pairwise-subject",
            "tid": TENANT_ID.upper(),
            "oid": OBJECT_ID.upper(),
            "acct": 0,
            "governance_areas": ["security"],
            "roles": ["Governance.Security.Reviewer"],
            "governance_admin": True,
        },
        areas_claim="governance_areas",
        admin_claim="governance_admin",
        corporate_policy=corporate_policy(),
        corporate_roles_claim="roles",
    )

    assert principal.user_id == f"{TENANT_ID}:{OBJECT_ID}"
    assert principal.directory_identity is not None
    assert principal.directory_identity.tenant_id == TENANT_ID
    assert principal.directory_identity.object_id == OBJECT_ID
    assert principal.directory_identity.account_type is DirectoryAccountType.MEMBER
    assert principal.approval_areas == frozenset()
    assert principal.directory_role_values == frozenset(
        {"Governance.Security.Reviewer"}
    )
    assert principal.is_admin


def test_guest_has_no_governance_capabilities_by_default() -> None:
    principal = principal_from_claims(
        {
            "tid": TENANT_ID,
            "oid": OBJECT_ID,
            "acct": "1",
            "roles": ["Governance.Security.Reviewer"],
            "governance_admin": True,
        },
        areas_claim="governance_areas",
        admin_claim="governance_admin",
        corporate_policy=corporate_policy(),
        corporate_roles_claim="roles",
    )

    assert principal.directory_identity is not None
    assert principal.directory_identity.account_type is DirectoryAccountType.GUEST
    assert principal.approval_areas == frozenset()
    assert not principal.is_admin


def test_explicit_policy_can_enable_guest_approval_capabilities() -> None:
    principal = principal_from_claims(
        {
            "tid": TENANT_ID,
            "oid": OBJECT_ID,
            "acct": 1,
            "roles": ["Governance.Privacy.Reviewer"],
            "governance_admin": True,
        },
        areas_claim="governance_areas",
        admin_claim="governance_admin",
        corporate_policy=corporate_policy(guest_approvals_enabled=True),
        corporate_roles_claim="roles",
    )

    assert principal.approval_areas == frozenset()
    assert principal.directory_role_values == frozenset(
        {"Governance.Privacy.Reviewer"}
    )
    assert not principal.is_admin


@pytest.mark.parametrize("account_claim", [None, True, False, 2, "member", []])
def test_unknown_account_type_cannot_receive_capabilities(account_claim: object) -> None:
    principal = principal_from_claims(
        {
            "tid": TENANT_ID,
            "oid": OBJECT_ID,
            "acct": account_claim,
            "roles": ["Governance.Security.Reviewer"],
            "governance_admin": True,
        },
        areas_claim="governance_areas",
        admin_claim="governance_admin",
        corporate_policy=corporate_policy(guest_approvals_enabled=True),
        corporate_roles_claim="roles",
    )

    assert principal.directory_identity is not None
    assert principal.directory_identity.account_type is DirectoryAccountType.UNKNOWN
    assert principal.approval_areas == frozenset()
    assert not principal.is_admin


def test_invalid_corporate_app_roles_claim_is_rejected() -> None:
    with pytest.raises(IdentityMappingError, match="App Roles claim is invalid"):
        principal_from_claims(
            {
                "tid": TENANT_ID,
                "oid": OBJECT_ID,
                "acct": 0,
                "roles": ["Governance.Security.Reviewer", 42],
            },
            areas_claim="governance_areas",
            admin_claim="governance_admin",
            corporate_policy=corporate_policy(),
            corporate_roles_claim="roles",
        )


def test_complete_entra_groups_claim_uses_only_canonical_object_ids() -> None:
    principal = principal_from_claims(
        {
            "tid": TENANT_ID,
            "oid": OBJECT_ID,
            "acct": 0,
            "groups": [GROUP_ID.upper(), GROUP_ID],
        },
        areas_claim="governance_areas",
        admin_claim="governance_admin",
        corporate_policy=corporate_policy(),
        corporate_groups_claim="groups",
    )

    assert principal.directory_group_claims.state is DirectoryGroupClaimState.COMPLETE
    assert principal.directory_group_claims.object_ids == frozenset({GROUP_ID})


@pytest.mark.parametrize(
    "overage_claims",
    [
        {"hasgroups": True},
        {
            "_claim_names": {"groups": "src1"},
            "_claim_sources": {
                "src1": {"endpoint": "https://attacker.example.com/groups"}
            },
        },
    ],
)
def test_entra_group_overage_ignores_claim_source_urls(
    overage_claims: dict[str, object],
) -> None:
    principal = principal_from_claims(
        {
            "tid": TENANT_ID,
            "oid": OBJECT_ID,
            "acct": 0,
            "groups": [GROUP_ID],
            **overage_claims,
        },
        areas_claim="governance_areas",
        admin_claim="governance_admin",
        corporate_policy=corporate_policy(),
        corporate_groups_claim="groups",
    )

    assert principal.directory_group_claims.state is DirectoryGroupClaimState.OVERAGE
    assert principal.directory_group_claims.object_ids == frozenset()


@pytest.mark.parametrize(
    "claims",
    [
        {"groups": "not-an-array"},
        {"groups": ["not-a-uuid"]},
        {"hasgroups": "true"},
        {"_claim_names": {"groups": 42}},
    ],
)
def test_invalid_entra_group_contract_is_rejected(claims: dict[str, object]) -> None:
    with pytest.raises(IdentityMappingError, match="OIDC"):
        principal_from_claims(
            {"tid": TENANT_ID, "oid": OBJECT_ID, "acct": 0, **claims},
            areas_claim="governance_areas",
            admin_claim="governance_admin",
            corporate_policy=corporate_policy(),
            corporate_groups_claim="groups",
        )


def test_entra_groups_claim_cannot_exceed_jwt_limit() -> None:
    with pytest.raises(IdentityMappingError, match="JWT item limit"):
        principal_from_claims(
            {
                "tid": TENANT_ID,
                "oid": OBJECT_ID,
                "acct": 0,
                "groups": [GROUP_ID] * 201,
            },
            areas_claim="governance_areas",
            admin_claim="governance_admin",
            corporate_policy=corporate_policy(),
            corporate_groups_claim="groups",
        )


def test_incomplete_group_claim_state_cannot_carry_object_ids() -> None:
    with pytest.raises(IdentityMappingError, match="cannot contain object IDs"):
        DirectoryGroupClaims(
            state=DirectoryGroupClaimState.OVERAGE,
            object_ids=frozenset({GROUP_ID}),
        )


def test_non_allowlisted_tenant_is_rejected() -> None:
    with pytest.raises(IdentityMappingError, match="tenant is not allowed"):
        principal_from_claims(
            {
                "tid": "33333333-3333-4333-8333-333333333333",
                "oid": OBJECT_ID,
                "acct": 0,
            },
            areas_claim="governance_areas",
            admin_claim="governance_admin",
            corporate_policy=corporate_policy(),
        )


def test_allowlisted_tenant_that_differs_from_issuer_is_rejected() -> None:
    other_tenant = "33333333-3333-4333-8333-333333333333"
    policy = CorporateIdentityPolicy(
        allowed_tenant_ids=frozenset({TENANT_ID, other_tenant}),
        issuer_tenant_id=TENANT_ID,
    )

    with pytest.raises(IdentityMappingError, match="does not match the verified issuer"):
        principal_from_claims(
            {"tid": other_tenant, "oid": OBJECT_ID, "acct": 0},
            areas_claim="governance_areas",
            admin_claim="governance_admin",
            corporate_policy=policy,
        )


@pytest.mark.parametrize(
    ("claim", "value"),
    [("tid", "not-a-uuid"), ("oid", ""), ("oid", None)],
)
def test_invalid_corporate_identity_claim_is_rejected(claim: str, value: object) -> None:
    claims: dict[str, object] = {"tid": TENANT_ID, "oid": OBJECT_ID, "acct": 0}
    claims[claim] = value

    with pytest.raises(IdentityMappingError, match=rf"{claim} claim missing or invalid"):
        principal_from_claims(
            claims,
            areas_claim="governance_areas",
            admin_claim="governance_admin",
            corporate_policy=corporate_policy(),
        )
