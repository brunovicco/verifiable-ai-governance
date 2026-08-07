"""SQLAlchemy adapters for shared directory-authorization cache use cases."""

from datetime import UTC, datetime
from typing import Any

from governance_schemas import ApprovalArea
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_governance_api.application.directory_authorization_cache import (
    DirectoryAuthorizationCacheUnavailable,
)
from ai_governance_api.audit import append_audit_event
from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationCacheError,
    DirectoryAuthorizationCacheKey,
    DirectoryAuthorizationInvalidation,
    DirectoryAuthorizationInvalidationReason,
    DirectoryAuthorizationSnapshot,
)
from ai_governance_api.domain.identity import DirectoryGroupResolutionSource
from ai_governance_api.models import DirectoryAuthorizationCacheEntry


class SqlAlchemyDirectoryAuthorizationCache:
    """Persist minimal authorization snapshots consistently across API replicas."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with a request-scoped transaction session."""
        self._session = session

    async def load(
        self,
        key: DirectoryAuthorizationCacheKey,
    ) -> DirectoryAuthorizationSnapshot | None:
        """Return a complete stored snapshot without deciding whether it is fresh."""
        try:
            entity = await self._session.get(
                DirectoryAuthorizationCacheEntry,
                key.entry_id,
            )
        except SQLAlchemyError as exc:
            raise DirectoryAuthorizationCacheUnavailable(
                "Shared authorization cache could not be read"
            ) from exc
        if entity is None or not _has_complete_snapshot(entity):
            return None
        if entity.tenant_id != key.tenant_id or entity.object_id != key.object_id:
            raise DirectoryAuthorizationCacheUnavailable(
                "Shared authorization cache identity binding is invalid"
            )
        try:
            return DirectoryAuthorizationSnapshot(
                key=key,
                approval_areas=frozenset(ApprovalArea(value) for value in entity.approval_areas),
                catalog_id=entity.catalog_id or "",
                catalog_version=entity.catalog_version or "",
                catalog_digest=entity.catalog_digest or "",
                resolved_at=_as_utc(entity.resolved_at),
                expires_at=_as_utc(entity.expires_at),
                matched_mapping_ids=tuple(entity.matched_mapping_ids),
                source_types=tuple(entity.source_types),
                original_group_resolution_source=DirectoryGroupResolutionSource(
                    entity.original_group_resolution_source
                    or DirectoryGroupResolutionSource.NONE.value
                ),
                invalidated_at=(
                    _as_utc(entity.invalidated_at) if entity.invalidated_at is not None else None
                ),
                version=entity.version,
            )
        except (ValueError, DirectoryAuthorizationCacheError) as exc:
            raise DirectoryAuthorizationCacheUnavailable(
                "Shared authorization cache contains an invalid snapshot"
            ) from exc

    async def save(self, snapshot: DirectoryAuthorizationSnapshot) -> bool:
        """Upsert a snapshot without overwriting newer data or invalidation."""
        table = DirectoryAuthorizationCacheEntry.__table__
        values: dict[str, Any] = {
            "id": snapshot.key.entry_id,
            "tenant_id": snapshot.key.tenant_id,
            "object_id": snapshot.key.object_id,
            "catalog_id": snapshot.catalog_id,
            "catalog_version": snapshot.catalog_version,
            "catalog_digest": snapshot.catalog_digest,
            "approval_areas": sorted(area.value for area in snapshot.approval_areas),
            "matched_mapping_ids": list(snapshot.matched_mapping_ids),
            "source_types": list(snapshot.source_types),
            "original_group_resolution_source": (snapshot.original_group_resolution_source.value),
            "resolved_at": snapshot.resolved_at,
            "expires_at": snapshot.expires_at,
            "invalidated_at": None,
            "version": 1,
            "created_at": snapshot.resolved_at,
            "updated_at": snapshot.resolved_at,
        }
        insert = self._dialect_insert(values)
        statement = insert.on_conflict_do_update(
            index_elements=[table.c.id],
            set_={
                "tenant_id": insert.excluded.tenant_id,
                "object_id": insert.excluded.object_id,
                "catalog_id": insert.excluded.catalog_id,
                "catalog_version": insert.excluded.catalog_version,
                "catalog_digest": insert.excluded.catalog_digest,
                "approval_areas": insert.excluded.approval_areas,
                "matched_mapping_ids": insert.excluded.matched_mapping_ids,
                "source_types": insert.excluded.source_types,
                "original_group_resolution_source": (
                    insert.excluded.original_group_resolution_source
                ),
                "resolved_at": insert.excluded.resolved_at,
                "expires_at": insert.excluded.expires_at,
                "invalidated_at": None,
                "version": table.c.version + 1,
                "updated_at": insert.excluded.updated_at,
            },
            where=or_(
                table.c.resolved_at.is_(None),
                table.c.resolved_at <= insert.excluded.resolved_at,
            )
            & or_(
                table.c.invalidated_at.is_(None),
                table.c.invalidated_at < insert.excluded.resolved_at,
            ),
        ).returning(table.c.id)
        try:
            result = await self._session.execute(statement)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise DirectoryAuthorizationCacheUnavailable(
                "Shared authorization cache could not be updated"
            ) from exc
        return result.scalar_one_or_none() is not None

    async def invalidate(
        self,
        key: DirectoryAuthorizationCacheKey,
        invalidated_at: datetime,
    ) -> DirectoryAuthorizationInvalidation:
        """Atomically replace any snapshot with a shared invalidation marker."""
        table = DirectoryAuthorizationCacheEntry.__table__
        values: dict[str, Any] = {
            "id": key.entry_id,
            "tenant_id": key.tenant_id,
            "object_id": key.object_id,
            "catalog_id": None,
            "catalog_version": None,
            "catalog_digest": None,
            "approval_areas": [],
            "matched_mapping_ids": [],
            "source_types": [],
            "original_group_resolution_source": None,
            "resolved_at": None,
            "expires_at": None,
            "invalidated_at": invalidated_at,
            "version": 1,
            "created_at": invalidated_at,
            "updated_at": invalidated_at,
        }
        insert = self._dialect_insert(values)
        statement = insert.on_conflict_do_update(
            index_elements=[table.c.id],
            set_={
                "catalog_id": None,
                "catalog_version": None,
                "catalog_digest": None,
                "approval_areas": [],
                "matched_mapping_ids": [],
                "source_types": [],
                "original_group_resolution_source": None,
                "resolved_at": None,
                "expires_at": None,
                "invalidated_at": insert.excluded.invalidated_at,
                "version": table.c.version + 1,
                "updated_at": insert.excluded.updated_at,
            },
        )
        try:
            await self._session.execute(statement)
            await self._session.flush()
            entity = await self._session.scalar(
                select(DirectoryAuthorizationCacheEntry)
                .where(DirectoryAuthorizationCacheEntry.id == key.entry_id)
                .execution_options(populate_existing=True)
            )
        except SQLAlchemyError as exc:
            raise DirectoryAuthorizationCacheUnavailable(
                "Shared authorization cache could not be invalidated"
            ) from exc
        if entity is None or entity.invalidated_at is None:
            raise DirectoryAuthorizationCacheUnavailable(
                "Shared authorization cache invalidation was not persisted"
            )
        return DirectoryAuthorizationInvalidation(
            key=key,
            invalidated_at=_as_utc(entity.invalidated_at),
            version=entity.version,
        )

    def _dialect_insert(self, values: dict[str, Any]) -> Any:
        """Build a supported native upsert for PostgreSQL or test SQLite."""
        bind = self._session.get_bind()
        if bind.dialect.name == "postgresql":
            return postgresql_insert(DirectoryAuthorizationCacheEntry).values(**values)
        if bind.dialect.name == "sqlite":
            return sqlite_insert(DirectoryAuthorizationCacheEntry).values(**values)
        raise DirectoryAuthorizationCacheUnavailable(
            "Shared authorization cache requires PostgreSQL or SQLite"
        )


class SqlAlchemyDirectoryAuthorizationCacheReader:
    """Read shared snapshots without holding a request transaction during Graph I/O."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the reader with a short-lived session factory."""
        self._session_factory = session_factory

    async def load(
        self,
        key: DirectoryAuthorizationCacheKey,
    ) -> DirectoryAuthorizationSnapshot | None:
        """Load one snapshot and release its database connection immediately."""
        async with self._session_factory() as session:
            return await SqlAlchemyDirectoryAuthorizationCache(session).load(key)


class SqlAlchemyDirectoryAuthorizationCacheAudit:
    """Append invalidations to the shared tamper-evident audit chain."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the audit adapter with the mutation transaction."""
        self._session = session

    async def append_invalidation(
        self,
        *,
        actor_id: str,
        invalidation: DirectoryAuthorizationInvalidation,
        reason: DirectoryAuthorizationInvalidationReason,
        reference: str | None,
    ) -> None:
        """Record bounded context without raw tenant or object identifiers."""
        await append_audit_event(
            self._session,
            actor_id=actor_id,
            action="directory_authorization_cache.invalidated",
            entity_type="directory_authorization_cache",
            entity_id=invalidation.key.entry_id,
            entity_version=invalidation.version,
            payload={
                "target_digest": invalidation.key.target_digest,
                "reason": reason.value,
                "reference": reference,
                "invalidated_at": invalidation.invalidated_at.isoformat(),
            },
        )


class SqlAlchemyDirectoryAuthorizationCacheTransaction:
    """Commit cache mutations and audit evidence through one database transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the transaction adapter with a request-scoped session."""
        self._session = session

    async def commit(self) -> None:
        """Commit or translate a database failure into a safe application error."""
        try:
            await self._session.commit()
        except SQLAlchemyError as exc:
            await self._session.rollback()
            raise DirectoryAuthorizationCacheUnavailable(
                "Shared authorization cache transaction failed"
            ) from exc


def _has_complete_snapshot(entity: DirectoryAuthorizationCacheEntry) -> bool:
    """Return whether the row contains every field required by the domain record."""
    return all(
        value is not None
        for value in (
            entity.catalog_id,
            entity.catalog_version,
            entity.catalog_digest,
            entity.original_group_resolution_source,
            entity.resolved_at,
            entity.expires_at,
        )
    )


def _as_utc(value: datetime | None) -> datetime:
    """Normalize SQLite-naive timestamps while preserving real timezone instants."""
    if value is None:
        raise DirectoryAuthorizationCacheUnavailable(
            "Shared authorization cache timestamp is missing"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
