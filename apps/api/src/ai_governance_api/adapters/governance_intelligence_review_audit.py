"""SQLAlchemy audit adapter for non-authoritative finding review receipts."""

from contextlib import suppress

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_governance_api.application.governance_intelligence_review import (
    GovernanceFindingReviewAuditRecord,
    GovernanceFindingReviewDependencyError,
)
from ai_governance_api.audit import append_audit_event


class SqlAlchemyGovernanceFindingReviewAudit:
    """Commit one content-minimized review receipt per short-lived transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize a request-scoped audit unit without opening a connection."""
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def append(
        self,
        *,
        actor_id: str,
        record: GovernanceFindingReviewAuditRecord,
    ) -> None:
        """Append only identities, digest, disposition, and trace context."""
        if self._session is not None:
            raise GovernanceFindingReviewDependencyError(
                "A finding review audit transaction is already active"
            )
        session = self._session_factory()
        self._session = session
        payload: dict[str, object] = {
            "schema_version": record.schema_version,
            "finding_id": str(record.finding_id),
            "finding_type": record.finding_type.value,
            "agent_run_id": str(record.agent_run_id),
            "candidate_digest": record.candidate_digest,
            "subject_id": record.subject_id,
            "correlation_id": record.correlation_id,
            "disposition": record.disposition.value,
            "administrator_access": record.administrator_access,
            "reviewed_at": record.reviewed_at.isoformat(),
        }
        try:
            await append_audit_event(
                session,
                actor_id=actor_id,
                action="governance_intelligence.finding_reviewed",
                entity_type="governance_intelligence_finding_review",
                entity_id=str(record.review_id),
                entity_version=1,
                payload=payload,
            )
        except SQLAlchemyError as exc:
            await self._discard_session(session)
            raise GovernanceFindingReviewDependencyError(
                "Governance Intelligence finding review audit could not be appended"
            ) from exc

    async def commit(self) -> None:
        """Commit a review receipt or expose one content-free dependency failure."""
        session = self._session
        if session is None:
            raise GovernanceFindingReviewDependencyError(
                "No finding review audit transaction is active"
            )
        error: SQLAlchemyError | None = None
        try:
            await session.commit()
        except SQLAlchemyError as exc:
            error = exc
            with suppress(SQLAlchemyError):
                await session.rollback()
        try:
            await session.close()
        except SQLAlchemyError as exc:
            error = error or exc
        finally:
            self._session = None
        if error is not None:
            raise GovernanceFindingReviewDependencyError(
                "Governance Intelligence finding review audit could not be committed"
            ) from error

    async def rollback(self) -> None:
        """Roll back and close an incomplete review receipt transaction."""
        session = self._session
        if session is None:
            return
        error: SQLAlchemyError | None = None
        try:
            await session.rollback()
        except SQLAlchemyError as exc:
            error = exc
        try:
            await session.close()
        except SQLAlchemyError as exc:
            error = error or exc
        finally:
            self._session = None
        if error is not None:
            raise GovernanceFindingReviewDependencyError(
                "Governance Intelligence finding review audit could not be rolled back"
            ) from error

    async def _discard_session(self, session: AsyncSession) -> None:
        """Best-effort cleanup after append fails before application rollback."""
        with suppress(SQLAlchemyError):
            await session.rollback()
        with suppress(SQLAlchemyError):
            await session.close()
        self._session = None
