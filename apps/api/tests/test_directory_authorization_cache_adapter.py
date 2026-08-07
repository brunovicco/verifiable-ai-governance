from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.adapters.directory_authorization_cache import (
    SqlAlchemyDirectoryAuthorizationCache,
    SqlAlchemyDirectoryAuthorizationCacheReader,
)
from ai_governance_api.application.directory_authorization_cache import (
    DirectoryAuthorizationCacheUnavailable,
)
from ai_governance_api.database import SessionFactory
from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationCacheKey,
    DirectoryAuthorizationSnapshot,
)
from ai_governance_api.domain.identity import DirectoryGroupResolutionSource
from ai_governance_api.models import DirectoryAuthorizationCacheEntry
from governance_schemas import ApprovalArea

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def snapshot(resolved_at: datetime) -> DirectoryAuthorizationSnapshot:
    """Return one minimal derived authorization snapshot."""
    return DirectoryAuthorizationSnapshot(
        key=DirectoryAuthorizationCacheKey(TENANT_ID, OBJECT_ID),
        approval_areas=frozenset({ApprovalArea.SECURITY}),
        catalog_id="enterprise-entra-authorization",
        catalog_version="2026.08.1",
        catalog_digest="a" * 64,
        resolved_at=resolved_at,
        expires_at=resolved_at + timedelta(seconds=60),
        matched_mapping_ids=("security-reviewers",),
        source_types=("group",),
        original_group_resolution_source=(DirectoryGroupResolutionSource.MICROSOFT_GRAPH),
    )


async def test_shared_adapter_round_trip_and_invalidation_marker() -> None:
    key = DirectoryAuthorizationCacheKey(TENANT_ID, OBJECT_ID)
    async with SessionFactory() as session:
        adapter = SqlAlchemyDirectoryAuthorizationCache(session)
        assert await adapter.save(snapshot(NOW))
        await session.commit()

    stored = await SqlAlchemyDirectoryAuthorizationCacheReader(SessionFactory).load(key)

    assert stored is not None
    assert stored.approval_areas == frozenset({ApprovalArea.SECURITY})
    assert stored.original_group_resolution_source is (
        DirectoryGroupResolutionSource.MICROSOFT_GRAPH
    )

    async with SessionFactory() as session:
        adapter = SqlAlchemyDirectoryAuthorizationCache(session)
        invalidation = await adapter.invalidate(key, NOW + timedelta(seconds=5))
        await session.commit()

    assert invalidation.version == 2
    async with SessionFactory() as session:
        assert await SqlAlchemyDirectoryAuthorizationCache(session).load(key) is None


async def test_invalidation_rejects_older_refresh_but_accepts_newer_one() -> None:
    key = DirectoryAuthorizationCacheKey(TENANT_ID, OBJECT_ID)
    invalidated_at = NOW + timedelta(seconds=10)
    async with SessionFactory() as session:
        adapter = SqlAlchemyDirectoryAuthorizationCache(session)
        await adapter.invalidate(key, invalidated_at)
        await session.commit()

    async with SessionFactory() as session:
        adapter = SqlAlchemyDirectoryAuthorizationCache(session)
        assert not await adapter.save(snapshot(NOW + timedelta(seconds=5)))
        await session.rollback()

    async with SessionFactory() as session:
        adapter = SqlAlchemyDirectoryAuthorizationCache(session)
        assert await adapter.save(snapshot(NOW + timedelta(seconds=11)))
        await session.commit()

    async with SessionFactory() as session:
        refreshed = await SqlAlchemyDirectoryAuthorizationCache(session).load(key)

    assert refreshed is not None
    assert refreshed.resolved_at == NOW + timedelta(seconds=11)


async def test_load_rejects_persisted_identity_binding_mismatch() -> None:
    key = DirectoryAuthorizationCacheKey(TENANT_ID, OBJECT_ID)
    async with SessionFactory() as session:
        adapter = SqlAlchemyDirectoryAuthorizationCache(session)
        assert await adapter.save(snapshot(NOW))
        await session.commit()

    async with SessionFactory() as session:
        entity = await session.get(DirectoryAuthorizationCacheEntry, key.entry_id)
        assert entity is not None
        entity.tenant_id = "33333333-3333-4333-8333-333333333333"
        await session.commit()

    async with SessionFactory() as session:
        with pytest.raises(DirectoryAuthorizationCacheUnavailable, match="binding"):
            await SqlAlchemyDirectoryAuthorizationCache(session).load(key)
