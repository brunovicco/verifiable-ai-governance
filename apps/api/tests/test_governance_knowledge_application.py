"""Tests for governed source resolution before Governance Intelligence consumption."""

import hashlib
from io import BytesIO

import pytest
from ai_governance_api.application.governance_knowledge import (
    GovernanceKnowledgeAccess,
    GovernanceKnowledgeDependencyError,
    GovernanceKnowledgeFailure,
    GovernanceKnowledgeResolutionError,
    ResolvedGovernanceKnowledgeSource,
    ResolveGovernanceKnowledgeSources,
    VerifiedGovernanceKnowledgeSource,
)
from governance_schemas import GovernanceSourceReference


class BytesContent:
    """Expose deterministic bytes through the governed asynchronous stream contract."""

    def __init__(
        self,
        content: bytes,
        *,
        fail_read: bool = False,
        fail_close: bool = False,
    ) -> None:
        self._content = BytesIO(content)
        self._fail_read = fail_read
        self._fail_close = fail_close
        self.closed = False

    async def read(self, size: int) -> bytes:
        if self._fail_read:
            raise GovernanceKnowledgeDependencyError("source read failed")
        return self._content.read(size)

    async def close(self) -> None:
        self.closed = True
        if self._fail_close:
            raise GovernanceKnowledgeDependencyError("source close failed")


class FakeAuthorizer:
    """Capture exact-reference authorization checks."""

    def __init__(self, *, allowed: bool = True, fail: bool = False) -> None:
        self.allowed = allowed
        self.fail = fail
        self.calls: list[GovernanceSourceReference] = []

    async def can_read(
        self,
        *,
        reference: GovernanceSourceReference,
        access: GovernanceKnowledgeAccess,
    ) -> bool:
        del access
        self.calls.append(reference)
        if self.fail:
            raise GovernanceKnowledgeDependencyError("authorization failed")
        return self.allowed


class FakeResolver:
    """Resolve configured sources only after authorization succeeds."""

    def __init__(
        self,
        sources: dict[tuple[str, str], ResolvedGovernanceKnowledgeSource] | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.sources = sources or {}
        self.fail = fail
        self.calls: list[GovernanceSourceReference] = []

    async def resolve(
        self,
        *,
        reference: GovernanceSourceReference,
        access: GovernanceKnowledgeAccess,
    ) -> ResolvedGovernanceKnowledgeSource | None:
        del access
        self.calls.append(reference)
        if self.fail:
            raise GovernanceKnowledgeDependencyError("resolution failed")
        return self.sources.get((reference.artifact_id, reference.version))


ACCESS = GovernanceKnowledgeAccess(
    actor_id="reviewer-1",
    subject_id="initiative-1",
    correlation_id="corr:gi-1-test",
)


def reference(
    content: bytes,
    *,
    artifact_id: str = "policy:acceptable-ai-use",
    version: str = "3.1",
    node_id: str | None = "clause:4.2.3",
    section: str | None = "4.2.3",
    digest: str | None = None,
) -> GovernanceSourceReference:
    """Create an exact versioned reference for deterministic source bytes."""
    return GovernanceSourceReference(
        artifact_id=artifact_id,
        version=version,
        node_id=node_id,
        section=section,
        content_digest=digest or hashlib.sha256(content).hexdigest(),
    )


def resolved(
    source_reference: GovernanceSourceReference,
    content: BytesContent,
    *,
    artifact_id: str | None = None,
    version: str | None = None,
    content_type: str = "text/markdown",
) -> ResolvedGovernanceKnowledgeSource:
    """Create unverified adapter output for one requested source."""
    return ResolvedGovernanceKnowledgeSource(
        artifact_id=artifact_id or source_reference.artifact_id,
        version=version or source_reference.version,
        content_type=content_type,
        content=content,
    )


def use_case(
    authorizer: FakeAuthorizer,
    resolver: FakeResolver,
    *,
    max_sources: int = 4,
    max_source_bytes: int = 1024,
    max_total_bytes: int = 2048,
) -> ResolveGovernanceKnowledgeSources:
    """Build the use case with explicit test limits."""
    return ResolveGovernanceKnowledgeSources(
        authorizer,
        resolver,
        max_sources=max_sources,
        max_source_bytes=max_source_bytes,
        max_total_bytes=max_total_bytes,
    )


async def test_authorized_exact_source_is_digest_verified_before_release() -> None:
    content = b"# Acceptable AI use\nHuman review is required."
    source_reference = reference(content)
    stream = BytesContent(content)
    authorizer = FakeAuthorizer()
    resolver = FakeResolver(
        {
            (source_reference.artifact_id, source_reference.version): resolved(
                source_reference, stream
            )
        }
    )

    result = await use_case(authorizer, resolver).execute(
        references=(source_reference,),
        access=ACCESS,
    )

    assert result[0].reference == source_reference
    assert result[0].content == content
    assert result[0].content_type == "text/markdown"
    assert result[0].size_bytes == len(content)
    assert authorizer.calls == [source_reference]
    assert resolver.calls == [source_reference]
    assert stream.closed
    assert content.decode() not in repr(result[0])


async def test_sections_of_same_verified_artifact_resolve_once_but_authorize_each() -> None:
    content = b"section one\nsection two"
    first = reference(content, node_id="section:1", section="1")
    second = reference(content, node_id="section:2", section="2")
    stream = BytesContent(content)
    authorizer = FakeAuthorizer()
    resolver = FakeResolver({(first.artifact_id, first.version): resolved(first, stream)})

    results = await use_case(authorizer, resolver).execute(
        references=(first, second),
        access=ACCESS,
    )

    assert tuple(item.reference for item in results) == (first, second)
    assert authorizer.calls == [first, second]
    assert resolver.calls == [first]
    assert results[0].content is results[1].content


async def test_denied_and_missing_sources_share_a_content_free_failure() -> None:
    source_reference = reference(b"governed source")
    denied_authorizer = FakeAuthorizer(allowed=False)
    denied_resolver = FakeResolver()

    with pytest.raises(GovernanceKnowledgeResolutionError) as denied:
        await use_case(denied_authorizer, denied_resolver).execute(
            references=(source_reference,), access=ACCESS
        )
    assert denied.value.reason is GovernanceKnowledgeFailure.SOURCE_UNAVAILABLE
    assert denied_resolver.calls == []

    with pytest.raises(GovernanceKnowledgeResolutionError) as missing:
        await use_case(FakeAuthorizer(), FakeResolver()).execute(
            references=(source_reference,), access=ACCESS
        )
    assert str(missing.value) == str(denied.value)
    assert source_reference.artifact_id not in str(missing.value)
    assert source_reference.content_digest not in str(missing.value)


@pytest.mark.parametrize(
    ("artifact_id", "version", "content_type"),
    [
        ("policy:another", None, "text/plain"),
        (None, "4.0", "text/plain"),
        (None, None, "text/plain; charset=utf-8"),
        (None, None, "text/plain\nunsafe"),
    ],
)
async def test_resolver_identity_version_and_metadata_must_match_exactly(
    artifact_id: str | None,
    version: str | None,
    content_type: str,
) -> None:
    payload = b"exact source"
    source_reference = reference(payload)
    stream = BytesContent(payload)
    source = resolved(
        source_reference,
        stream,
        artifact_id=artifact_id,
        version=version,
        content_type=content_type,
    )

    with pytest.raises(GovernanceKnowledgeResolutionError) as captured:
        await use_case(
            FakeAuthorizer(),
            FakeResolver({(source_reference.artifact_id, source_reference.version): source}),
        ).execute(references=(source_reference,), access=ACCESS)

    assert captured.value.reason is GovernanceKnowledgeFailure.SOURCE_MISMATCH
    assert stream.closed


@pytest.mark.parametrize("payload", [b"changed source", b""])
async def test_actual_bytes_must_match_the_declared_non_empty_digest(payload: bytes) -> None:
    source_reference = reference(b"expected source")
    stream = BytesContent(payload)

    with pytest.raises(GovernanceKnowledgeResolutionError) as captured:
        await use_case(
            FakeAuthorizer(),
            FakeResolver(
                {
                    (source_reference.artifact_id, source_reference.version): resolved(
                        source_reference, stream
                    )
                }
            ),
        ).execute(references=(source_reference,), access=ACCESS)

    assert captured.value.reason is GovernanceKnowledgeFailure.INTEGRITY_MISMATCH
    assert stream.closed


async def test_per_source_and_total_content_limits_fail_closed() -> None:
    oversized = b"12345"
    oversized_reference = reference(oversized)
    oversized_stream = BytesContent(oversized)
    with pytest.raises(GovernanceKnowledgeResolutionError) as per_source:
        await use_case(
            FakeAuthorizer(),
            FakeResolver(
                {
                    (oversized_reference.artifact_id, oversized_reference.version): resolved(
                        oversized_reference, oversized_stream
                    )
                }
            ),
            max_source_bytes=4,
        ).execute(references=(oversized_reference,), access=ACCESS)
    assert per_source.value.reason is GovernanceKnowledgeFailure.LIMIT_EXCEEDED
    assert oversized_stream.closed

    first_content = b"1234"
    second_content = b"5678"
    first = reference(first_content, artifact_id="policy:first")
    second = reference(second_content, artifact_id="policy:second")
    first_stream = BytesContent(first_content)
    second_stream = BytesContent(second_content)
    resolver = FakeResolver(
        {
            (first.artifact_id, first.version): resolved(first, first_stream),
            (second.artifact_id, second.version): resolved(second, second_stream),
        }
    )
    with pytest.raises(GovernanceKnowledgeResolutionError) as total:
        await use_case(
            FakeAuthorizer(), resolver, max_source_bytes=4, max_total_bytes=7
        ).execute(references=(first, second), access=ACCESS)
    assert total.value.reason is GovernanceKnowledgeFailure.LIMIT_EXCEEDED
    assert first_stream.closed and second_stream.closed


async def test_duplicate_or_contradictory_requests_fail_before_port_calls() -> None:
    content = b"one source"
    first = reference(content)
    conflicting = reference(content, digest="f" * 64, node_id="section:other")
    authorizer = FakeAuthorizer()
    resolver = FakeResolver()

    for references in ((first, first), (first, conflicting)):
        with pytest.raises(GovernanceKnowledgeResolutionError) as captured:
            await use_case(authorizer, resolver).execute(references=references, access=ACCESS)
        assert captured.value.reason is GovernanceKnowledgeFailure.INVALID_REQUEST

    assert authorizer.calls == []
    assert resolver.calls == []


async def test_request_count_and_empty_request_are_bounded() -> None:
    first = reference(b"first", artifact_id="policy:first")
    second = reference(b"second", artifact_id="policy:second")
    service = use_case(FakeAuthorizer(), FakeResolver(), max_sources=1)

    for references in ((), (first, second)):
        with pytest.raises(GovernanceKnowledgeResolutionError) as captured:
            await service.execute(references=references, access=ACCESS)
        assert captured.value.reason is GovernanceKnowledgeFailure.LIMIT_EXCEEDED


@pytest.mark.parametrize("stage", ["authorize", "resolve", "read", "close"])
async def test_dependency_failures_are_mapped_without_source_metadata(stage: str) -> None:
    payload = b"governed source"
    source_reference = reference(payload)
    stream = BytesContent(payload, fail_read=stage == "read", fail_close=stage == "close")
    authorizer = FakeAuthorizer(fail=stage == "authorize")
    resolver = FakeResolver(
        {
            (source_reference.artifact_id, source_reference.version): resolved(
                source_reference, stream
            )
        },
        fail=stage == "resolve",
    )

    with pytest.raises(GovernanceKnowledgeResolutionError) as captured:
        await use_case(authorizer, resolver).execute(
            references=(source_reference,), access=ACCESS
        )

    assert captured.value.reason is GovernanceKnowledgeFailure.DEPENDENCY_UNAVAILABLE
    assert source_reference.artifact_id not in str(captured.value)
    assert source_reference.content_digest not in str(captured.value)


def test_access_and_limit_configuration_reject_invalid_values() -> None:
    for actor_id in ("", " actor", "actor\nspoof"):
        with pytest.raises(ValueError):
            GovernanceKnowledgeAccess(
                actor_id=actor_id,
                subject_id="subject",
                correlation_id="correlation",
            )
    with pytest.raises(ValueError):
        use_case(FakeAuthorizer(), FakeResolver(), max_source_bytes=0)


def test_verified_source_cannot_be_constructed_outside_the_gate() -> None:
    payload = b"unverified"

    with pytest.raises(TypeError, match="resolution gate"):
        VerifiedGovernanceKnowledgeSource(
            reference=reference(payload),
            content_type="text/plain",
            size_bytes=len(payload),
            content=payload,
        )
