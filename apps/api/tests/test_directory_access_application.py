from datetime import UTC, datetime

import pytest
from ai_governance_api.application.directory_access import (
    BlockDirectoryAccess,
    DirectoryAccessUnavailable,
    RequireActiveDirectoryAccess,
    RestoreDirectoryAccess,
)
from ai_governance_api.domain.directory_access import (
    DirectoryAccessBlockReason,
    DirectoryAccessRestoreReason,
    DirectoryAccessState,
    DirectoryAccessTarget,
)
from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationCacheKey,
    DirectoryAuthorizationInvalidation,
)
from ai_governance_api.domain.identity import (
    DirectoryAccountType,
    DirectoryIdentity,
    Principal,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


class MemoryAccessStore:
    """Record current access state for application tests."""

    def __init__(self, state: DirectoryAccessState | None = None) -> None:
        self.state = state

    async def load(self, target: DirectoryAccessTarget) -> DirectoryAccessState | None:
        assert target == DirectoryAccessTarget(TENANT_ID, OBJECT_ID)
        return self.state

    async def set_state(
        self,
        target: DirectoryAccessTarget,
        *,
        blocked: bool,
        changed_at: datetime,
    ) -> DirectoryAccessState:
        self.state = DirectoryAccessState(
            target=target,
            blocked=blocked,
            changed_at=changed_at,
            version=(self.state.version + 1 if self.state is not None else 1),
        )
        return self.state


class RecordingCache:
    """Capture cache invalidation coordinated with an access transition."""

    def __init__(self) -> None:
        self.key: DirectoryAuthorizationCacheKey | None = None
        self.invalidated_at: datetime | None = None
        self.unavailable = False

    async def invalidate(
        self,
        key: DirectoryAuthorizationCacheKey,
        invalidated_at: datetime,
    ) -> DirectoryAuthorizationInvalidation:
        if self.unavailable:
            raise DirectoryAccessUnavailable("cache unavailable")
        self.key = key
        self.invalidated_at = invalidated_at
        return DirectoryAuthorizationInvalidation(
            key=key,
            invalidated_at=invalidated_at,
            version=4,
        )


class RecordingAudit:
    """Capture minimized access-change evidence."""

    def __init__(self) -> None:
        self.event: dict[str, object] | None = None

    async def append_change(self, **values: object) -> None:
        self.event = values


class RecordingTransaction:
    """Record whether all operations reached their atomic boundary."""

    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


def corporate_principal(*, admin: bool = False) -> Principal:
    """Return a deterministic Entra principal."""
    return Principal(
        user_id=f"{TENANT_ID}:{OBJECT_ID}",
        is_admin=admin,
        directory_identity=DirectoryIdentity(
            tenant_id=TENANT_ID,
            object_id=OBJECT_ID,
            account_type=DirectoryAccountType.MEMBER,
        ),
    )


def administrator() -> Principal:
    """Return an administrator distinct from the target identity."""
    return Principal(user_id="incident-admin", is_admin=True)


async def test_active_access_query_allows_absent_state_and_local_principal() -> None:
    store = MemoryAccessStore()
    query = RequireActiveDirectoryAccess(store)

    assert await query.execute(corporate_principal()) == corporate_principal()
    local = Principal(user_id="local-user")
    assert await query.execute(local) is local


async def test_active_access_query_rejects_blocked_identity() -> None:
    state = DirectoryAccessState(
        target=DirectoryAccessTarget(TENANT_ID, OBJECT_ID),
        blocked=True,
        changed_at=NOW,
        version=1,
    )

    with pytest.raises(ApplicationError) as caught:
        await RequireActiveDirectoryAccess(MemoryAccessStore(state)).execute(corporate_principal())

    assert caught.value.kind is ErrorKind.FORBIDDEN


async def test_admin_block_is_atomic_with_cache_invalidation_and_audit() -> None:
    store = MemoryAccessStore()
    cache = RecordingCache()
    audit = RecordingAudit()
    transaction = RecordingTransaction()

    state = await BlockDirectoryAccess(
        store,
        cache,
        audit,
        transaction,
        allowed_tenant_ids=frozenset({TENANT_ID}),
        clock=lambda: NOW,
    ).execute(
        tenant_id=TENANT_ID,
        object_id=OBJECT_ID,
        reason=DirectoryAccessBlockReason.ACCOUNT_COMPROMISED,
        reference="INC-2026-184",
        actor=administrator(),
    )

    assert state.blocked
    assert cache.key == DirectoryAuthorizationCacheKey(TENANT_ID, OBJECT_ID)
    assert cache.invalidated_at == state.changed_at == NOW
    assert audit.event is not None
    assert audit.event["authorization_cache_version"] == 4
    assert transaction.committed


async def test_restore_keeps_authorization_invalidated_for_fresh_resolution() -> None:
    store = MemoryAccessStore(
        DirectoryAccessState(
            target=DirectoryAccessTarget(TENANT_ID, OBJECT_ID),
            blocked=True,
            changed_at=NOW,
            version=1,
        )
    )
    cache = RecordingCache()

    state = await RestoreDirectoryAccess(
        store,
        cache,
        RecordingAudit(),
        RecordingTransaction(),
        allowed_tenant_ids=frozenset({TENANT_ID}),
        clock=lambda: NOW,
    ).execute(
        tenant_id=TENANT_ID,
        object_id=OBJECT_ID,
        reason=DirectoryAccessRestoreReason.REMEDIATION_COMPLETED,
        reference="INC-2026-184",
        actor=administrator(),
    )

    assert not state.blocked
    assert cache.invalidated_at == NOW


async def test_non_admin_and_out_of_boundary_target_are_rejected() -> None:
    command = BlockDirectoryAccess(
        MemoryAccessStore(),
        RecordingCache(),
        RecordingAudit(),
        RecordingTransaction(),
        allowed_tenant_ids=frozenset({TENANT_ID}),
        clock=lambda: NOW,
    )

    with pytest.raises(ApplicationError) as forbidden:
        await command.execute(
            tenant_id=TENANT_ID,
            object_id=OBJECT_ID,
            reason=DirectoryAccessBlockReason.MANUAL_EMERGENCY,
            reference=None,
            actor=corporate_principal(),
        )
    assert forbidden.value.kind is ErrorKind.FORBIDDEN

    with pytest.raises(ApplicationError) as invalid:
        await command.execute(
            tenant_id="33333333-3333-4333-8333-333333333333",
            object_id=OBJECT_ID,
            reason=DirectoryAccessBlockReason.MANUAL_EMERGENCY,
            reference=None,
            actor=administrator(),
        )
    assert invalid.value.kind is ErrorKind.UNPROCESSABLE


async def test_cache_failure_prevents_commit_and_returns_safe_dependency_error() -> None:
    cache = RecordingCache()
    cache.unavailable = True
    transaction = RecordingTransaction()

    with pytest.raises(ApplicationError) as caught:
        await BlockDirectoryAccess(
            MemoryAccessStore(),
            cache,
            RecordingAudit(),
            transaction,
            allowed_tenant_ids=frozenset({TENANT_ID}),
            clock=lambda: NOW,
        ).execute(
            tenant_id=TENANT_ID,
            object_id=OBJECT_ID,
            reason=DirectoryAccessBlockReason.INCIDENT_RESPONSE,
            reference=None,
            actor=administrator(),
        )

    assert caught.value.kind is ErrorKind.DEPENDENCY_UNAVAILABLE
    assert not transaction.committed
