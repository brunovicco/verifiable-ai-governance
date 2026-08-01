from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.adapters.directory_access import (
    SqlAlchemyDirectoryAccessReader,
    SqlAlchemyDirectoryAccessStore,
)
from ai_governance_api.application.directory_access import DirectoryAccessUnavailable
from ai_governance_api.database import SessionFactory
from ai_governance_api.domain.directory_access import DirectoryAccessTarget
from ai_governance_api.models import DirectoryAccessRestrictionEntry

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


async def test_store_round_trip_block_and_restore() -> None:
    target = DirectoryAccessTarget(TENANT_ID, OBJECT_ID)
    async with SessionFactory() as session:
        blocked = await SqlAlchemyDirectoryAccessStore(session).set_state(
            target,
            blocked=True,
            changed_at=NOW,
        )
        await session.commit()

    assert blocked.blocked
    assert blocked.version == 1
    stored = await SqlAlchemyDirectoryAccessReader(SessionFactory).load(target)
    assert stored == blocked

    async with SessionFactory() as session:
        restored = await SqlAlchemyDirectoryAccessStore(session).set_state(
            target,
            blocked=False,
            changed_at=NOW + timedelta(seconds=1),
        )
        await session.commit()

    assert not restored.blocked
    assert restored.version == 2


async def test_store_rejects_older_concurrent_transition() -> None:
    target = DirectoryAccessTarget(TENANT_ID, OBJECT_ID)
    async with SessionFactory() as session:
        await SqlAlchemyDirectoryAccessStore(session).set_state(
            target,
            blocked=True,
            changed_at=NOW + timedelta(seconds=5),
        )
        await session.commit()

    async with SessionFactory() as session:
        with pytest.raises(DirectoryAccessUnavailable, match="newer"):
            await SqlAlchemyDirectoryAccessStore(session).set_state(
                target,
                blocked=False,
                changed_at=NOW,
            )


async def test_load_rejects_persisted_identity_binding_mismatch() -> None:
    target = DirectoryAccessTarget(TENANT_ID, OBJECT_ID)
    async with SessionFactory() as session:
        await SqlAlchemyDirectoryAccessStore(session).set_state(
            target,
            blocked=True,
            changed_at=NOW,
        )
        await session.commit()

    async with SessionFactory() as session:
        entity = await session.get(DirectoryAccessRestrictionEntry, target.entry_id)
        assert entity is not None
        entity.object_id = "33333333-3333-4333-8333-333333333333"
        await session.commit()

    with pytest.raises(DirectoryAccessUnavailable, match="binding"):
        await SqlAlchemyDirectoryAccessReader(SessionFactory).load(target)
