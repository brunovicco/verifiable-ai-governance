"""Non-authoritative review boundary for Governance Intelligence findings."""

import asyncio
import hashlib
import hmac
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

from ai_governance_api.application.governance_intelligence_integrity import (
    governance_finding_envelope_digest,
)

GOVERNANCE_FINDING_REVIEW_RECEIPT_SCHEMA_VERSION = "1.0"
_RECEIPT_VERSION = 1
_LOWERCASE_HEX = frozenset("0123456789abcdef")


class GovernanceFindingReviewDependencyError(RuntimeError):
    """Report an unavailable authorization or persistence dependency without details."""


class GovernanceFindingReviewWriteConflict(RuntimeError):
    """Report a concurrent durable request collision without database details."""


class GovernanceFindingReviewIntegrityError(RuntimeError):
    """Report invalid persisted receipt evidence without exposing stored values."""


class GovernanceFindingReviewFailure(StrEnum):
    """Content-free failures exposed by advisory finding review."""

    INVALID_REQUEST = "invalid_request"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"


_FAILURE_MESSAGES: dict[GovernanceFindingReviewFailure, str] = {
    GovernanceFindingReviewFailure.INVALID_REQUEST: (
        "Governance Intelligence finding review request is invalid"
    ),
    GovernanceFindingReviewFailure.FORBIDDEN: (
        "Governance Intelligence finding review is not permitted"
    ),
    GovernanceFindingReviewFailure.CONFLICT: (
        "Governance Intelligence finding review request conflicts with existing evidence"
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
            if not _bounded_identifier(value):
                raise ValueError(
                    "Finding review identifiers must contain 1 to 200 printable characters"
                )
        if not isinstance(self.is_admin, bool):
            raise ValueError("Finding review administrator access must be boolean")


@dataclass(frozen=True, slots=True)
class GovernanceFindingReviewReceipt:
    """Immutable content-minimized evidence for one advisory review request."""

    request_id: UUID
    review_id: UUID
    schema_version: str
    finding_schema_version: str
    finding_id: UUID
    finding_type: GovernanceFindingType
    agent_run_id: UUID
    candidate_digest: str
    subject_id: str
    correlation_id: str
    disposition: GovernanceFindingReviewDisposition
    reviewed_by: str
    administrator_access: bool
    reviewed_at: datetime
    receipt_digest: str
    version: int = _RECEIPT_VERSION

    def __post_init__(self) -> None:
        """Reject malformed or non-canonical durable receipt evidence."""
        for identifier in (
            self.request_id,
            self.review_id,
            self.finding_id,
            self.agent_run_id,
        ):
            if not isinstance(identifier, UUID) or identifier.int == 0:
                raise ValueError("Finding review receipt UUIDs must be non-nil")
        if self.schema_version != GOVERNANCE_FINDING_REVIEW_RECEIPT_SCHEMA_VERSION:
            raise ValueError("Finding review receipt schema version is unsupported")
        if self.finding_schema_version != "1.0":
            raise ValueError("Finding review envelope schema version is unsupported")
        if not isinstance(self.finding_type, GovernanceFindingType):
            raise ValueError("Finding review type is unsupported")
        if not isinstance(self.disposition, GovernanceFindingReviewDisposition):
            raise ValueError("Finding review disposition is unsupported")
        for value in (self.subject_id, self.correlation_id, self.reviewed_by):
            if not _bounded_identifier(value):
                raise ValueError("Finding review receipt identifiers are invalid")
        if not isinstance(self.administrator_access, bool):
            raise ValueError("Finding review administrator access must be boolean")
        if not _utc_datetime(self.reviewed_at):
            raise ValueError("Finding review receipt time must be UTC")
        if not _lowercase_sha256(self.candidate_digest) or not _lowercase_sha256(
            self.receipt_digest
        ):
            raise ValueError("Finding review receipt digests are invalid")
        if self.version != _RECEIPT_VERSION:
            raise ValueError("Finding review receipt version is unsupported")


@dataclass(frozen=True, slots=True)
class GovernanceFindingReviewAuditRecord:
    """Content-minimized receipt facts permitted in the durable audit chain."""

    request_id: UUID
    review_id: UUID
    schema_version: str
    finding_schema_version: str
    finding_id: UUID
    finding_type: GovernanceFindingType
    agent_run_id: UUID
    candidate_digest: str
    subject_id: str
    correlation_id: str
    disposition: GovernanceFindingReviewDisposition
    administrator_access: bool
    reviewed_at: datetime
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class _GovernanceFindingReviewBinding:
    """Content-free command facts bound to one idempotent request identity."""

    request_id: UUID
    finding_schema_version: str
    finding_id: UUID
    finding_type: GovernanceFindingType
    agent_run_id: UUID
    candidate_digest: str
    subject_id: str
    correlation_id: str
    disposition: GovernanceFindingReviewDisposition
    reviewed_by: str
    administrator_access: bool


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


class GovernanceFindingReleaseVerifierPort(Protocol):
    """Verify that an exact finding passed the governed GI-2 release boundary."""

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
        """Return only whether intact minimized release evidence matches exactly."""
        ...


class GovernanceFindingReviewStorePort(Protocol):
    """Persist and load minimized advisory review receipts by request identity."""

    async def get_by_request_id(
        self,
        request_id: UUID,
    ) -> GovernanceFindingReviewReceipt | None:
        """Return durable receipt evidence for an idempotent request."""
        ...

    async def save(self, receipt: GovernanceFindingReviewReceipt) -> None:
        """Persist one append-only receipt without committing."""
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
    """Commit or roll back receipt evidence and its audit event atomically."""

    async def commit(self) -> None:
        """Commit the pending review receipt and audit evidence."""
        ...

    async def rollback(self) -> None:
        """Discard an incomplete review transaction."""
        ...


type Clock = Callable[[], datetime]
type ReviewIdFactory = Callable[[], UUID]


class ReviewGovernanceFinding:
    """Authorize, persist, and idempotently replay one advisory finding review."""

    def __init__(
        self,
        authorizer: GovernanceFindingReviewAuthorizerPort,
        release_verifier: GovernanceFindingReleaseVerifierPort,
        store: GovernanceFindingReviewStorePort,
        audit: GovernanceFindingReviewAuditPort,
        transaction: GovernanceFindingReviewTransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: ReviewIdFactory | None = None,
    ) -> None:
        """Initialize subject authorization and one durable receipt unit of work."""
        self._authorizer = authorizer
        self._release_verifier = release_verifier
        self._store = store
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or uuid4

    async def execute(
        self,
        *,
        request_id: UUID,
        finding: GovernanceFindingEnvelope,
        disposition: GovernanceFindingReviewDisposition,
        access: GovernanceFindingReviewAccess,
    ) -> GovernanceFindingReviewReceipt:
        """Create or replay a receipt only after current authorization succeeds."""
        request_id, finding, disposition = self._validate_request(
            request_id,
            finding,
            disposition,
            access,
        )
        await self._authorize(finding.candidate.finding_type, access)
        binding = self._binding(request_id, finding, disposition, access)
        try:
            await self._require_released(binding)
            return await self._persist_or_replay(binding)
        except GovernanceFindingReviewWriteConflict:
            await self._rollback_quietly()
            return await self._recover_concurrent_replay(binding)
        except GovernanceFindingReviewIntegrityError as exc:
            await self._rollback_quietly()
            raise GovernanceFindingReviewError(GovernanceFindingReviewFailure.CONFLICT) from exc
        except GovernanceFindingReviewDependencyError as exc:
            await self._rollback_quietly()
            raise GovernanceFindingReviewError(
                GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
            ) from exc
        except GovernanceFindingReviewError:
            await self._rollback_quietly()
            raise
        except asyncio.CancelledError:
            await self._rollback_quietly()
            raise

    @staticmethod
    def _validate_request(
        request_id: object,
        finding: object,
        disposition: object,
        access: object,
    ) -> tuple[UUID, GovernanceFindingEnvelope, GovernanceFindingReviewDisposition]:
        """Revalidate idempotency identity, untrusted input, and trace context."""
        if not isinstance(request_id, UUID) or request_id.int == 0:
            raise GovernanceFindingReviewError(GovernanceFindingReviewFailure.INVALID_REQUEST)
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
        return request_id, validated, disposition

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

    @staticmethod
    def _binding(
        request_id: UUID,
        finding: GovernanceFindingEnvelope,
        disposition: GovernanceFindingReviewDisposition,
        access: GovernanceFindingReviewAccess,
    ) -> _GovernanceFindingReviewBinding:
        candidate = finding.candidate
        return _GovernanceFindingReviewBinding(
            request_id=request_id,
            finding_schema_version=finding.schema_version,
            finding_id=candidate.finding_id,
            finding_type=candidate.finding_type,
            agent_run_id=candidate.provenance.agent_run_id,
            candidate_digest=governance_finding_envelope_digest(finding),
            subject_id=access.subject_id,
            correlation_id=access.correlation_id,
            disposition=disposition,
            reviewed_by=access.actor_id,
            administrator_access=access.is_admin,
        )

    async def _require_released(self, binding: _GovernanceFindingReviewBinding) -> None:
        """Fail closed unless exact intact GI-2 release evidence exists."""
        released = await self._release_verifier.was_released(
            finding_schema_version=binding.finding_schema_version,
            finding_id=binding.finding_id,
            finding_type=binding.finding_type,
            agent_run_id=binding.agent_run_id,
            candidate_digest=binding.candidate_digest,
            subject_id=binding.subject_id,
            correlation_id=binding.correlation_id,
        )
        if released is not True:
            raise GovernanceFindingReviewError(GovernanceFindingReviewFailure.INVALID_REQUEST)

    async def _persist_or_replay(
        self,
        binding: _GovernanceFindingReviewBinding,
    ) -> GovernanceFindingReviewReceipt:
        existing = await self._store.get_by_request_id(binding.request_id)
        if existing is not None:
            self._require_idempotent_replay(existing, binding)
            await self._transaction.commit()
            return existing

        receipt = self._new_receipt(binding)
        await self._store.save(receipt)
        await self._audit.append(
            actor_id=receipt.reviewed_by,
            record=_audit_record(receipt),
        )
        await self._transaction.commit()
        return receipt

    async def _recover_concurrent_replay(
        self,
        binding: _GovernanceFindingReviewBinding,
    ) -> GovernanceFindingReviewReceipt:
        """Reload a unique-constraint winner once and require an exact binding."""
        try:
            existing = await self._store.get_by_request_id(binding.request_id)
            if existing is None:
                raise GovernanceFindingReviewError(GovernanceFindingReviewFailure.CONFLICT)
            self._require_idempotent_replay(existing, binding)
            await self._transaction.commit()
            return existing
        except GovernanceFindingReviewIntegrityError as exc:
            await self._rollback_quietly()
            raise GovernanceFindingReviewError(GovernanceFindingReviewFailure.CONFLICT) from exc
        except GovernanceFindingReviewDependencyError as exc:
            await self._rollback_quietly()
            raise GovernanceFindingReviewError(
                GovernanceFindingReviewFailure.DEPENDENCY_UNAVAILABLE
            ) from exc
        except GovernanceFindingReviewError:
            await self._rollback_quietly()
            raise
        except asyncio.CancelledError:
            await self._rollback_quietly()
            raise

    def _new_receipt(
        self,
        binding: _GovernanceFindingReviewBinding,
    ) -> GovernanceFindingReviewReceipt:
        reviewed_at = self._reviewed_at()
        review_id = self._review_id()
        receipt_digest = _receipt_digest(
            binding=binding,
            review_id=review_id,
            reviewed_at=reviewed_at,
        )
        return GovernanceFindingReviewReceipt(
            request_id=binding.request_id,
            review_id=review_id,
            schema_version=GOVERNANCE_FINDING_REVIEW_RECEIPT_SCHEMA_VERSION,
            finding_schema_version=binding.finding_schema_version,
            finding_id=binding.finding_id,
            finding_type=binding.finding_type,
            agent_run_id=binding.agent_run_id,
            candidate_digest=binding.candidate_digest,
            subject_id=binding.subject_id,
            correlation_id=binding.correlation_id,
            disposition=binding.disposition,
            reviewed_by=binding.reviewed_by,
            administrator_access=binding.administrator_access,
            reviewed_at=reviewed_at,
            receipt_digest=receipt_digest,
        )

    @staticmethod
    def _require_idempotent_replay(
        receipt: GovernanceFindingReviewReceipt,
        binding: _GovernanceFindingReviewBinding,
    ) -> None:
        try:
            receipt_binding = _binding_from_receipt(receipt)
            expected_digest = _receipt_digest(
                binding=receipt_binding,
                review_id=receipt.review_id,
                reviewed_at=receipt.reviewed_at,
            )
        except ValueError as exc:
            raise GovernanceFindingReviewIntegrityError(
                "Stored finding review receipt is invalid"
            ) from exc
        if not hmac.compare_digest(receipt.receipt_digest, expected_digest):
            raise GovernanceFindingReviewIntegrityError(
                "Stored finding review receipt binding is invalid"
            )
        if receipt_binding != binding:
            raise GovernanceFindingReviewError(GovernanceFindingReviewFailure.CONFLICT)

    def _reviewed_at(self) -> datetime:
        """Return a UTC review time or fail closed on an invalid clock value."""
        try:
            reviewed_at = self._clock()
        except Exception as exc:
            raise GovernanceFindingReviewDependencyError(
                "Finding review clock is unavailable"
            ) from exc
        if not _utc_datetime(reviewed_at):
            raise GovernanceFindingReviewDependencyError("Finding review clock is invalid")
        return reviewed_at.astimezone(UTC)

    def _review_id(self) -> UUID:
        """Return one non-nil review identifier from the configured factory."""
        try:
            review_id = self._id_factory()
        except Exception as exc:
            raise GovernanceFindingReviewDependencyError(
                "Finding review identity generation is unavailable"
            ) from exc
        if not isinstance(review_id, UUID) or review_id.int == 0:
            raise GovernanceFindingReviewDependencyError("Finding review identity is invalid")
        return review_id

    async def _rollback_quietly(self) -> None:
        """Best-effort cleanup without replacing the bounded primary failure."""
        with suppress(GovernanceFindingReviewDependencyError):
            await self._transaction.rollback()


def _receipt_digest(
    *,
    binding: _GovernanceFindingReviewBinding,
    review_id: UUID,
    reviewed_at: datetime,
) -> str:
    """Bind immutable request, review, actor, and candidate facts to one receipt."""
    canonical = json.dumps(
        {
            "request_id": str(binding.request_id),
            "review_id": str(review_id),
            "schema_version": GOVERNANCE_FINDING_REVIEW_RECEIPT_SCHEMA_VERSION,
            "finding_schema_version": binding.finding_schema_version,
            "finding_id": str(binding.finding_id),
            "finding_type": binding.finding_type.value,
            "agent_run_id": str(binding.agent_run_id),
            "candidate_digest": binding.candidate_digest,
            "subject_id": binding.subject_id,
            "correlation_id": binding.correlation_id,
            "disposition": binding.disposition.value,
            "reviewed_by": binding.reviewed_by,
            "administrator_access": binding.administrator_access,
            "reviewed_at": reviewed_at.isoformat(),
            "version": _RECEIPT_VERSION,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _binding_from_receipt(
    receipt: GovernanceFindingReviewReceipt,
) -> _GovernanceFindingReviewBinding:
    """Project stored receipt evidence into the replay comparison boundary."""
    return _GovernanceFindingReviewBinding(
        request_id=receipt.request_id,
        finding_schema_version=receipt.finding_schema_version,
        finding_id=receipt.finding_id,
        finding_type=receipt.finding_type,
        agent_run_id=receipt.agent_run_id,
        candidate_digest=receipt.candidate_digest,
        subject_id=receipt.subject_id,
        correlation_id=receipt.correlation_id,
        disposition=receipt.disposition,
        reviewed_by=receipt.reviewed_by,
        administrator_access=receipt.administrator_access,
    )


def _audit_record(receipt: GovernanceFindingReviewReceipt) -> GovernanceFindingReviewAuditRecord:
    """Project one validated receipt into minimized audit facts."""
    return GovernanceFindingReviewAuditRecord(
        request_id=receipt.request_id,
        review_id=receipt.review_id,
        schema_version=receipt.schema_version,
        finding_schema_version=receipt.finding_schema_version,
        finding_id=receipt.finding_id,
        finding_type=receipt.finding_type,
        agent_run_id=receipt.agent_run_id,
        candidate_digest=receipt.candidate_digest,
        subject_id=receipt.subject_id,
        correlation_id=receipt.correlation_id,
        disposition=receipt.disposition,
        administrator_access=receipt.administrator_access,
        reviewed_at=receipt.reviewed_at,
        receipt_digest=receipt.receipt_digest,
    )


def _bounded_identifier(value: object) -> bool:
    """Return whether a value is one bounded printable identity without whitespace."""
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 200
        and value == value.strip()
        and all(character.isprintable() and not character.isspace() for character in value)
    )


def _utc_datetime(value: object) -> bool:
    """Return whether a value is a timezone-aware UTC datetime."""
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
        and value.utcoffset() == UTC.utcoffset(value)
    )


def _lowercase_sha256(value: object) -> bool:
    """Return whether a value is one canonical lowercase SHA-256 digest."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _LOWERCASE_HEX for character in value)
    )
