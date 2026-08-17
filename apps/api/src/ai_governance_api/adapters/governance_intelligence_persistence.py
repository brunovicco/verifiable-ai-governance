"""SQLAlchemy persistence for governed analysis releases and audit stages."""

import hmac
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

from governance_schemas import GovernanceFindingType
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_governance_api.application.governance_intelligence import (
    GovernanceIntelligenceAuditRecord,
    GovernanceIntelligenceDependencyError,
    GovernanceIntelligenceFindingRelease,
    GovernanceIntelligenceReleaseConflict,
)
from ai_governance_api.application.governance_intelligence_review import (
    GovernanceFindingReviewDependencyError,
)
from ai_governance_api.audit import append_audit_event
from ai_governance_api.models import GovernanceIntelligenceFindingReleaseEntry


class SqlAlchemyGovernanceIntelligenceUnitOfWork:
    """Persist terminal releases and every analysis audit stage transactionally."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the unit without opening a database connection."""
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def save_releases(
        self,
        releases: tuple[GovernanceIntelligenceFindingRelease, ...],
    ) -> None:
        """Flush one complete minimized release set without committing."""
        if not releases:
            return
        session = self._get_session()
        session.add_all(_to_entry(release) for release in releases)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise GovernanceIntelligenceReleaseConflict(
                "Governance Intelligence finding identity is already released"
            ) from exc
        except SQLAlchemyError as exc:
            raise GovernanceIntelligenceDependencyError(
                "Governance Intelligence releases could not be persisted"
            ) from exc

    async def append(
        self,
        *,
        actor_id: str,
        record: GovernanceIntelligenceAuditRecord,
    ) -> None:
        """Append minimized analysis lifecycle evidence in the active transaction."""
        session = self._get_session()
        payload: dict[str, object] = {
            "stage": record.stage.value,
            "analysis_type": record.analysis_type.value,
            "subject_id": record.subject_id,
            "correlation_id": record.correlation_id,
            "administrator_access": record.administrator_access,
            "source_count": len(record.references),
            "sources": [
                {
                    "artifact_id": reference.artifact_id,
                    "version": reference.version,
                    "node_id": reference.node_id,
                    "section": reference.section,
                    "content_digest": reference.content_digest,
                }
                for reference in record.references
            ],
            "finding_count": len(record.findings),
            "findings": [
                {
                    "finding_id": finding.finding_id,
                    "finding_type": finding.finding_type.value,
                    "agent_run_id": finding.agent_run_id,
                    "release_id": finding.release_id,
                    "candidate_digest": finding.candidate_digest,
                    "release_digest": finding.release_digest,
                    "released_at": finding.released_at.isoformat(),
                }
                for finding in record.findings
            ],
        }
        if record.source_total_bytes is not None:
            payload["source_total_bytes"] = record.source_total_bytes
        if record.failure_reason is not None:
            payload["failure_reason"] = record.failure_reason
        try:
            await append_audit_event(
                session,
                actor_id=actor_id,
                action=f"governance_intelligence.{record.stage.value}",
                entity_type="governance_intelligence_analysis",
                entity_id=record.correlation_id,
                entity_version=record.sequence,
                payload=payload,
            )
        except SQLAlchemyError as exc:
            raise GovernanceIntelligenceDependencyError(
                "Governance Intelligence audit could not be appended"
            ) from exc

    async def commit(self) -> None:
        """Commit one audit stage and any terminal release set, then close."""
        session = self._session
        if session is None:
            raise GovernanceIntelligenceDependencyError(
                "No Governance Intelligence persistence transaction is active"
            )
        error: SQLAlchemyError | None = None
        conflict: IntegrityError | None = None
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
            raise GovernanceIntelligenceDependencyError(
                "Governance Intelligence transaction could not be committed"
            ) from error
        if conflict is not None:
            raise GovernanceIntelligenceReleaseConflict(
                "Governance Intelligence finding identity is already released"
            ) from conflict

    async def rollback(self) -> None:
        """Roll back an incomplete audit/release transaction, then close."""
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
            raise GovernanceIntelligenceDependencyError(
                "Governance Intelligence transaction could not be rolled back"
            ) from error

    def _get_session(self) -> AsyncSession:
        """Return the active stage session or lazily open one."""
        if self._session is None:
            self._session = self._session_factory()
        return self._session


class SqlAlchemyGovernanceFindingReleaseVerifier:
    """Verify exact minimized GI-2 release evidence for one GI-3 review."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the reader without opening a database connection."""
        self._session_factory = session_factory

    async def was_released(
        self,
        *,
        finding_schema_version: str,
        finding_id: UUID,
        finding_type: GovernanceFindingType,
        agent_run_id: UUID,
        candidate_digest: str,
        subject_id: str,
        correlation_id: str,
    ) -> bool:
        """Return true only for an intact release with the complete expected binding."""
        try:
            async with self._session_factory() as session:
                entity = await session.scalar(
                    select(GovernanceIntelligenceFindingReleaseEntry).where(
                        GovernanceIntelligenceFindingReleaseEntry.finding_id == str(finding_id)
                    )
                )
        except SQLAlchemyError as exc:
            raise GovernanceFindingReviewDependencyError(
                "Governance Intelligence release verification is unavailable"
            ) from exc
        if entity is None:
            return False
        try:
            release = _to_release(entity)
        except (TypeError, ValueError) as exc:
            raise GovernanceFindingReviewDependencyError(
                "Governance Intelligence release evidence is invalid"
            ) from exc
        if not release.has_valid_digest():
            raise GovernanceFindingReviewDependencyError(
                "Governance Intelligence release evidence failed integrity verification"
            )
        return (
            release.finding_schema_version == finding_schema_version
            and release.finding_id == finding_id
            and release.finding_type is finding_type
            and release.agent_run_id == agent_run_id
            and hmac.compare_digest(release.candidate_digest, candidate_digest)
            and release.subject_id == subject_id
            and release.correlation_id == correlation_id
        )


def _to_entry(
    release: GovernanceIntelligenceFindingRelease,
) -> GovernanceIntelligenceFindingReleaseEntry:
    """Map one validated release to append-only persistence."""
    return GovernanceIntelligenceFindingReleaseEntry(
        release_id=str(release.release_id),
        schema_version=release.schema_version,
        finding_schema_version=release.finding_schema_version,
        finding_id=str(release.finding_id),
        finding_type=release.finding_type.value,
        agent_run_id=str(release.agent_run_id),
        candidate_digest=release.candidate_digest,
        subject_id=release.subject_id,
        correlation_id=release.correlation_id,
        released_at=release.released_at,
        release_digest=release.release_digest,
        version=release.version,
    )


def _to_release(
    entity: GovernanceIntelligenceFindingReleaseEntry,
) -> GovernanceIntelligenceFindingRelease:
    """Reconstruct and validate minimized release evidence from persistence."""
    return GovernanceIntelligenceFindingRelease(
        release_id=_canonical_uuid(entity.release_id),
        schema_version=entity.schema_version,
        finding_schema_version=entity.finding_schema_version,
        finding_id=_canonical_uuid(entity.finding_id),
        finding_type=GovernanceFindingType(entity.finding_type),
        agent_run_id=_canonical_uuid(entity.agent_run_id),
        candidate_digest=entity.candidate_digest,
        subject_id=entity.subject_id,
        correlation_id=entity.correlation_id,
        released_at=_as_utc(entity.released_at),
        release_digest=entity.release_digest,
        version=entity.version,
    )


def _canonical_uuid(value: str) -> UUID:
    """Return one canonical non-nil UUID or reject persisted aliases."""
    parsed = UUID(value)
    if parsed.int == 0 or str(parsed) != value:
        raise ValueError("Persisted Governance Intelligence release UUID is not canonical")
    return parsed


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive timestamps before release validation."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
