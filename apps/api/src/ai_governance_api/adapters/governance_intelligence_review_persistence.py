"""SQLAlchemy unit of work for durable advisory finding review receipts."""

from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

from governance_schemas import GovernanceFindingType
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_governance_api.application.governance_intelligence_review import (
    GovernanceFindingReviewAuditRecord,
    GovernanceFindingReviewDependencyError,
    GovernanceFindingReviewDisposition,
    GovernanceFindingReviewIntegrityError,
    GovernanceFindingReviewReceipt,
    GovernanceFindingReviewWriteConflict,
)
from ai_governance_api.audit import append_audit_event
from ai_governance_api.models import GovernanceFindingReviewReceiptEntry


class SqlAlchemyGovernanceFindingReviewUnitOfWork:
    """Persist receipt and audit evidence in one short-lived transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the unit without opening a database connection."""
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def get_by_request_id(
        self,
        request_id: UUID,
    ) -> GovernanceFindingReviewReceipt | None:
        """Load one minimized receipt by its durable idempotency identity."""
        session = self._get_session()
        try:
            entity = await session.scalar(
                select(GovernanceFindingReviewReceiptEntry).where(
                    GovernanceFindingReviewReceiptEntry.request_id == str(request_id)
                )
            )
        except SQLAlchemyError as exc:
            raise GovernanceFindingReviewDependencyError(
                "Governance Intelligence finding review receipt could not be loaded"
            ) from exc
        if entity is None:
            return None
        try:
            return _to_receipt(entity)
        except (TypeError, ValueError) as exc:
            raise GovernanceFindingReviewIntegrityError(
                "Governance Intelligence finding review receipt is invalid"
            ) from exc

    async def save(self, receipt: GovernanceFindingReviewReceipt) -> None:
        """Insert one append-only minimized receipt and detect request collisions."""
        session = self._get_session()
        session.add(_to_entry(receipt))
        try:
            await session.flush()
        except IntegrityError as exc:
            raise GovernanceFindingReviewWriteConflict(
                "Governance Intelligence finding review request already exists"
            ) from exc
        except SQLAlchemyError as exc:
            raise GovernanceFindingReviewDependencyError(
                "Governance Intelligence finding review receipt could not be persisted"
            ) from exc

    async def append(
        self,
        *,
        actor_id: str,
        record: GovernanceFindingReviewAuditRecord,
    ) -> None:
        """Append the minimized receipt binding inside the shared transaction."""
        session = self._get_session()
        payload: dict[str, object] = {
            "request_id": str(record.request_id),
            "schema_version": record.schema_version,
            "finding_schema_version": record.finding_schema_version,
            "finding_id": str(record.finding_id),
            "finding_type": record.finding_type.value,
            "agent_run_id": str(record.agent_run_id),
            "candidate_digest": record.candidate_digest,
            "subject_id": record.subject_id,
            "correlation_id": record.correlation_id,
            "disposition": record.disposition.value,
            "administrator_access": record.administrator_access,
            "reviewed_at": record.reviewed_at.isoformat(),
            "receipt_digest": record.receipt_digest,
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
            raise GovernanceFindingReviewDependencyError(
                "Governance Intelligence finding review audit could not be appended"
            ) from exc

    async def commit(self) -> None:
        """Commit receipt and audit together, then release the connection."""
        session = self._session
        if session is None:
            raise GovernanceFindingReviewDependencyError(
                "No finding review persistence transaction is active"
            )
        conflict: IntegrityError | None = None
        error: SQLAlchemyError | None = None
        try:
            await session.commit()
        except IntegrityError as exc:
            conflict = exc
            with suppress(SQLAlchemyError):
                await session.rollback()
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
                "Governance Intelligence finding review transaction could not be committed"
            ) from error
        if conflict is not None:
            raise GovernanceFindingReviewWriteConflict(
                "Governance Intelligence finding review request already exists"
            ) from conflict

    async def rollback(self) -> None:
        """Roll back incomplete receipt and audit work, then release the connection."""
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
                "Governance Intelligence finding review transaction could not be rolled back"
            ) from error

    def _get_session(self) -> AsyncSession:
        """Return the current session or lazily open one unit-of-work session."""
        if self._session is None:
            self._session = self._session_factory()
        return self._session


def _to_entry(receipt: GovernanceFindingReviewReceipt) -> GovernanceFindingReviewReceiptEntry:
    """Map a validated minimized receipt to append-only persistence."""
    return GovernanceFindingReviewReceiptEntry(
        review_id=str(receipt.review_id),
        request_id=str(receipt.request_id),
        schema_version=receipt.schema_version,
        finding_schema_version=receipt.finding_schema_version,
        finding_id=str(receipt.finding_id),
        finding_type=receipt.finding_type.value,
        agent_run_id=str(receipt.agent_run_id),
        candidate_digest=receipt.candidate_digest,
        subject_id=receipt.subject_id,
        correlation_id=receipt.correlation_id,
        disposition=receipt.disposition.value,
        reviewed_by=receipt.reviewed_by,
        administrator_access=receipt.administrator_access,
        reviewed_at=receipt.reviewed_at,
        receipt_digest=receipt.receipt_digest,
        version=receipt.version,
    )


def _to_receipt(
    entity: GovernanceFindingReviewReceiptEntry,
) -> GovernanceFindingReviewReceipt:
    """Reconstruct and validate minimized receipt evidence from persistence."""
    return GovernanceFindingReviewReceipt(
        request_id=_canonical_uuid(entity.request_id),
        review_id=_canonical_uuid(entity.review_id),
        schema_version=entity.schema_version,
        finding_schema_version=entity.finding_schema_version,
        finding_id=_canonical_uuid(entity.finding_id),
        finding_type=GovernanceFindingType(entity.finding_type),
        agent_run_id=_canonical_uuid(entity.agent_run_id),
        candidate_digest=entity.candidate_digest,
        subject_id=entity.subject_id,
        correlation_id=entity.correlation_id,
        disposition=GovernanceFindingReviewDisposition(entity.disposition),
        reviewed_by=entity.reviewed_by,
        administrator_access=entity.administrator_access,
        reviewed_at=_as_utc(entity.reviewed_at),
        receipt_digest=entity.receipt_digest,
        version=entity.version,
    )


def _canonical_uuid(value: str) -> UUID:
    """Return one canonical non-nil UUID or reject persisted aliases."""
    parsed = UUID(value)
    if parsed.int == 0 or str(parsed) != value:
        raise ValueError("Persisted finding review UUID is not canonical")
    return parsed


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive timestamps before receipt validation."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
