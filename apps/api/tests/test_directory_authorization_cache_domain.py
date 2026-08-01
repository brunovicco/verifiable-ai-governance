from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationCacheError,
    DirectoryAuthorizationCacheKey,
    DirectoryAuthorizationSnapshot,
)
from ai_governance_api.domain.identity import (
    DirectoryAccountType,
    DirectoryGroupResolutionSource,
    DirectoryIdentity,
    Principal,
)
from governance_schemas import ApprovalArea

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def corporate_principal(*, object_id: str = OBJECT_ID) -> Principal:
    """Return a stable member principal for cache-binding tests."""
    return Principal(
        user_id=f"{TENANT_ID}:{object_id}",
        directory_identity=DirectoryIdentity(
            tenant_id=TENANT_ID,
            object_id=object_id,
            account_type=DirectoryAccountType.MEMBER,
        ),
    )


def snapshot(**overrides: object) -> DirectoryAuthorizationSnapshot:
    """Return a valid minimal snapshot with deterministic freshness."""
    values: dict[str, object] = {
        "key": DirectoryAuthorizationCacheKey(TENANT_ID, OBJECT_ID),
        "approval_areas": frozenset({ApprovalArea.SECURITY}),
        "catalog_id": "enterprise-entra-authorization",
        "catalog_version": "2026.08.1",
        "catalog_digest": "a" * 64,
        "resolved_at": NOW,
        "expires_at": NOW + timedelta(seconds=60),
        "matched_mapping_ids": ("security-reviewers",),
        "source_types": ("group",),
        "original_group_resolution_source": (
            DirectoryGroupResolutionSource.MICROSOFT_GRAPH
        ),
    }
    values.update(overrides)
    return DirectoryAuthorizationSnapshot(**values)


def test_fresh_snapshot_is_bound_to_identity_and_catalog() -> None:
    cached = snapshot()

    assert cached.is_fresh(now=NOW + timedelta(seconds=59), catalog_digest="a" * 64)
    authorized = cached.authorize(corporate_principal())

    assert authorized.approval_areas == frozenset({ApprovalArea.SECURITY})
    assert authorized.authorization_provenance is not None
    assert (
        authorized.authorization_provenance.group_resolution_source
        is DirectoryGroupResolutionSource.CACHE
    )


def test_expiry_catalog_change_and_invalidation_make_snapshot_stale() -> None:
    cached = snapshot()
    invalidated = snapshot(invalidated_at=NOW + timedelta(seconds=1))

    assert not cached.is_fresh(now=NOW + timedelta(seconds=60), catalog_digest="a" * 64)
    assert not cached.is_fresh(now=NOW, catalog_digest="b" * 64)
    assert not invalidated.is_fresh(
        now=NOW + timedelta(seconds=2),
        catalog_digest="a" * 64,
    )


def test_snapshot_cannot_authorize_another_directory_identity() -> None:
    with pytest.raises(DirectoryAuthorizationCacheError, match="does not match"):
        snapshot().authorize(
            corporate_principal(object_id="33333333-3333-4333-8333-333333333333")
        )


def test_cache_key_produces_stable_minimized_identifiers() -> None:
    key = DirectoryAuthorizationCacheKey(TENANT_ID.upper(), OBJECT_ID.upper())

    assert key.tenant_id == TENANT_ID
    assert key.object_id == OBJECT_ID
    assert len(key.entry_id) == 36
    assert len(key.target_digest) == 64
    assert TENANT_ID not in key.target_digest
