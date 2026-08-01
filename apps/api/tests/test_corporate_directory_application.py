import pytest
from ai_governance_api.application.corporate_directory import (
    CorporateDirectoryIdentityMismatch,
    CorporateDirectoryNotApplicable,
    CorporateDirectoryProfile,
    ResolveCorporateDirectory,
)
from ai_governance_api.domain.identity import (
    DirectoryAccountType,
    DirectoryIdentity,
    Principal,
)

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "22222222-2222-4222-8222-222222222222"


class FixedDirectory:
    def __init__(self, profile: CorporateDirectoryProfile) -> None:
        self.profile = profile
        self.received_assertion: str | None = None

    async def resolve(
        self,
        user_assertion: str,
        expected_identity: DirectoryIdentity,
    ) -> CorporateDirectoryProfile:
        self.received_assertion = user_assertion
        assert expected_identity.tenant_id == TENANT_ID
        return self.profile


def corporate_principal() -> Principal:
    return Principal(
        user_id=f"{TENANT_ID}:{OBJECT_ID}",
        directory_identity=DirectoryIdentity(
            tenant_id=TENANT_ID,
            object_id=OBJECT_ID,
            account_type=DirectoryAccountType.MEMBER,
        ),
    )


async def test_directory_profile_is_bound_to_authenticated_identity() -> None:
    profile = CorporateDirectoryProfile(
        tenant_id=TENANT_ID,
        object_id=OBJECT_ID,
        department="Segurança da Informação",
    )
    directory = FixedDirectory(profile)

    result = await ResolveCorporateDirectory(directory).execute(
        corporate_principal(),
        "api-access-token",
    )

    assert result is profile
    assert directory.received_assertion == "api-access-token"


async def test_directory_enrichment_rejects_principal_without_directory_identity() -> None:
    directory = FixedDirectory(
        CorporateDirectoryProfile(tenant_id=TENANT_ID, object_id=OBJECT_ID)
    )

    with pytest.raises(CorporateDirectoryNotApplicable):
        await ResolveCorporateDirectory(directory).execute(
            Principal(user_id="provider-neutral-user"),
            "api-access-token",
        )

    assert directory.received_assertion is None


@pytest.mark.parametrize(
    ("tenant_id", "object_id"),
    [
        ("33333333-3333-4333-8333-333333333333", OBJECT_ID),
        (TENANT_ID, "44444444-4444-4444-8444-444444444444"),
    ],
)
async def test_directory_enrichment_rejects_identity_mismatch(
    tenant_id: str,
    object_id: str,
) -> None:
    directory = FixedDirectory(
        CorporateDirectoryProfile(tenant_id=tenant_id, object_id=object_id)
    )

    with pytest.raises(CorporateDirectoryIdentityMismatch):
        await ResolveCorporateDirectory(directory).execute(
            corporate_principal(),
            "api-access-token",
        )
