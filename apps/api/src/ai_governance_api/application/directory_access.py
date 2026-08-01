"""Use cases and ports for emergency directory-access restrictions."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from ai_governance_api.domain.directory_access import (
    DirectoryAccessBlockReason,
    DirectoryAccessChangeReason,
    DirectoryAccessError,
    DirectoryAccessRestoreReason,
    DirectoryAccessState,
    DirectoryAccessTarget,
)
from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationCacheKey,
    DirectoryAuthorizationInvalidation,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]


class DirectoryAccessUnavailable(Exception):
    """Raised when shared emergency access state cannot be trusted or changed."""


class DirectoryAccessReaderPort(Protocol):
    """Consumer-owned read operation for current directory-access state."""

    async def load(self, target: DirectoryAccessTarget) -> DirectoryAccessState | None:
        """Return the current state when one has been recorded."""
        ...


class DirectoryAccessWriterPort(Protocol):
    """Consumer-owned mutation for one directory-access state."""

    async def set_state(
        self,
        target: DirectoryAccessTarget,
        *,
        blocked: bool,
        changed_at: datetime,
    ) -> DirectoryAccessState:
        """Persist and return the requested current state atomically."""
        ...


class DirectoryAccessCacheInvalidationPort(Protocol):
    """Minimal authorization-cache operation required by access changes."""

    async def invalidate(
        self,
        key: DirectoryAuthorizationCacheKey,
        invalidated_at: datetime,
    ) -> DirectoryAuthorizationInvalidation:
        """Invalidate any authorization decision for the changed identity."""
        ...


class DirectoryAccessAuditPort(Protocol):
    """Content-minimized audit operation for emergency access changes."""

    async def append_change(
        self,
        *,
        actor_id: str,
        state: DirectoryAccessState,
        reason: DirectoryAccessChangeReason,
        reference: str | None,
        authorization_cache_version: int,
    ) -> None:
        """Append one access-state event without raw target identifiers."""
        ...


class DirectoryAccessTransactionPort(Protocol):
    """Atomic boundary for access state, cache invalidation, and audit evidence."""

    async def commit(self) -> None:
        """Commit all pending access-change operations atomically."""
        ...


class RequireActiveDirectoryAccess:
    """Deny every platform request for an identity under emergency restriction."""

    def __init__(self, reader: DirectoryAccessReaderPort) -> None:
        """Initialize the query with its short-lived persistence reader."""
        self._reader = reader

    async def execute(self, principal: Principal) -> Principal:
        """Return unrestricted principals and reject an explicitly blocked identity."""
        identity = principal.directory_identity
        if identity is None:
            return principal
        try:
            target = DirectoryAccessTarget.from_identity(identity)
        except DirectoryAccessError as exc:
            raise DirectoryAccessUnavailable(
                "Authenticated directory identity is invalid"
            ) from exc
        state = await self._reader.load(target)
        if state is not None and state.blocked:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Directory identity access is suspended",
            )
        return principal


class BlockDirectoryAccess:
    """Persist an immediate platform block with cache and audit evidence."""

    def __init__(
        self,
        writer: DirectoryAccessWriterPort,
        cache: DirectoryAccessCacheInvalidationPort,
        audit: DirectoryAccessAuditPort,
        transaction: DirectoryAccessTransactionPort,
        *,
        allowed_tenant_ids: frozenset[str],
        clock: Clock | None = None,
    ) -> None:
        """Initialize the command with explicit dependencies and tenant boundary."""
        self._change = _ChangeDirectoryAccess(
            writer,
            cache,
            audit,
            transaction,
            allowed_tenant_ids=allowed_tenant_ids,
            clock=clock,
        )

    async def execute(
        self,
        *,
        tenant_id: str,
        object_id: str,
        reason: DirectoryAccessBlockReason,
        reference: str | None,
        actor: Principal,
    ) -> DirectoryAccessState:
        """Block the target immediately within every platform replica."""
        return await self._change.execute(
            tenant_id=tenant_id,
            object_id=object_id,
            blocked=True,
            reason=reason,
            reference=reference,
            actor=actor,
        )


class RestoreDirectoryAccess:
    """Restore platform access while forcing fresh directory authorization."""

    def __init__(
        self,
        writer: DirectoryAccessWriterPort,
        cache: DirectoryAccessCacheInvalidationPort,
        audit: DirectoryAccessAuditPort,
        transaction: DirectoryAccessTransactionPort,
        *,
        allowed_tenant_ids: frozenset[str],
        clock: Clock | None = None,
    ) -> None:
        """Initialize the command with explicit dependencies and tenant boundary."""
        self._change = _ChangeDirectoryAccess(
            writer,
            cache,
            audit,
            transaction,
            allowed_tenant_ids=allowed_tenant_ids,
            clock=clock,
        )

    async def execute(
        self,
        *,
        tenant_id: str,
        object_id: str,
        reason: DirectoryAccessRestoreReason,
        reference: str | None,
        actor: Principal,
    ) -> DirectoryAccessState:
        """Restore the target and invalidate any pre-incident authorization snapshot."""
        return await self._change.execute(
            tenant_id=tenant_id,
            object_id=object_id,
            blocked=False,
            reason=reason,
            reference=reference,
            actor=actor,
        )


class _ChangeDirectoryAccess:
    """Shared application service for audited block and restore transitions."""

    def __init__(
        self,
        writer: DirectoryAccessWriterPort,
        cache: DirectoryAccessCacheInvalidationPort,
        audit: DirectoryAccessAuditPort,
        transaction: DirectoryAccessTransactionPort,
        *,
        allowed_tenant_ids: frozenset[str],
        clock: Clock | None,
    ) -> None:
        """Store collaborators without importing delivery or persistence frameworks."""
        self._writer = writer
        self._cache = cache
        self._audit = audit
        self._transaction = transaction
        self._allowed_tenant_ids = allowed_tenant_ids
        self._clock = clock or (lambda: datetime.now(UTC))

    async def execute(
        self,
        *,
        tenant_id: str,
        object_id: str,
        blocked: bool,
        reason: DirectoryAccessChangeReason,
        reference: str | None,
        actor: Principal,
    ) -> DirectoryAccessState:
        """Apply a tenant-bounded state change as one atomic application operation."""
        if not actor.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only an administrator can change directory access",
            )
        try:
            target = DirectoryAccessTarget(tenant_id=tenant_id, object_id=object_id)
        except DirectoryAccessError as exc:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                "Directory access target is invalid",
            ) from exc
        if target.tenant_id not in self._allowed_tenant_ids:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                "Directory access target is outside the configured tenant boundary",
            )

        changed_at = self._clock()
        try:
            state = await self._writer.set_state(
                target,
                blocked=blocked,
                changed_at=changed_at,
            )
            if state.blocked is not blocked or state.changed_at != changed_at:
                raise DirectoryAccessUnavailable(
                    "A concurrent directory access change superseded this operation"
                )
            invalidation = await self._cache.invalidate(
                DirectoryAuthorizationCacheKey(
                    tenant_id=target.tenant_id,
                    object_id=target.object_id,
                ),
                changed_at,
            )
            await self._audit.append_change(
                actor_id=actor.user_id,
                state=state,
                reason=reason,
                reference=reference,
                authorization_cache_version=invalidation.version,
            )
            await self._transaction.commit()
        except DirectoryAccessUnavailable as exc:
            raise ApplicationError(
                ErrorKind.DEPENDENCY_UNAVAILABLE,
                "Directory access change could not be committed safely",
            ) from exc
        return state
