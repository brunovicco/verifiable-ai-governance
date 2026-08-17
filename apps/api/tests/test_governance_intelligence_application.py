"""Tests for governed advisory analysis orchestration and output validation."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from io import BytesIO
from typing import cast
from uuid import UUID

import pytest
from ai_governance_api import dependencies
from ai_governance_api.adapters.governance_intelligence_audit import (
    SqlAlchemyGovernanceIntelligenceAudit,
)
from ai_governance_api.application.governance_intelligence import (
    GovernanceIntelligenceAnalysisError,
    GovernanceIntelligenceAnalysisType,
    GovernanceIntelligenceAuditRecord,
    GovernanceIntelligenceAuditStage,
    GovernanceIntelligenceDependencyError,
    GovernanceIntelligenceFailure,
    GovernanceIntelligenceFindingAudit,
    RunGovernanceIntelligenceAnalysis,
)
from ai_governance_api.application.governance_knowledge import (
    GovernanceKnowledgeAccess,
    GovernanceKnowledgeFailure,
    GovernanceKnowledgeResolutionError,
    ResolvedGovernanceKnowledgeSource,
    ResolveGovernanceKnowledgeSources,
    VerifiedGovernanceKnowledgeSource,
)
from ai_governance_api.config import Settings
from ai_governance_api.database import SessionFactory
from ai_governance_api.models import AuditEvent
from governance_schemas import (
    AgentRunProvenance,
    GovernanceFindingCandidate,
    GovernanceFindingType,
    GovernanceSourceReference,
)
from sqlalchemy import select

CONTENT = b'{"control": "GOV-EVD-001", "passed": true}'
CORRELATION_ID = "corr:gi-2-test"
SUBJECT_ID = "22222222-2222-4222-8222-222222222222"
ACTOR_ID = "owner-1"
FINDING_ID = UUID("33333333-3333-4333-8333-333333333333")
RUN_ID = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 8, 17, 5, 0, tzinfo=UTC)


def reference(
    *,
    artifact_id: str = "evidence:11111111-1111-4111-8111-111111111111",
    content_digest: str | None = None,
) -> GovernanceSourceReference:
    """Return one exact whole-file source reference."""
    return GovernanceSourceReference(
        artifact_id=artifact_id,
        version="1",
        content_digest=content_digest or hashlib.sha256(CONTENT).hexdigest(),
    )


def access() -> GovernanceKnowledgeAccess:
    """Return one bounded authenticated analysis context."""
    return GovernanceKnowledgeAccess(
        actor_id=ACTOR_ID,
        subject_id=SUBJECT_ID,
        correlation_id=CORRELATION_ID,
    )


def candidate(
    source_reference: GovernanceSourceReference,
    *,
    finding_type: GovernanceFindingType = GovernanceFindingType.EVIDENCE_INTERPRETATION,
    finding_id: UUID = FINDING_ID,
    correlation_id: str = CORRELATION_ID,
    sources: tuple[GovernanceSourceReference, ...] | None = None,
    retrieved_sources: tuple[GovernanceSourceReference, ...] | None = None,
) -> GovernanceFindingCandidate:
    """Return one schema-valid untrusted finding candidate."""
    return GovernanceFindingCandidate(
        finding_id=finding_id,
        finding_type=finding_type,
        statement="The uploaded artifact may support a reviewer assessment.",
        confidence=0.82,
        sources=sources or (source_reference,),
        provenance=AgentRunProvenance(
            agent_run_id=RUN_ID,
            agent_name="evidence_interpreter",
            provider="provider-neutral",
            model="deterministic-test-adapter",
            prompt_config_version="gi-2-test-v1",
            retrieved_sources=retrieved_sources or (source_reference,),
            created_at=NOW,
            correlation_id=correlation_id,
        ),
    )


class BytesContent:
    """Expose deterministic source bytes through the GI-1 streaming contract."""

    def __init__(self, content: bytes) -> None:
        self._content = BytesIO(content)
        self.closed = False

    async def read(self, size: int) -> bytes:
        return self._content.read(size)

    async def close(self) -> None:
        self.closed = True


class AllowAuthorizer:
    """Authorize the exact test reference."""

    async def can_read(
        self,
        *,
        reference: GovernanceSourceReference,
        access: GovernanceKnowledgeAccess,
    ) -> bool:
        del reference, access
        return True


class StaticResolver:
    """Return one unverified source stream for the real GI-1 gate."""

    def __init__(self, source_reference: GovernanceSourceReference, content: BytesContent) -> None:
        self._reference = source_reference
        self._content = content

    async def resolve(
        self,
        *,
        reference: GovernanceSourceReference,
        access: GovernanceKnowledgeAccess,
    ) -> ResolvedGovernanceKnowledgeSource | None:
        del access
        if reference != self._reference:
            return None
        return ResolvedGovernanceKnowledgeSource(
            artifact_id=reference.artifact_id,
            version=reference.version,
            content_type="application/json",
            content=self._content,
        )


class TracingKnowledge:
    """Wrap the real GI-1 gate and expose orchestration ordering."""

    def __init__(
        self,
        gate: ResolveGovernanceKnowledgeSources,
        trace: list[str],
    ) -> None:
        self._gate = gate
        self._trace = trace
        self.calls = 0

    async def execute(
        self,
        *,
        references: tuple[GovernanceSourceReference, ...],
        access: GovernanceKnowledgeAccess,
    ) -> tuple[VerifiedGovernanceKnowledgeSource, ...]:
        self.calls += 1
        self._trace.append("knowledge")
        return await self._gate.execute(references=references, access=access)


class FailingKnowledge:
    """Return one stable GI-1 failure for lifecycle-audit tests."""

    def __init__(self) -> None:
        self.calls = 0

    async def execute(
        self,
        *,
        references: tuple[GovernanceSourceReference, ...],
        access: GovernanceKnowledgeAccess,
    ) -> tuple[VerifiedGovernanceKnowledgeSource, ...]:
        del references, access
        self.calls += 1
        raise GovernanceKnowledgeResolutionError(GovernanceKnowledgeFailure.SOURCE_UNAVAILABLE)


class FakeIntelligence:
    """Return configured untrusted output through all advisory operations."""

    def __init__(
        self,
        result: object,
        trace: list[str],
        *,
        fail: bool = False,
        block: bool = False,
    ) -> None:
        self.result = result
        self.trace = trace
        self.fail = fail
        self.block = block
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[
            tuple[
                str,
                str,
                tuple[VerifiedGovernanceKnowledgeSource, ...],
                str,
            ]
        ] = []

    async def _respond(
        self,
        operation: str,
        *,
        subject_id: str,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        self.trace.append("analysis")
        self.calls.append((operation, subject_id, sources, correlation_id))
        self.started.set()
        if self.block:
            await self.release.wait()
        if self.fail:
            raise GovernanceIntelligenceDependencyError("provider detail must not escape")
        return cast(tuple[GovernanceFindingCandidate, ...], self.result)

    async def analyze_policy(
        self,
        *,
        subject_id: str,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        return await self._respond(
            "analyze_policy",
            subject_id=subject_id,
            sources=sources,
            correlation_id=correlation_id,
        )

    async def identify_risks(
        self,
        *,
        subject_id: str,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        return await self._respond(
            "identify_risks",
            subject_id=subject_id,
            sources=sources,
            correlation_id=correlation_id,
        )

    async def suggest_controls(
        self,
        *,
        subject_id: str,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        return await self._respond(
            "suggest_controls",
            subject_id=subject_id,
            sources=sources,
            correlation_id=correlation_id,
        )

    async def analyze_evidence(
        self,
        *,
        subject_id: str,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        return await self._respond(
            "analyze_evidence",
            subject_id=subject_id,
            sources=sources,
            correlation_id=correlation_id,
        )

    async def assist_intake(
        self,
        *,
        subject_id: str,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        return await self._respond(
            "assist_intake",
            subject_id=subject_id,
            sources=sources,
            correlation_id=correlation_id,
        )


class FakeAudit:
    """Capture minimized lifecycle records and deterministic failures."""

    def __init__(
        self,
        trace: list[str],
        *,
        fail_stage: GovernanceIntelligenceAuditStage | None = None,
    ) -> None:
        self.trace = trace
        self.fail_stage = fail_stage
        self.records: list[tuple[str, GovernanceIntelligenceAuditRecord]] = []

    async def append(
        self,
        *,
        actor_id: str,
        record: GovernanceIntelligenceAuditRecord,
    ) -> None:
        self.trace.append(f"audit:{record.stage.value}")
        if record.stage is self.fail_stage:
            raise GovernanceIntelligenceDependencyError("audit detail must not escape")
        self.records.append((actor_id, record))


class FakeTransaction:
    """Capture stage commits and rollbacks."""

    def __init__(self, trace: list[str], *, fail_commit_at: int | None = None) -> None:
        self.trace = trace
        self.fail_commit_at = fail_commit_at
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1
        self.trace.append("commit")
        if self.commits == self.fail_commit_at:
            raise GovernanceIntelligenceDependencyError("commit detail must not escape")

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.trace.append("rollback")


def governed_knowledge(
    source_reference: GovernanceSourceReference,
    trace: list[str],
) -> tuple[TracingKnowledge, BytesContent]:
    """Build the real GI-1 verification gate under a tracing wrapper."""
    content = BytesContent(CONTENT)
    gate = ResolveGovernanceKnowledgeSources(
        AllowAuthorizer(),
        StaticResolver(source_reference, content),
        max_sources=4,
        max_source_bytes=1024,
        max_total_bytes=2048,
    )
    return TracingKnowledge(gate, trace), content


def use_case(
    knowledge: TracingKnowledge | FailingKnowledge,
    intelligence: FakeIntelligence,
    audit: FakeAudit,
    transaction: FakeTransaction,
    *,
    max_sources: int = 4,
    max_findings: int = 5,
    timeout: float = 1,
) -> RunGovernanceIntelligenceAnalysis:
    """Compose the GI-2 use case with deterministic ports."""
    return RunGovernanceIntelligenceAnalysis(
        knowledge,
        intelligence,
        audit,
        transaction,
        max_sources=max_sources,
        max_findings=max_findings,
        analysis_timeout_seconds=timeout,
    )


async def test_verified_sources_are_audited_before_advisory_analysis_and_release() -> None:
    trace: list[str] = []
    source_reference = reference()
    knowledge, content = governed_knowledge(source_reference, trace)
    intelligence = FakeIntelligence((candidate(source_reference),), trace)
    audit = FakeAudit(trace)
    transaction = FakeTransaction(trace)

    result = await use_case(knowledge, intelligence, audit, transaction).execute(
        analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
        references=(source_reference,),
        access=access(),
    )

    assert result[0].candidate.finding_id == FINDING_ID
    assert result[0].candidate.trust_level == "untrusted"
    assert result[0].candidate.advisory_only is True
    assert intelligence.calls[0][0] == "analyze_evidence"
    assert intelligence.calls[0][1] == SUBJECT_ID
    assert intelligence.calls[0][2][0].content == CONTENT
    assert intelligence.calls[0][3] == CORRELATION_ID
    assert content.closed
    assert trace == [
        "audit:analysis_requested",
        "commit",
        "knowledge",
        "audit:sources_verified",
        "commit",
        "analysis",
        "audit:analysis_completed",
        "commit",
    ]
    assert [record.stage for _, record in audit.records] == [
        GovernanceIntelligenceAuditStage.ANALYSIS_REQUESTED,
        GovernanceIntelligenceAuditStage.SOURCES_VERIFIED,
        GovernanceIntelligenceAuditStage.ANALYSIS_COMPLETED,
    ]
    assert audit.records[1][1].source_total_bytes == len(CONTENT)
    assert audit.records[2][1].findings[0].finding_id == str(FINDING_ID)
    assert CONTENT.decode() not in repr(audit.records)


@pytest.mark.parametrize(
    ("analysis_type", "finding_type", "operation"),
    [
        (
            GovernanceIntelligenceAnalysisType.POLICY_ANALYSIS,
            GovernanceFindingType.POLICY_INTERPRETATION,
            "analyze_policy",
        ),
        (
            GovernanceIntelligenceAnalysisType.RISK_IDENTIFICATION,
            GovernanceFindingType.RISK_CANDIDATE,
            "identify_risks",
        ),
        (
            GovernanceIntelligenceAnalysisType.CONTROL_SUGGESTION,
            GovernanceFindingType.CONTROL_CANDIDATE,
            "suggest_controls",
        ),
        (
            GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
            GovernanceFindingType.EVIDENCE_INTERPRETATION,
            "analyze_evidence",
        ),
        (
            GovernanceIntelligenceAnalysisType.INTAKE_ASSISTANCE,
            GovernanceFindingType.INTAKE_SUGGESTION,
            "assist_intake",
        ),
    ],
)
async def test_each_explicit_analysis_purpose_dispatches_only_its_advisory_operation(
    analysis_type: GovernanceIntelligenceAnalysisType,
    finding_type: GovernanceFindingType,
    operation: str,
) -> None:
    trace: list[str] = []
    source_reference = reference()
    knowledge, _ = governed_knowledge(source_reference, trace)
    intelligence = FakeIntelligence(
        (candidate(source_reference, finding_type=finding_type),),
        trace,
    )

    result = await use_case(
        knowledge,
        intelligence,
        FakeAudit(trace),
        FakeTransaction(trace),
    ).execute(
        analysis_type=analysis_type,
        references=(source_reference,),
        access=access(),
    )

    assert result[0].candidate.finding_type is finding_type
    assert [call[0] for call in intelligence.calls] == [operation]


async def test_evidence_gap_is_allowed_for_every_explicit_analysis_purpose() -> None:
    for analysis_type in GovernanceIntelligenceAnalysisType:
        trace: list[str] = []
        source_reference = reference()
        knowledge, _ = governed_knowledge(source_reference, trace)
        intelligence = FakeIntelligence(
            (candidate(source_reference, finding_type=GovernanceFindingType.EVIDENCE_GAP),),
            trace,
        )

        result = await use_case(
            knowledge,
            intelligence,
            FakeAudit(trace),
            FakeTransaction(trace),
        ).execute(
            analysis_type=analysis_type,
            references=(source_reference,),
            access=access(),
        )

        assert result[0].candidate.finding_type is GovernanceFindingType.EVIDENCE_GAP


@pytest.mark.parametrize(
    "invalid_case",
    [
        "non_tuple",
        "wrong_finding_type",
        "wrong_correlation",
        "invented_citation",
        "missing_retrieval",
        "duplicate_citation",
        "duplicate_retrieval",
        "duplicate_finding_id",
        "invalid_constructed_model",
    ],
)
async def test_untrusted_output_must_match_verified_sources_and_provenance(
    invalid_case: str,
) -> None:
    trace: list[str] = []
    source_reference = reference()
    invented = reference(
        artifact_id="evidence:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        content_digest="a" * 64,
    )
    valid = candidate(source_reference)
    result: object = (valid,)
    if invalid_case == "non_tuple":
        result = [valid]
    elif invalid_case == "wrong_finding_type":
        result = (
            candidate(source_reference, finding_type=GovernanceFindingType.CONTROL_CANDIDATE),
        )
    elif invalid_case == "wrong_correlation":
        result = (candidate(source_reference, correlation_id="corr:other"),)
    elif invalid_case == "invented_citation":
        result = (candidate(source_reference, sources=(invented,)),)
    elif invalid_case == "missing_retrieval":
        result = (candidate(source_reference, retrieved_sources=(invented,)),)
    elif invalid_case == "duplicate_citation":
        result = (candidate(source_reference, sources=(source_reference, source_reference)),)
    elif invalid_case == "duplicate_retrieval":
        result = (
            candidate(
                source_reference,
                retrieved_sources=(source_reference, source_reference),
            ),
        )
    elif invalid_case == "duplicate_finding_id":
        result = (valid, valid)
    elif invalid_case == "invalid_constructed_model":
        result = (
            valid.model_copy(update={"advisory_only": False}),
        )
    knowledge, _ = governed_knowledge(source_reference, trace)
    audit = FakeAudit(trace)

    with pytest.raises(GovernanceIntelligenceAnalysisError) as captured:
        await use_case(
            knowledge,
            FakeIntelligence(result, trace),
            audit,
            FakeTransaction(trace),
        ).execute(
            analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
            references=(source_reference,),
            access=access(),
        )

    assert captured.value.reason is GovernanceIntelligenceFailure.OUTPUT_REJECTED
    assert audit.records[-1][1].stage is GovernanceIntelligenceAuditStage.ANALYSIS_REJECTED
    assert audit.records[-1][1].findings == ()
    assert valid.statement not in repr(audit.records[-1])


async def test_excess_findings_are_rejected_without_returning_partial_output() -> None:
    trace: list[str] = []
    source_reference = reference()
    findings = tuple(
        candidate(
            source_reference,
            finding_id=UUID(f"00000000-0000-4000-8000-{index:012d}"),
        )
        for index in range(1, 4)
    )
    knowledge, _ = governed_knowledge(source_reference, trace)
    audit = FakeAudit(trace)

    with pytest.raises(GovernanceIntelligenceAnalysisError) as captured:
        await use_case(
            knowledge,
            FakeIntelligence(findings, trace),
            audit,
            FakeTransaction(trace),
            max_findings=2,
        ).execute(
            analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
            references=(source_reference,),
            access=access(),
        )

    assert captured.value.reason is GovernanceIntelligenceFailure.LIMIT_EXCEEDED
    assert audit.records[-1][1].failure_reason == "limit_exceeded"
    assert audit.records[-1][1].findings == ()


async def test_empty_advisory_result_is_valid_and_audited() -> None:
    trace: list[str] = []
    source_reference = reference()
    knowledge, _ = governed_knowledge(source_reference, trace)
    audit = FakeAudit(trace)

    result = await use_case(
        knowledge,
        FakeIntelligence((), trace),
        audit,
        FakeTransaction(trace),
    ).execute(
        analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
        references=(source_reference,),
        access=access(),
    )

    assert result == ()
    assert audit.records[-1][1].stage is GovernanceIntelligenceAuditStage.ANALYSIS_COMPLETED
    assert audit.records[-1][1].findings == ()


@pytest.mark.parametrize("failure", ["dependency", "timeout"])
async def test_analysis_dependency_failures_are_bounded_and_audited(failure: str) -> None:
    trace: list[str] = []
    source_reference = reference()
    knowledge, _ = governed_knowledge(source_reference, trace)
    intelligence = FakeIntelligence(
        (candidate(source_reference),),
        trace,
        fail=failure == "dependency",
        block=failure == "timeout",
    )
    audit = FakeAudit(trace)

    with pytest.raises(GovernanceIntelligenceAnalysisError) as captured:
        await use_case(
            knowledge,
            intelligence,
            audit,
            FakeTransaction(trace),
            timeout=0.01,
        ).execute(
            analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
            references=(source_reference,),
            access=access(),
        )

    assert captured.value.reason is GovernanceIntelligenceFailure.DEPENDENCY_UNAVAILABLE
    assert source_reference.artifact_id not in str(captured.value)
    assert audit.records[-1][1].stage is (
        GovernanceIntelligenceAuditStage.ANALYSIS_DEPENDENCY_FAILED
    )
    assert audit.records[-1][1].findings == ()


async def test_source_resolution_failure_is_audited_without_calling_analysis() -> None:
    trace: list[str] = []
    source_reference = reference()
    intelligence = FakeIntelligence((), trace)
    audit = FakeAudit(trace)

    with pytest.raises(GovernanceKnowledgeResolutionError):
        await use_case(
            FailingKnowledge(),
            intelligence,
            audit,
            FakeTransaction(trace),
        ).execute(
            analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
            references=(source_reference,),
            access=access(),
        )

    assert intelligence.calls == []
    assert audit.records[-1][1].stage is GovernanceIntelligenceAuditStage.SOURCE_RESOLUTION_FAILED
    assert audit.records[-1][1].failure_reason == "source_unavailable"


async def test_initial_audit_failure_prevents_source_access_and_analysis() -> None:
    trace: list[str] = []
    source_reference = reference()
    knowledge, _ = governed_knowledge(source_reference, trace)
    intelligence = FakeIntelligence((candidate(source_reference),), trace)
    transaction = FakeTransaction(trace)

    with pytest.raises(GovernanceIntelligenceAnalysisError) as captured:
        await use_case(
            knowledge,
            intelligence,
            FakeAudit(
                trace,
                fail_stage=GovernanceIntelligenceAuditStage.ANALYSIS_REQUESTED,
            ),
            transaction,
        ).execute(
            analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
            references=(source_reference,),
            access=access(),
        )

    assert captured.value.reason is GovernanceIntelligenceFailure.DEPENDENCY_UNAVAILABLE
    assert knowledge.calls == 0
    assert intelligence.calls == []
    assert transaction.commits == 0
    assert transaction.rollbacks == 1


@pytest.mark.parametrize("fail_commit_at", [1, 2])
async def test_audit_commit_failure_stops_before_the_next_sensitive_stage(
    fail_commit_at: int,
) -> None:
    trace: list[str] = []
    source_reference = reference()
    knowledge, _ = governed_knowledge(source_reference, trace)
    intelligence = FakeIntelligence((candidate(source_reference),), trace)
    transaction = FakeTransaction(trace, fail_commit_at=fail_commit_at)

    with pytest.raises(GovernanceIntelligenceAnalysisError) as captured:
        await use_case(
            knowledge,
            intelligence,
            FakeAudit(trace),
            transaction,
        ).execute(
            analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
            references=(source_reference,),
            access=access(),
        )

    assert captured.value.reason is GovernanceIntelligenceFailure.DEPENDENCY_UNAVAILABLE
    assert transaction.rollbacks == 1
    assert knowledge.calls == (0 if fail_commit_at == 1 else 1)
    assert intelligence.calls == []


async def test_completion_audit_failure_withholds_valid_findings() -> None:
    trace: list[str] = []
    source_reference = reference()
    knowledge, _ = governed_knowledge(source_reference, trace)
    intelligence = FakeIntelligence((candidate(source_reference),), trace)
    transaction = FakeTransaction(trace)

    with pytest.raises(GovernanceIntelligenceAnalysisError) as captured:
        await use_case(
            knowledge,
            intelligence,
            FakeAudit(
                trace,
                fail_stage=GovernanceIntelligenceAuditStage.ANALYSIS_COMPLETED,
            ),
            transaction,
        ).execute(
            analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
            references=(source_reference,),
            access=access(),
        )

    assert captured.value.reason is GovernanceIntelligenceFailure.DEPENDENCY_UNAVAILABLE
    assert len(intelligence.calls) == 1
    assert transaction.rollbacks == 1


async def test_cancellation_propagates_after_durable_source_access_audit() -> None:
    trace: list[str] = []
    source_reference = reference()
    knowledge, _ = governed_knowledge(source_reference, trace)
    intelligence = FakeIntelligence((candidate(source_reference),), trace, block=True)
    audit = FakeAudit(trace)
    task = asyncio.create_task(
        use_case(
            knowledge,
            intelligence,
            audit,
            FakeTransaction(trace),
            timeout=5,
        ).execute(
            analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
            references=(source_reference,),
            access=access(),
        )
    )
    await intelligence.started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert [record.stage for _, record in audit.records] == [
        GovernanceIntelligenceAuditStage.ANALYSIS_REQUESTED,
        GovernanceIntelligenceAuditStage.SOURCES_VERIFIED,
    ]
    assert GovernanceIntelligenceAuditStage.ANALYSIS_COMPLETED not in {
        record.stage for _, record in audit.records
    }


@pytest.mark.parametrize(
    ("max_sources", "max_findings", "timeout"),
    [(0, 1, 1), (101, 1, 1), (1, 0, 1), (1, 101, 1), (1, 1, 0), (1, 1, 301)],
)
def test_analysis_limits_are_validated(
    max_sources: int,
    max_findings: int,
    timeout: float,
) -> None:
    trace: list[str] = []
    source_reference = reference()
    knowledge, _ = governed_knowledge(source_reference, trace)

    with pytest.raises(ValueError):
        use_case(
            knowledge,
            FakeIntelligence((), trace),
            FakeAudit(trace),
            FakeTransaction(trace),
            max_sources=max_sources,
            max_findings=max_findings,
            timeout=timeout,
        )


@pytest.mark.parametrize("invalid_case", ["oversized", "duplicate", "invalid_model"])
async def test_invalid_source_requests_are_rejected_before_audit_or_resolution(
    invalid_case: str,
) -> None:
    trace: list[str] = []
    source_reference = reference()
    another_reference = reference(
        artifact_id="evidence:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        content_digest="a" * 64,
    )
    references: tuple[GovernanceSourceReference, ...] = (
        source_reference,
        another_reference,
    )
    max_sources = 1
    expected = GovernanceIntelligenceFailure.LIMIT_EXCEEDED
    if invalid_case == "duplicate":
        references = (source_reference, source_reference)
        max_sources = 2
        expected = GovernanceIntelligenceFailure.INVALID_REQUEST
    elif invalid_case == "invalid_model":
        invalid = source_reference.model_copy(update={"content_digest": "not-a-digest"})
        references = (invalid,)
        max_sources = 1
        expected = GovernanceIntelligenceFailure.INVALID_REQUEST
    knowledge, _ = governed_knowledge(source_reference, trace)
    audit = FakeAudit(trace)

    with pytest.raises(GovernanceIntelligenceAnalysisError) as captured:
        await use_case(
            knowledge,
            FakeIntelligence((), trace),
            audit,
            FakeTransaction(trace),
            max_sources=max_sources,
        ).execute(
            analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
            references=references,
            access=access(),
        )

    assert captured.value.reason is expected
    assert audit.records == []
    assert knowledge.calls == 0


async def test_sqlalchemy_audit_persists_only_content_minimized_analysis_facts() -> None:
    source_reference = reference()
    record = GovernanceIntelligenceAuditRecord(
        stage=GovernanceIntelligenceAuditStage.ANALYSIS_COMPLETED,
        sequence=3,
        analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
        subject_id=SUBJECT_ID,
        correlation_id=CORRELATION_ID,
        administrator_access=False,
        references=(source_reference,),
        source_total_bytes=len(CONTENT),
        findings=(
            GovernanceIntelligenceFindingAudit(
                finding_id=str(FINDING_ID),
                finding_type=GovernanceFindingType.EVIDENCE_INTERPRETATION,
                agent_run_id=str(RUN_ID),
            ),
        ),
    )

    audit = SqlAlchemyGovernanceIntelligenceAudit(SessionFactory)
    await audit.append(actor_id=ACTOR_ID, record=record)
    await audit.commit()
    async with SessionFactory() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "governance_intelligence.analysis_completed",
                AuditEvent.entity_id == CORRELATION_ID,
            )
        )

    assert event is not None
    assert event.entity_type == "governance_intelligence_analysis"
    assert event.entity_version == 3
    assert event.payload["analysis_type"] == "evidence_analysis"
    assert event.payload["source_count"] == 1
    assert event.payload["finding_count"] == 1
    serialized = json.dumps(event.payload, sort_keys=True)
    assert CONTENT.decode() not in serialized
    assert "uploaded artifact may support" not in serialized.lower()
    assert "filename" not in serialized
    assert "storage_bucket" not in serialized
    assert "storage_key" not in serialized
    assert "prompt" not in serialized


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("governance_intelligence_max_findings", 0),
        ("governance_intelligence_max_findings", 101),
        ("governance_intelligence_analysis_timeout_seconds", 0),
        ("governance_intelligence_analysis_timeout_seconds", 301),
    ],
)
def test_governance_intelligence_composition_limits_fail_closed(
    override: str,
    value: int,
) -> None:
    """Reject deployment values outside the use-case policy boundary."""
    with pytest.raises(ValueError):
        Settings(**{override: value})


async def test_composition_root_runs_verified_analysis_with_durable_stage_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wire GI-1, GI-2, bounded policy, and one request-scoped audit unit together."""
    correlation_id = "corr:gi-2a-composition"
    settings = Settings(
        governance_knowledge_max_sources=4,
        governance_intelligence_max_findings=5,
        governance_intelligence_analysis_timeout_seconds=1,
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    trace: list[str] = []
    source_reference = reference()
    knowledge, content = governed_knowledge(source_reference, trace)
    intelligence = FakeIntelligence(
        (candidate(source_reference, correlation_id=correlation_id),),
        trace,
    )

    service = dependencies.build_governance_intelligence_analysis(
        knowledge,
        intelligence,
    )
    composition = vars(service)
    assert composition["_audit"] is composition["_transaction"]
    assert composition["_max_sources"] == 4
    assert composition["_max_findings"] == 5
    assert composition["_analysis_timeout_seconds"] == 1

    result = await service.execute(
        analysis_type=GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS,
        references=(source_reference,),
        access=GovernanceKnowledgeAccess(
            actor_id=ACTOR_ID,
            subject_id=SUBJECT_ID,
            correlation_id=correlation_id,
        ),
    )

    assert result[0].candidate.finding_id == FINDING_ID
    assert content.closed
    async with SessionFactory() as session:
        events = (
            await session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_id == correlation_id)
                .order_by(AuditEvent.entity_version)
            )
        ).all()

    assert [event.action for event in events] == [
        "governance_intelligence.analysis_requested",
        "governance_intelligence.sources_verified",
        "governance_intelligence.analysis_completed",
    ]
