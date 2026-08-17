"""Non-authoritative review boundary for Governance Intelligence findings."""

import asyncio
import hashlib
import json
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from governance_schemas import (
    GovernanceFindingEnvelope,
    GovernanceFindingType,
)


class GovernanceFindingReviewDependencyError(RuntimeError):
    """Report an unavailable authorization or audit dependency without details."""


class GovernanceFindingReviewFailure(StrEnum):
    """Content-free failures exposed by advisory finding review."""

    INVALID_REQUEST = "invalid_request"
    FORBIDDEN = "forbidden"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"


_FAILURE_MESSAGES: dict[GovernanceFindingReviewFailure, str] = {
    GovernanceFindingReviewFailure.INVALID_REQUEST: (
        "Governance Intelligence finding review request is invalid"
    ),
    GovernanceFindingReviewFailure.FORBIDDEN: (
        "Governance Intelligence finding review is not permitted"
    ),
    GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE: (
        "Governance Intelligence finding review is temporarily unavailable"
    ),
}


class GovernanceFindingReviewError(RuntimeError):
    """Expose one bounded review failure without finding or dependency content."""

    def __init__(self, reason: GovernanceFindingReviewFailure) -> None:
        """Initialize the stable public failure category."""
        super().__init__(_FAILURE_MESSAGES[reason])
        self.reason = reason


class GovernanceFindingReviewDisposition(StrEnum):
    """Closed non-authoritative outcomes for one advisory finding review."""

    ACCEPTED_FOR_CONSIDERATION = "accepted_for_consideration"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass(frozen=True, slots=True)
class GovernanceFindingReviewAccess:
    """Authenticated content-free context used to authorize one review."""

    actor_id: str
    subject_id: str
    correlation_id: str
    is_admin: bool = False

    def __post_init__(self) -> None:
        """Reject absent or unbounded identifiers before invoking a port."""
        for value in (self.actor_id, self.subject_id, self.correlation_id):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 200
                or value != value.strip()
                or any(character.isspace() or not character.isprintable() for character in value)
            ):
                raise ValueError(
                    "Finding review identifiers must contain 1 to 200 printable characters"
                )
        if not isinstance(self.is_admin, bool):
            raise ValueError("Finding review administrator access must be boolean")


@dataclass(frozen=True, slots=True)
class GovernanceFindingReviewReceipt:
    """Immutable receipt for a review disposition that grants no governance authority."""

    review_id: UUID
    finding_id: UUID
    finding_type: GovernanceFindingType
    agent_run_id: UUID
    candidate_digest: str
    subject_id: str
    correlation_id: str
    disposition: GovernanceFindingReviewDisposition
    reviewed_by: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class GovernanceFindingReviewAuditRecord:
    """Content-minimized facts permitted in the durable audit chain."""

    review_id: UUID
    schema_version: str
    finding_id: UUID
    finding_type: GovernanceFindingType
    agent_run_id: UUID
    candidate_digest: str
    subject_id: str
    correlation_id: str
    disposition: GovernanceFindingReviewDisposition
    administrator_access: bool
    reviewed_at: datetime


class GovernanceFindingReviewAuthorizerPort(Protocol):
    """Decide whether an actor may review a finding for one governed subject."""

    async def can_review(
        self,
        *,
        actor_id: str,
        subject_id: str,
        finding_type: GovernanceFindingType,
        is_admin: bool,
    ) -> bool:
        """Return only an authorization decision over content-free identifiers."""
        ...


class GovernanceFindingReviewAuditPort(Protocol):
    """Append one minimized review receipt without finding content."""

    async def append(
        self,
        *,
        actor_id: str,
        record: GovernanceFindingReviewAuditRecord,
    ) -> None:
        """Append a review receipt without committing the transaction."""
        ...


class GovernanceFindingReviewTransactionPort(Protocol):
    """Commit or roll back one advisory review audit receipt."""

    async def commit(self) -> None:
        """Commit the pending review receipt."""
        ...

    async def rollback(self) -> None:
        """Discard an incomplete review receipt."""
        ...


type Clock = Callable[[], datetime]
type ReviewIdFactory = Callable[[], UUID]


class ReviewGovernanceFinding:
    """Authorize and record a non-authoritative disposition for one finding."""

    def __init__(
        self,
        authorizer: GovernanceFindingReviewAuthorizerPort,
        audit: GovernanceFindingReviewAuditPort,
        transaction: GovernanceFindingReviewTransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: ReviewIdFactory | None = None,
    ) -> None:
        """Initialize consumer-owned authorization and minimized audit ports."""
        self._authorizer = authorizer
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or uuid4

    async def execute(
        self,
        *,
        finding: GovernanceFindingEnvelope,
        disposition: GovernanceFindingReviewDisposition,
        access: GovernanceFindingReviewAccess,
    ) -> GovernanceFindingReviewReceipt:
        """Return a receipt only after authorization and durable minimized audit."""
        finding, disposition = self._validate_request(finding, disposition, access)
        await self._authorize(finding.candidate.finding_type, access)
        reviewed_at = self._reviewed_at()
        review_id = self._review_id()
        candidate = finding.candidate
        candidate_digest = _candidate_digest(finding)
        receipt = GovernanceFindingReviewReceipt(
            review_id=review_id,
            finding_id=candidate.finding_id,
            finding_type=candidate.finding_type,
            agent_run_id=candidate.provenance.agent_run_id,
            candidate_digest=candidate_digest,
            subject_id=access.subject_id,
            correlation_id=access.correlation_id,
            disposition=disposition,
            reviewed_by=access.actor_id,
            reviewed_at=reviewed_at,
        )
        await self._append_audit(
            actor_id=access.actor_id,
            record=GovernanceFindingReviewAuditRecord(
                review_id=review_id,
                schema_version=finding.schema_version,
                finding_id=candidate.finding_id,
                finding_type=candidate.finding_type,
                agent_run_id=candidate.provenance.agent_run_id,
                candidate_digest=candidate_digest,
                subject_id=access.subject_id,
                correlation_id=access.correlation_id,
                disposition=disposition,
                administrator_access=access.is_admin,
                reviewed_at=reviewed_at,
            ),
        )
        return receipt

    @staticmethod
    def _validate_request(
        finding: object,
        disposition: object,
        access: object,
    ) -> tuple[GovernanceFindingEnvelope, GovernanceFindingReviewDisposition]:
        """Revalidate untrusted input and require matching trace context."""
        if not isinstance(finding, GovernanceFindingEnvelope):
            raise GovernanceFindingReviewError(GovernanceFindingReviewFailure.INVALID_REQUEST)
        if not isinstance(disposition, GovernanceFindingReviewDisposition):
            raise GovernanceFindingReviewError(GovernanceFindingReviewFailure.INVALID_REQUEST)
        if not isinstance(access, GovernanceFindingReviewAccess):
            raise GovernanceFindingReviewError(GovernanceFindingReviewFailure.INVALID_REQUEST)
        try:
            validated = GovernanceFindingEnvelope.model_validate(finding.model_dump(mode="python"))
        except ValueError as exc:
            raise GovernanceFindingReviewError(
                GovernanceFindingReviewFailure.INVALID_REQUEST
            ) from exc
        if validated.candidate.provenance.correlation_id != access.correlation_id:
            raise GovernanceFindingReviewError(GovernanceFindingReviewFailure.INVALID_REQUEST)
        return validated, disposition

    async def _authorize(
        self,
        finding_type: GovernanceFindingType,
        access: GovernanceFindingReviewAccess,
    ) -> None:
        """Fail closed on denial or an unavailable authorization dependency."""
        try:
            allowed = await self._authorizer.can_review(
                actor_id=access.actor_id,
                subject_id=access.subject_id,
                finding_type=finding_type,
                is_admin=access.is_admin,
            )
        except GovernanceFindingReviewDependencyError as exc:
            raise GovernanceFindingReviewError(
                GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
            ) from exc
        if allowed is not True:
            raise GovernanceFindingReviewError(GovernanceFindingReviewFailure.FORBIDDEN)

    def _reviewed_at(self) -> datetime:
        """Return a UTC review time or fail closed on an invalid clock value."""
        try:
            reviewed_at = self._clock()
        except Exception as exc:
            raise GovernanceFindingReviewError(
                GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
            ) from exc
        if (
            not isinstance(reviewed_at, datetime)
            or reviewed_at.tzinfo is None
            or reviewed_at.utcoffset() is None
            or reviewed_at.utcoffset() != UTC.utcoffset(reviewed_at)
        ):
            raise GovernanceFindingReviewError(
                GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
            )
        return reviewed_at.astimezone(UTC)

    def _review_id(self) -> UUID:
        """Return one non-nil review identifier from the configured factory."""
        try:
            review_id = self._id_factory()
        except Exception as exc:
            raise GovernanceFindingReviewError(
                GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
            ) from exc
        if not isinstance(review_id, UUID) or review_id.int == 0:
            raise GovernanceFindingReviewError(
                GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
            )
        return review_id

    async def _append_audit(
        self,
        *,
        actor_id: str,
        record: GovernanceFindingReviewAuditRecord,
    ) -> None:
        """Commit the receipt before release and clean up interrupted transactions."""
        try:
            await self._audit.append(actor_id=actor_id, record=record)
            await self._transaction.commit()
        except GovernanceFindingReviewDependencyError as exc:
            with suppress(GovernanceFindingReviewDependencyError):
                await self._transaction.rollback()
            raise GovernanceFindingReviewError(
                GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
            ) from exc
        except asyncio.CancelledError:
            with suppress(GovernanceFindingReviewDependencyError):
                await self._transaction.rollback()
            raise


def _candidate_digest(finding: GovernanceFindingEnvelope) -> str:
    """Bind a receipt to the complete envelope without retaining its content."""
    canonical = json.dumps(
        finding.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
