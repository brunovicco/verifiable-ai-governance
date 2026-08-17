"""SQLAlchemy audit adapters for governed advisory analysis."""

from contextlib import suppress

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_governance_api.application.governance_intelligence import (
    GovernanceIntelligenceAuditRecord,
    GovernanceIntelligenceDependencyError,
)
from ai_governance_api.audit import append_audit_event


class SqlAlchemyGovernanceIntelligenceAudit:
    """Append and commit each stage in a request-scoped, short-lived transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize a dedicated audit unit of work without opening a connection."""
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def append(
        self,
        *,
        actor_id: str,
        record: GovernanceIntelligenceAuditRecord,
    ) -> None:
        """Append identities and outcomes without source bytes or finding statements."""
        if self._session is not None:
            raise GovernanceIntelligenceDependencyError(
                "A Governance Intelligence audit transaction is already active"
            )
        session = self._session_factory()
        self._session = session
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
            await self._discard_session(session)
            raise GovernanceIntelligenceDependencyError(
                "Governance Intelligence audit could not be appended"
            ) from exc

    async def commit(self) -> None:
        """Commit an audit stage or expose a content-free dependency failure."""
        session = self._session
        if session is None:
            raise GovernanceIntelligenceDependencyError(
                "No Governance Intelligence audit transaction is active"
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
            raise GovernanceIntelligenceDependencyError(
                "Governance Intelligence audit transaction could not be committed"
            ) from error

    async def rollback(self) -> None:
        """Roll back an incomplete audit stage after a persistence failure."""
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
                "Governance Intelligence audit transaction could not be rolled back"
            ) from error

    async def _discard_session(self, session: AsyncSession) -> None:
        """Best-effort cleanup after append fails before the application can roll back."""
        with suppress(SQLAlchemyError):
            await session.rollback()
        with suppress(SQLAlchemyError):
            await session.close()
        self._session = None
