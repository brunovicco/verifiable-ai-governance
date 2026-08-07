"""SQLAlchemy adapters for emergency directory-access restrictions."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_governance_api.adapters.directory_authorization_cache import (
    SqlAlchemyDirectoryAuthorizationCache,
)
from ai_governance_api.application.directory_access import DirectoryAccessUnavailable
from ai_governance_api.application.directory_authorization_cache import (
    DirectoryAuthorizationCacheUnavailable,
)
from ai_governance_api.audit import append_audit_event
from ai_governance_api.domain.directory_access import (
    DirectoryAccessChangeReason,
    DirectoryAccessError,
    DirectoryAccessState,
    DirectoryAccessTarget,
)
from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationCacheKey,
    DirectoryAuthorizationInvalidation,
)
from ai_governance_api.models import DirectoryAccessRestrictionEntry


class SqlAlchemyDirectoryAccessStore:
    """Persist current access state consistently across API replicas."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with a transaction-capable session."""
        self._session = session

    async def load(self, target: DirectoryAccessTarget) -> DirectoryAccessState | None:
        """Load and validate one identity-bound access state."""
        try:
            entity = await self._session.get(
                DirectoryAccessRestrictionEntry,
                target.entry_id,
            )
        except SQLAlchemyError as exc:
            raise DirectoryAccessUnavailable("Directory access state could not be read") from exc
        if entity is None:
            return None
        return _state_from_entity(entity, target)

    async def set_state(
        self,
        target: DirectoryAccessTarget,
        *,
        blocked: bool,
        changed_at: datetime,
    ) -> DirectoryAccessState:
        """Upsert a state transition without overwriting a newer concurrent event."""
        table = DirectoryAccessRestrictionEntry.__table__
        values: dict[str, Any] = {
            "id": target.entry_id,
            "tenant_id": target.tenant_id,
            "object_id": target.object_id,
            "blocked": blocked,
            "changed_at": changed_at,
            "version": 1,
            "created_at": changed_at,
            "updated_at": changed_at,
        }
        insert = self._dialect_insert(values)
        statement = insert.on_conflict_do_update(
            index_elements=[table.c.id],
            set_={
                "tenant_id": insert.excluded.tenant_id,
                "object_id": insert.excluded.object_id,
                "blocked": insert.excluded.blocked,
                "changed_at": insert.excluded.changed_at,
                "version": table.c.version + 1,
                "updated_at": insert.excluded.updated_at,
            },
            where=table.c.changed_at <= insert.excluded.changed_at,
        ).returning(table.c.id)
        try:
            result = await self._session.execute(statement)
            entry_id = result.scalar_one_or_none()
            if entry_id is None:
                raise DirectoryAccessUnavailable(
                    "A newer directory access transition already exists"
                )
            await self._session.flush()
            entity = await self._session.scalar(
                select(DirectoryAccessRestrictionEntry)
                .where(DirectoryAccessRestrictionEntry.id == entry_id)
                .execution_options(populate_existing=True)
            )
        except DirectoryAccessUnavailable:
            raise
        except SQLAlchemyError as exc:
            raise DirectoryAccessUnavailable("Directory access state could not be updated") from exc
        if entity is None:
            raise DirectoryAccessUnavailable("Directory access state was not persisted")
        return _state_from_entity(entity, target)

    def _dialect_insert(self, values: dict[str, Any]) -> Any:
        """Build a native upsert for PostgreSQL or the SQLite test adapter."""
        bind = self._session.get_bind()
        if bind.dialect.name == "postgresql":
            return postgresql_insert(DirectoryAccessRestrictionEntry).values(**values)
        if bind.dialect.name == "sqlite":
            return sqlite_insert(DirectoryAccessRestrictionEntry).values(**values)
        raise DirectoryAccessUnavailable(
            "Directory access restrictions require PostgreSQL or SQLite"
        )


class SqlAlchemyDirectoryAccessReader:
    """Read restriction state in a short-lived transaction on every request."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the reader with the shared session factory."""
        self._session_factory = session_factory

    async def load(self, target: DirectoryAccessTarget) -> DirectoryAccessState | None:
        """Load one state and release the database connection immediately."""
        async with self._session_factory() as session:
            return await SqlAlchemyDirectoryAccessStore(session).load(target)


class SqlAlchemyDirectoryAccessCacheInvalidation:
    """Adapt cache invalidation failures to the emergency-access boundary."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter over the shared cache transaction session."""
        self._cache = SqlAlchemyDirectoryAuthorizationCache(session)

    async def invalidate(
        self,
        key: DirectoryAuthorizationCacheKey,
        invalidated_at: datetime,
    ) -> DirectoryAuthorizationInvalidation:
        """Invalidate authorization or expose one access-specific dependency error."""
        try:
            return await self._cache.invalidate(key, invalidated_at)
        except DirectoryAuthorizationCacheUnavailable as exc:
            raise DirectoryAccessUnavailable(
                "Directory authorization cache could not be invalidated"
            ) from exc


class SqlAlchemyDirectoryAccessAudit:
    """Append minimized access changes to the tamper-evident audit chain."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the audit adapter with the mutation transaction."""
        self._session = session

    async def append_change(
        self,
        *,
        actor_id: str,
        state: DirectoryAccessState,
        reason: DirectoryAccessChangeReason,
        reference: str | None,
        authorization_cache_version: int,
    ) -> None:
        """Record bounded context without raw tenant or object identifiers."""
        try:
            await append_audit_event(
                self._session,
                actor_id=actor_id,
                action=(
                    "directory_access.blocked" if state.blocked else "directory_access.restored"
                ),
                entity_type="directory_access_restriction",
                entity_id=state.target.entry_id,
                entity_version=state.version,
                payload={
                    "target_digest": state.target.target_digest,
                    "blocked": state.blocked,
                    "reason": reason.value,
                    "reference": reference,
                    "changed_at": state.changed_at.isoformat(),
                    "authorization_cache_version": authorization_cache_version,
                },
            )
        except SQLAlchemyError as exc:
            raise DirectoryAccessUnavailable(
                "Directory access audit evidence could not be appended"
            ) from exc


class SqlAlchemyDirectoryAccessTransaction:
    """Commit restriction, cache invalidation, and audit as one transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the transaction adapter with a request-scoped session."""
        self._session = session

    async def commit(self) -> None:
        """Commit or translate a database failure into a safe dependency error."""
        try:
            await self._session.commit()
        except SQLAlchemyError as exc:
            await self._session.rollback()
            raise DirectoryAccessUnavailable("Directory access transaction failed") from exc


def _state_from_entity(
    entity: DirectoryAccessRestrictionEntry,
    target: DirectoryAccessTarget,
) -> DirectoryAccessState:
    """Validate persistence binding before returning a domain state."""
    if entity.tenant_id != target.tenant_id or entity.object_id != target.object_id:
        raise DirectoryAccessUnavailable("Directory access identity binding is invalid")
    try:
        return DirectoryAccessState(
            target=target,
            blocked=entity.blocked,
            changed_at=_as_utc(entity.changed_at),
            version=entity.version,
        )
    except DirectoryAccessError as exc:
        raise DirectoryAccessUnavailable("Directory access state is invalid") from exc


def _as_utc(value: datetime | None) -> datetime:
    """Normalize SQLite-naive timestamps while preserving real timezone instants."""
    if value is None:
        raise DirectoryAccessUnavailable("Directory access timestamp is missing")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
