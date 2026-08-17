"""Governed resolution and integrity verification for knowledge sources."""

import hashlib
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from governance_schemas import GovernanceSourceReference


class GovernanceKnowledgeDependencyError(RuntimeError):
    """Report an unavailable authorization or source-resolution dependency."""


class GovernanceKnowledgeFailure(StrEnum):
    """Bounded failure reasons exposed by governed knowledge resolution."""

    INVALID_REQUEST = "invalid_request"
    SOURCE_UNAVAILABLE = "source_unavailable"
    SOURCE_MISMATCH = "source_mismatch"
    INTEGRITY_MISMATCH = "integrity_mismatch"
    LIMIT_EXCEEDED = "limit_exceeded"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"


_FAILURE_MESSAGES: Mapping[GovernanceKnowledgeFailure, str] = {
    GovernanceKnowledgeFailure.INVALID_REQUEST: "Governance knowledge request is invalid",
    GovernanceKnowledgeFailure.SOURCE_UNAVAILABLE: "Governance knowledge source is unavailable",
    GovernanceKnowledgeFailure.SOURCE_MISMATCH: "Governance knowledge source identity is invalid",
    GovernanceKnowledgeFailure.INTEGRITY_MISMATCH: (
        "Governance knowledge source integrity verification failed"
    ),
    GovernanceKnowledgeFailure.LIMIT_EXCEEDED: "Governance knowledge resolution limit exceeded",
    GovernanceKnowledgeFailure.DEPENDENCY_UNAVAILABLE: (
        "Governance knowledge resolution is temporarily unavailable"
    ),
}
_CONTENT_TYPE_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$"
)
_VERIFIED_SOURCE_TOKEN = object()


class GovernanceKnowledgeResolutionError(RuntimeError):
    """Describe a content-minimized, fail-closed knowledge resolution failure."""

    def __init__(self, reason: GovernanceKnowledgeFailure) -> None:
        """Initialize the error without source identifiers, digests, or content."""
        super().__init__(_FAILURE_MESSAGES[reason])
        self.reason = reason


@dataclass(frozen=True, slots=True)
class GovernanceKnowledgeAccess:
    """Authenticated context used to authorize a source for one governed subject."""

    actor_id: str
    subject_id: str
    correlation_id: str

    def __post_init__(self) -> None:
        """Reject absent or unbounded access identifiers before port invocation."""
        for value in (self.actor_id, self.subject_id, self.correlation_id):
            if (
                not value
                or len(value) > 200
                or value != value.strip()
                or any(character.isspace() or not character.isprintable() for character in value)
            ):
                raise ValueError(
                    "Knowledge access identifiers must contain 1 to 200 printable characters"
                )


class GovernanceKnowledgeContent(Protocol):
    """Asynchronous bounded-read interface returned by source adapters."""

    async def read(self, size: int) -> bytes:
        """Read at most ``size`` bytes and return an empty value at EOF."""
        ...

    async def close(self) -> None:
        """Release the source even when verification fails."""
        ...


@dataclass(frozen=True, slots=True)
class ResolvedGovernanceKnowledgeSource:
    """Unverified source identity and stream returned by a resolver adapter."""

    artifact_id: str
    version: str
    content_type: str
    content: GovernanceKnowledgeContent = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True, init=False)
class VerifiedGovernanceKnowledgeSource:
    """Ephemeral source bytes released only after governed integrity verification."""

    reference: GovernanceSourceReference
    content_type: str
    size_bytes: int
    content: bytes = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        reference: GovernanceSourceReference,
        content_type: str,
        size_bytes: int,
        content: bytes,
        _verification_token: object | None = None,
    ) -> None:
        """Allow construction only from the deterministic verification gate."""
        if _verification_token is not _VERIFIED_SOURCE_TOKEN:
            raise TypeError("Verified knowledge sources must be created by the resolution gate")
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "size_bytes", size_bytes)
        object.__setattr__(self, "content", content)


class GovernanceKnowledgeAuthorizerPort(Protocol):
    """Consumer-owned authorization check for exact source references."""

    async def can_read(
        self,
        *,
        reference: GovernanceSourceReference,
        access: GovernanceKnowledgeAccess,
    ) -> bool:
        """Return whether the actor may resolve the exact source for the subject."""
        ...


class GovernanceKnowledgeResolverPort(Protocol):
    """Resolve exact versioned sources without interpreting their content."""

    async def resolve(
        self,
        *,
        reference: GovernanceSourceReference,
        access: GovernanceKnowledgeAccess,
    ) -> ResolvedGovernanceKnowledgeSource | None:
        """Return the source stream, or no result for unavailable references."""
        ...


@dataclass(frozen=True, slots=True)
class _VerifiedContent:
    """Cache verified bytes for repeated section references to one artifact version."""

    content_type: str
    size_bytes: int
    content: bytes = field(repr=False)


class ResolveGovernanceKnowledgeSources:
    """Authorize, resolve, bound, and verify knowledge sources before consumption."""

    _chunk_size = 64 * 1024

    def __init__(
        self,
        authorizer: GovernanceKnowledgeAuthorizerPort,
        resolver: GovernanceKnowledgeResolverPort,
        *,
        max_sources: int,
        max_source_bytes: int,
        max_total_bytes: int,
    ) -> None:
        """Initialize explicit limits and consumer-owned ports."""
        if min(max_sources, max_source_bytes, max_total_bytes) <= 0:
            raise ValueError("Governance knowledge limits must be positive")
        self._authorizer = authorizer
        self._resolver = resolver
        self._max_sources = max_sources
        self._max_source_bytes = max_source_bytes
        self._max_total_bytes = max_total_bytes

    async def execute(
        self,
        *,
        references: tuple[GovernanceSourceReference, ...],
        access: GovernanceKnowledgeAccess,
    ) -> tuple[VerifiedGovernanceKnowledgeSource, ...]:
        """Return sources only after the complete requested set verifies successfully."""
        self._validate_request(references)
        verified_by_identity: dict[tuple[str, str], _VerifiedContent] = {}
        results: list[VerifiedGovernanceKnowledgeSource] = []
        total_bytes = 0

        for reference in references:
            await self._authorize(reference, access)
            identity = (reference.artifact_id, reference.version)
            verified = verified_by_identity.get(identity)
            if verified is None:
                remaining_total_bytes = self._max_total_bytes - total_bytes
                if remaining_total_bytes <= 0:
                    raise GovernanceKnowledgeResolutionError(
                        GovernanceKnowledgeFailure.LIMIT_EXCEEDED
                    )
                resolved = await self._resolve(reference, access)
                verified = await self._verify(
                    reference,
                    resolved,
                    max_bytes=min(self._max_source_bytes, remaining_total_bytes),
                )
                total_bytes += verified.size_bytes
                verified_by_identity[identity] = verified
            results.append(
                VerifiedGovernanceKnowledgeSource(
                    reference=reference,
                    content_type=verified.content_type,
                    size_bytes=verified.size_bytes,
                    content=verified.content,
                    _verification_token=_VERIFIED_SOURCE_TOKEN,
                )
            )
        return tuple(results)

    def _validate_request(self, references: tuple[GovernanceSourceReference, ...]) -> None:
        """Reject empty, oversized, duplicate, or contradictory source requests."""
        if not references or len(references) > self._max_sources:
            raise GovernanceKnowledgeResolutionError(GovernanceKnowledgeFailure.LIMIT_EXCEEDED)

        seen_references: set[tuple[str, str, str | None, str | None, str]] = set()
        digest_by_identity: dict[tuple[str, str], str] = {}
        for reference in references:
            reference_key = (
                reference.artifact_id,
                reference.version,
                reference.node_id,
                reference.section,
                reference.content_digest,
            )
            if reference_key in seen_references:
                raise GovernanceKnowledgeResolutionError(
                    GovernanceKnowledgeFailure.INVALID_REQUEST
                )
            seen_references.add(reference_key)

            identity = (reference.artifact_id, reference.version)
            prior_digest = digest_by_identity.setdefault(identity, reference.content_digest)
            if not hmac.compare_digest(prior_digest, reference.content_digest):
                raise GovernanceKnowledgeResolutionError(
                    GovernanceKnowledgeFailure.INVALID_REQUEST
                )

    async def _authorize(
        self,
        reference: GovernanceSourceReference,
        access: GovernanceKnowledgeAccess,
    ) -> None:
        """Fail without resolving when exact-reference access is denied."""
        try:
            allowed = await self._authorizer.can_read(reference=reference, access=access)
        except GovernanceKnowledgeDependencyError as exc:
            raise GovernanceKnowledgeResolutionError(
                GovernanceKnowledgeFailure.DEPENDENCY_UNAVAILABLE
            ) from exc
        if allowed is not True:
            raise GovernanceKnowledgeResolutionError(
                GovernanceKnowledgeFailure.SOURCE_UNAVAILABLE
            )

    async def _resolve(
        self,
        reference: GovernanceSourceReference,
        access: GovernanceKnowledgeAccess,
    ) -> ResolvedGovernanceKnowledgeSource:
        """Resolve one authorized exact-version source or fail closed."""
        try:
            resolved = await self._resolver.resolve(reference=reference, access=access)
        except GovernanceKnowledgeDependencyError as exc:
            raise GovernanceKnowledgeResolutionError(
                GovernanceKnowledgeFailure.DEPENDENCY_UNAVAILABLE
            ) from exc
        if resolved is None:
            raise GovernanceKnowledgeResolutionError(
                GovernanceKnowledgeFailure.SOURCE_UNAVAILABLE
            )
        return resolved

    async def _verify(
        self,
        reference: GovernanceSourceReference,
        resolved: ResolvedGovernanceKnowledgeSource,
        *,
        max_bytes: int,
    ) -> _VerifiedContent:
        """Verify exact identity, safe metadata, size, and actual content digest."""
        try:
            if (
                resolved.artifact_id != reference.artifact_id
                or resolved.version != reference.version
                or not _valid_content_type(resolved.content_type)
            ):
                raise GovernanceKnowledgeResolutionError(
                    GovernanceKnowledgeFailure.SOURCE_MISMATCH
                )
            digest = hashlib.sha256()
            chunks: list[bytes] = []
            size_bytes = 0
            while True:
                read_size = min(self._chunk_size, max_bytes - size_bytes + 1)
                chunk = await resolved.content.read(read_size)
                if not isinstance(chunk, bytes):
                    raise GovernanceKnowledgeResolutionError(
                        GovernanceKnowledgeFailure.SOURCE_MISMATCH
                    )
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    raise GovernanceKnowledgeResolutionError(
                        GovernanceKnowledgeFailure.LIMIT_EXCEEDED
                    )
                digest.update(chunk)
                chunks.append(chunk)
            if size_bytes == 0 or not hmac.compare_digest(
                digest.hexdigest(), reference.content_digest
            ):
                raise GovernanceKnowledgeResolutionError(
                    GovernanceKnowledgeFailure.INTEGRITY_MISMATCH
                )
            return _VerifiedContent(
                content_type=resolved.content_type,
                size_bytes=size_bytes,
                content=b"".join(chunks),
            )
        except GovernanceKnowledgeDependencyError as exc:
            raise GovernanceKnowledgeResolutionError(
                GovernanceKnowledgeFailure.DEPENDENCY_UNAVAILABLE
            ) from exc
        finally:
            try:
                await resolved.content.close()
            except GovernanceKnowledgeDependencyError as exc:
                raise GovernanceKnowledgeResolutionError(
                    GovernanceKnowledgeFailure.DEPENDENCY_UNAVAILABLE
                ) from exc


def _valid_content_type(value: str) -> bool:
    """Accept bounded printable media types without parameters or control characters."""
    return len(value) <= 200 and _CONTENT_TYPE_PATTERN.fullmatch(value) is not None
