"""Use cases and ports for shared directory-authorization snapshots."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationCacheError,
    DirectoryAuthorizationCacheKey,
    DirectoryAuthorizationInvalidation,
    DirectoryAuthorizationInvalidationReason,
    DirectoryAuthorizationSnapshot,
)
from ai_governance_api.domain.identity import DirectoryGroupResolutionSource, Principal
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]


class DirectoryAuthorizationCacheUnavailable(Exception):
    """Raised when shared cache state cannot be read or changed safely."""


class DirectoryAuthorizationCacheReaderPort(Protocol):
    """Consumer-owned read operation for shared authorization snapshots."""

    async def load(
        self,
        key: DirectoryAuthorizationCacheKey,
    ) -> DirectoryAuthorizationSnapshot | None:
        """Return the stored snapshot, including stale metadata, when present."""
        ...


class DirectoryAuthorizationCacheWriterPort(Protocol):
    """Consumer-owned write operation for derived authorization snapshots."""

    async def save(self, snapshot: DirectoryAuthorizationSnapshot) -> bool:
        """Persist a newer snapshot unless a concurrent invalidation superseded it."""
        ...


class DirectoryAuthorizationCacheInvalidationPort(Protocol):
    """Consumer-owned write operation for shared invalidation markers."""

    async def invalidate(
        self,
        key: DirectoryAuthorizationCacheKey,
        invalidated_at: datetime,
    ) -> DirectoryAuthorizationInvalidation:
        """Invalidate the identity across every replica sharing the persistence store."""
        ...


class DirectoryAuthorizationCacheAuditPort(Protocol):
    """Content-minimized audit operation for administrative invalidation."""

    async def append_invalidation(
        self,
        *,
        actor_id: str,
        invalidation: DirectoryAuthorizationInvalidation,
        reason: DirectoryAuthorizationInvalidationReason,
        reference: str | None,
    ) -> None:
        """Append an invalidation event without raw tenant or object IDs."""
        ...


class DirectoryAuthorizationCacheTransactionPort(Protocol):
    """Transaction boundary for cache mutations and their audit evidence."""

    async def commit(self) -> None:
        """Atomically commit the pending cache operation."""
        ...


class ReuseDirectoryAuthorization:
    """Reuse only a fresh snapshot bound to the current identity and catalog."""

    def __init__(
        self,
        cache: DirectoryAuthorizationCacheReaderPort,
        *,
        clock: Clock | None = None,
    ) -> None:
        """Initialize the query with an explicit clock seam."""
        self._cache = cache
        self._clock = clock or (lambda: datetime.now(UTC))

    async def execute(
        self,
        principal: Principal,
        *,
        catalog_digest: str,
    ) -> Principal | None:
        """Return an authorized principal only when every freshness check succeeds."""
        identity = principal.directory_identity
        if identity is None:
            return None
        snapshot = await self._cache.load(DirectoryAuthorizationCacheKey.from_identity(identity))
        if snapshot is None or not snapshot.is_fresh(
            now=self._clock(),
            catalog_digest=catalog_digest,
        ):
            return None
        return snapshot.authorize(principal)


class CacheResolvedDirectoryAuthorization:
    """Persist a live, derived decision using a short bounded validity interval."""

    def __init__(
        self,
        cache: DirectoryAuthorizationCacheWriterPort,
        transaction: DirectoryAuthorizationCacheTransactionPort,
        *,
        ttl_seconds: int,
        clock: Clock | None = None,
    ) -> None:
        """Initialize the command with explicit persistence, TTL, and clock seams."""
        if ttl_seconds < 1:
            raise ValueError("Directory authorization cache TTL must be positive")
        self._cache = cache
        self._transaction = transaction
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def execute(
        self,
        principal: Principal,
        *,
        resolved_at: datetime | None = None,
    ) -> Principal:
        """Cache a decision using the instant when its live resolution began."""
        identity = principal.directory_identity
        provenance = principal.authorization_provenance
        if identity is None or provenance is None:
            return principal
        if provenance.group_resolution_source in {
            DirectoryGroupResolutionSource.CACHE,
            DirectoryGroupResolutionSource.OVERAGE_UNRESOLVED,
        }:
            return principal

        resolution_started_at = resolved_at or self._clock()
        snapshot = DirectoryAuthorizationSnapshot(
            key=DirectoryAuthorizationCacheKey.from_identity(identity),
            approval_areas=principal.approval_areas,
            catalog_id=provenance.catalog_id,
            catalog_version=provenance.catalog_version,
            catalog_digest=provenance.catalog_digest,
            resolved_at=resolution_started_at,
            expires_at=resolution_started_at + self._ttl,
            matched_mapping_ids=provenance.matched_mapping_ids,
            source_types=provenance.source_types,
            original_group_resolution_source=provenance.group_resolution_source,
        )
        if not await self._cache.save(snapshot):
            raise DirectoryAuthorizationCacheUnavailable(
                "A concurrent invalidation rejected the authorization snapshot"
            )
        await self._transaction.commit()
        return principal


class InvalidateDirectoryAuthorization:
    """Invalidate one identity snapshot and append atomic audit evidence."""

    def __init__(
        self,
        cache: DirectoryAuthorizationCacheInvalidationPort,
        audit: DirectoryAuthorizationCacheAuditPort,
        transaction: DirectoryAuthorizationCacheTransactionPort,
        *,
        allowed_tenant_ids: frozenset[str],
        clock: Clock | None = None,
    ) -> None:
        """Initialize the administrative command with its required ports."""
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
        reason: DirectoryAuthorizationInvalidationReason,
        reference: str | None,
        actor: Principal,
    ) -> DirectoryAuthorizationInvalidation:
        """Invalidate a target when the caller has explicit administrator authority."""
        if not actor.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only an administrator can invalidate directory authorization",
            )
        try:
            key = DirectoryAuthorizationCacheKey(
                tenant_id=tenant_id,
                object_id=object_id,
            )
        except DirectoryAuthorizationCacheError as exc:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                "Directory authorization target is invalid",
            ) from exc
        if key.tenant_id not in self._allowed_tenant_ids:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                "Directory authorization target is outside the configured tenant boundary",
            )
        invalidation = await self._cache.invalidate(key, self._clock())
        await self._audit.append_invalidation(
            actor_id=actor.user_id,
            invalidation=invalidation,
            reason=reason,
            reference=reference,
        )
        await self._transaction.commit()
        return invalidation
