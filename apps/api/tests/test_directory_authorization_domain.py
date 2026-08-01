import pytest
from ai_governance_api.domain.directory_authorization import (
    DirectoryAuthorizationCatalog,
    DirectoryAuthorizationError,
    DirectoryAuthorizationMapping,
    DirectoryAuthorizationSource,
)
from ai_governance_api.domain.identity import (
    DirectoryAccountType,
    DirectoryIdentity,
    Principal,
)
from governance_schemas import ApprovalArea

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "22222222-2222-4222-8222-222222222222"
GROUP_ID = "33333333-3333-4333-8333-333333333333"


def mapping(
    mapping_id: str,
    *,
    source_type: DirectoryAuthorizationSource,
    source_value: str,
    approval_area: ApprovalArea,
    enabled: bool = True,
    tenant_id: str = TENANT_ID,
) -> DirectoryAuthorizationMapping:
    return DirectoryAuthorizationMapping(
        mapping_id=mapping_id,
        tenant_id=tenant_id,
        source_type=source_type,
        source_value=source_value,
        approval_area=approval_area,
        enabled=enabled,
        owner="identity-and-access-management",
        mapping_version=1,
    )


def catalog(*mappings: DirectoryAuthorizationMapping) -> DirectoryAuthorizationCatalog:
    return DirectoryAuthorizationCatalog(
        catalog_id="enterprise-entra-authorization",
        catalog_version="2026.08.1",
        mappings=mappings,
    )


def principal(
    account_type: DirectoryAccountType = DirectoryAccountType.MEMBER,
) -> Principal:
    return Principal(
        user_id=f"{TENANT_ID}:{OBJECT_ID}",
        directory_identity=DirectoryIdentity(
            tenant_id=TENANT_ID,
            object_id=OBJECT_ID,
            account_type=account_type,
        ),
        directory_role_values=frozenset({"Governance.Security.Reviewer"}),
    )


def test_catalog_combines_exact_app_role_and_transitive_group_mappings() -> None:
    policy = catalog(
        mapping(
            "entra-role-security",
            source_type=DirectoryAuthorizationSource.APP_ROLE,
            source_value="Governance.Security.Reviewer",
            approval_area=ApprovalArea.SECURITY,
        ),
        mapping(
            "entra-group-privacy",
            source_type=DirectoryAuthorizationSource.GROUP,
            source_value=GROUP_ID.upper(),
            approval_area=ApprovalArea.PRIVACY,
        ),
        mapping(
            "disabled-business",
            source_type=DirectoryAuthorizationSource.APP_ROLE,
            source_value="Governance.Security.Reviewer",
            approval_area=ApprovalArea.BUSINESS,
            enabled=False,
        ),
    )

    authorized = policy.authorize(
        principal(),
        group_object_ids=frozenset({GROUP_ID}),
        guest_approvals_enabled=False,
    )

    assert authorized.approval_areas == frozenset(
        {ApprovalArea.SECURITY, ApprovalArea.PRIVACY}
    )
    assert authorized.authorization_provenance is not None
    assert authorized.authorization_provenance.catalog_version == "2026.08.1"
    assert len(authorized.authorization_provenance.catalog_digest) == 64
    assert authorized.authorization_provenance.matched_mapping_ids == (
        "entra-group-privacy",
        "entra-role-security",
    )
    assert authorized.authorization_provenance.source_types == ("app_role", "group")


def test_app_role_matching_is_case_sensitive_and_tenant_scoped() -> None:
    policy = catalog(
        mapping(
            "wrong-case",
            source_type=DirectoryAuthorizationSource.APP_ROLE,
            source_value="governance.security.reviewer",
            approval_area=ApprovalArea.SECURITY,
        ),
        mapping(
            "wrong-tenant",
            tenant_id="44444444-4444-4444-8444-444444444444",
            source_type=DirectoryAuthorizationSource.APP_ROLE,
            source_value="Governance.Security.Reviewer",
            approval_area=ApprovalArea.SECURITY,
        ),
    )

    authorized = policy.authorize(
        principal(),
        group_object_ids=frozenset(),
        guest_approvals_enabled=False,
    )

    assert authorized.approval_areas == frozenset()
    assert authorized.authorization_provenance is not None
    assert authorized.authorization_provenance.matched_mapping_ids == ()


@pytest.mark.parametrize(
    ("account_type", "guest_enabled", "expected"),
    [
        (DirectoryAccountType.GUEST, False, frozenset()),
        (DirectoryAccountType.GUEST, True, frozenset({ApprovalArea.SECURITY})),
        (DirectoryAccountType.UNKNOWN, True, frozenset()),
    ],
)
def test_account_type_policy_is_fail_closed(
    account_type: DirectoryAccountType,
    guest_enabled: bool,
    expected: frozenset[ApprovalArea],
) -> None:
    policy = catalog(
        mapping(
            "security-reviewer",
            source_type=DirectoryAuthorizationSource.APP_ROLE,
            source_value="Governance.Security.Reviewer",
            approval_area=ApprovalArea.SECURITY,
        )
    )

    authorized = policy.authorize(
        principal(account_type),
        group_object_ids=frozenset(),
        guest_approvals_enabled=guest_enabled,
    )

    assert authorized.approval_areas == expected


def test_provider_neutral_principal_keeps_existing_capabilities() -> None:
    original = Principal(
        user_id="local-reviewer",
        approval_areas=frozenset({ApprovalArea.BUSINESS}),
    )

    authorized = catalog().authorize(
        original,
        group_object_ids=frozenset(),
        guest_approvals_enabled=False,
    )

    assert authorized is original


def test_catalog_rejects_duplicate_mapping_identity() -> None:
    first = mapping(
        "security-v1",
        source_type=DirectoryAuthorizationSource.APP_ROLE,
        source_value="Governance.Security.Reviewer",
        approval_area=ApprovalArea.SECURITY,
    )
    duplicate = mapping(
        "security-v2",
        source_type=DirectoryAuthorizationSource.APP_ROLE,
        source_value="Governance.Security.Reviewer",
        approval_area=ApprovalArea.SECURITY,
    )

    with pytest.raises(DirectoryAuthorizationError, match="must be unique"):
        catalog(first, duplicate)


def test_group_mapping_requires_canonicalizable_object_id() -> None:
    with pytest.raises(DirectoryAuthorizationError, match="group object ID must be a UUID"):
        mapping(
            "invalid-group",
            source_type=DirectoryAuthorizationSource.GROUP,
            source_value="Security Reviewers",
            approval_area=ApprovalArea.SECURITY,
        )


def test_mapping_id_must_be_opaque_and_audit_safe() -> None:
    with pytest.raises(DirectoryAuthorizationError, match="lowercase letters"):
        mapping(
            "security-reviewer@example.com",
            source_type=DirectoryAuthorizationSource.APP_ROLE,
            source_value="Governance.Security.Reviewer",
            approval_area=ApprovalArea.SECURITY,
        )


def test_catalog_digest_changes_with_semantic_policy_content() -> None:
    first = catalog(
        mapping(
            "security-reviewer",
            source_type=DirectoryAuthorizationSource.APP_ROLE,
            source_value="Governance.Security.Reviewer",
            approval_area=ApprovalArea.SECURITY,
        )
    )
    second = catalog(
        mapping(
            "security-reviewer",
            source_type=DirectoryAuthorizationSource.APP_ROLE,
            source_value="Governance.Security.Reviewer.V2",
            approval_area=ApprovalArea.SECURITY,
        )
    )

    assert first.catalog_digest != second.catalog_digest
