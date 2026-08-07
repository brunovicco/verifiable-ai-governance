from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.application.directory_authorization_cache import (
    CacheResolvedDirectoryAuthorization,
    DirectoryAuthorizationCacheUnavailable,
    InvalidateDirectoryAuthorization,
    ReuseDirectoryAuthorization,
)
from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationCacheKey,
    DirectoryAuthorizationInvalidation,
    DirectoryAuthorizationInvalidationReason,
    DirectoryAuthorizationSnapshot,
)
from ai_governance_api.domain.identity import (
    AuthorizationProvenance,
    DirectoryAccountType,
    DirectoryGroupResolutionSource,
    DirectoryIdentity,
    Principal,
)
from ai_governance_api.errors import ApplicationError, ErrorKind
from governance_schemas import ApprovalArea

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


class MemoryCache:
    """Deterministic cache port for application-use-case tests."""

    def __init__(self, snapshot: DirectoryAuthorizationSnapshot | None = None) -> None:
        self.snapshot = snapshot
        self.saved: DirectoryAuthorizationSnapshot | None = None
        self.save_allowed = True
        self.invalidated: DirectoryAuthorizationInvalidation | None = None

    async def load(
        self,
        key: DirectoryAuthorizationCacheKey,
    ) -> DirectoryAuthorizationSnapshot | None:
        assert key == DirectoryAuthorizationCacheKey(TENANT_ID, OBJECT_ID)
        return self.snapshot

    async def save(self, snapshot: DirectoryAuthorizationSnapshot) -> bool:
        self.saved = snapshot
        return self.save_allowed

    async def invalidate(
        self,
        key: DirectoryAuthorizationCacheKey,
        invalidated_at: datetime,
    ) -> DirectoryAuthorizationInvalidation:
        self.invalidated = DirectoryAuthorizationInvalidation(
            key=key,
            invalidated_at=invalidated_at,
            version=2,
        )
        return self.invalidated


class RecordingAudit:
    """Capture one minimized invalidation event."""

    def __init__(self) -> None:
        self.event: dict[str, object] | None = None

    async def append_invalidation(self, **values: object) -> None:
        self.event = values


class RecordingTransaction:
    """Record whether a mutation crossed its transaction boundary."""

    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


def principal(
    *,
    admin: bool = False,
    source: DirectoryGroupResolutionSource = DirectoryGroupResolutionSource.MICROSOFT_GRAPH,
) -> Principal:
    """Return a mapped corporate principal with minimized provenance."""
    return Principal(
        user_id=f"{TENANT_ID}:{OBJECT_ID}",
        is_admin=admin,
        directory_identity=DirectoryIdentity(
            tenant_id=TENANT_ID,
            object_id=OBJECT_ID,
            account_type=DirectoryAccountType.MEMBER,
        ),
        approval_areas=frozenset({ApprovalArea.SECURITY}),
        authorization_provenance=AuthorizationProvenance(
            catalog_id="enterprise-entra-authorization",
            catalog_version="2026.08.1",
            catalog_digest="a" * 64,
            matched_mapping_ids=("security-reviewers",),
            source_types=("group",),
            group_resolution_source=source,
        ),
    )


def cached_snapshot(*, expires_at: datetime) -> DirectoryAuthorizationSnapshot:
    """Return a deterministic cached decision."""
    return DirectoryAuthorizationSnapshot(
        key=DirectoryAuthorizationCacheKey(TENANT_ID, OBJECT_ID),
        approval_areas=frozenset({ApprovalArea.SECURITY}),
        catalog_id="enterprise-entra-authorization",
        catalog_version="2026.08.1",
        catalog_digest="a" * 64,
        resolved_at=NOW,
        expires_at=expires_at,
        matched_mapping_ids=("security-reviewers",),
        source_types=("group",),
        original_group_resolution_source=(DirectoryGroupResolutionSource.MICROSOFT_GRAPH),
    )


async def test_reuse_returns_only_a_fresh_catalog_bound_snapshot() -> None:
    cache = MemoryCache(cached_snapshot(expires_at=NOW + timedelta(seconds=60)))

    result = await ReuseDirectoryAuthorization(cache, clock=lambda: NOW).execute(
        principal(),
        catalog_digest="a" * 64,
    )

    assert result is not None
    assert result.authorization_provenance is not None
    assert (
        result.authorization_provenance.group_resolution_source
        is DirectoryGroupResolutionSource.CACHE
    )


async def test_reuse_rejects_expired_snapshot() -> None:
    cache = MemoryCache(cached_snapshot(expires_at=NOW + timedelta(seconds=1)))

    result = await ReuseDirectoryAuthorization(
        cache,
        clock=lambda: NOW + timedelta(seconds=1),
    ).execute(
        principal(),
        catalog_digest="a" * 64,
    )

    assert result is None


async def test_live_resolution_is_cached_without_raw_group_data() -> None:
    cache = MemoryCache()
    transaction = RecordingTransaction()
    resolution_started_at = NOW - timedelta(seconds=5)

    result = await CacheResolvedDirectoryAuthorization(
        cache,
        transaction,
        ttl_seconds=60,
        clock=lambda: NOW,
    ).execute(principal(), resolved_at=resolution_started_at)

    assert result.approval_areas == frozenset({ApprovalArea.SECURITY})
    assert cache.saved is not None
    assert cache.saved.resolved_at == resolution_started_at
    assert cache.saved.expires_at == resolution_started_at + timedelta(seconds=60)
    assert cache.saved.matched_mapping_ids == ("security-reviewers",)
    assert not hasattr(cache.saved, "group_object_ids")
    assert transaction.committed


async def test_overage_without_graph_is_never_cached() -> None:
    cache = MemoryCache()
    transaction = RecordingTransaction()

    await CacheResolvedDirectoryAuthorization(
        cache,
        transaction,
        ttl_seconds=60,
        clock=lambda: NOW,
    ).execute(principal(source=DirectoryGroupResolutionSource.OVERAGE_UNRESOLVED))

    assert cache.saved is None
    assert not transaction.committed


async def test_concurrent_invalidation_rejects_older_live_snapshot() -> None:
    cache = MemoryCache()
    cache.save_allowed = False

    with pytest.raises(DirectoryAuthorizationCacheUnavailable, match="invalidation"):
        await CacheResolvedDirectoryAuthorization(
            cache,
            RecordingTransaction(),
            ttl_seconds=60,
            clock=lambda: NOW,
        ).execute(principal())


async def test_admin_invalidation_is_audited_and_committed() -> None:
    cache = MemoryCache()
    audit = RecordingAudit()
    transaction = RecordingTransaction()

    result = await InvalidateDirectoryAuthorization(
        cache,
        audit,
        transaction,
        allowed_tenant_ids=frozenset({TENANT_ID}),
        clock=lambda: NOW,
    ).execute(
        tenant_id=TENANT_ID,
        object_id=OBJECT_ID,
        reason=DirectoryAuthorizationInvalidationReason.ACCESS_REMOVED,
        reference="IAM-2026-184",
        actor=principal(admin=True),
    )

    assert result.version == 2
    assert audit.event is not None
    assert audit.event["reason"] is DirectoryAuthorizationInvalidationReason.ACCESS_REMOVED
    assert transaction.committed


async def test_non_admin_cannot_invalidate_authorization() -> None:
    with pytest.raises(ApplicationError) as caught:
        await InvalidateDirectoryAuthorization(
            MemoryCache(),
            RecordingAudit(),
            RecordingTransaction(),
            allowed_tenant_ids=frozenset({TENANT_ID}),
            clock=lambda: NOW,
        ).execute(
            tenant_id=TENANT_ID,
            object_id=OBJECT_ID,
            reason=DirectoryAuthorizationInvalidationReason.MANUAL_REVALIDATION,
            reference=None,
            actor=principal(),
        )

    assert caught.value.kind is ErrorKind.FORBIDDEN


async def test_admin_cannot_create_marker_outside_configured_tenant() -> None:
    with pytest.raises(ApplicationError) as caught:
        await InvalidateDirectoryAuthorization(
            MemoryCache(),
            RecordingAudit(),
            RecordingTransaction(),
            allowed_tenant_ids=frozenset({"33333333-3333-4333-8333-333333333333"}),
            clock=lambda: NOW,
        ).execute(
            tenant_id=TENANT_ID,
            object_id=OBJECT_ID,
            reason=DirectoryAuthorizationInvalidationReason.MANUAL_REVALIDATION,
            reference=None,
            actor=principal(admin=True),
        )

    assert caught.value.kind is ErrorKind.UNPROCESSABLE
