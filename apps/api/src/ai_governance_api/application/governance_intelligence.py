"""Governed orchestration for non-authoritative Governance Intelligence analysis."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from governance_schemas import (
    GovernanceFindingCandidate,
    GovernanceFindingEnvelope,
    GovernanceFindingType,
    GovernanceSourceReference,
)

from ai_governance_api.application.governance_knowledge import (
    GovernanceKnowledgeAccess,
    GovernanceKnowledgeResolutionError,
    VerifiedGovernanceKnowledgeSource,
)


class GovernanceIntelligenceDependencyError(RuntimeError):
    """Report an unavailable analysis or audit dependency without provider details."""


class GovernanceIntelligenceFailure(StrEnum):
    """Content-free failures exposed by governed advisory analysis."""

    INVALID_REQUEST = "invalid_request"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    OUTPUT_REJECTED = "output_rejected"
    LIMIT_EXCEEDED = "limit_exceeded"


_FAILURE_MESSAGES: dict[GovernanceIntelligenceFailure, str] = {
    GovernanceIntelligenceFailure.INVALID_REQUEST: (
        "Governance Intelligence analysis request is invalid"
    ),
    GovernanceIntelligenceFailure.DEPENDENCY_UNAVAILABLE: (
        "Governance Intelligence analysis is temporarily unavailable"
    ),
    GovernanceIntelligenceFailure.OUTPUT_REJECTED: (
        "Governance Intelligence output failed advisory validation"
    ),
    GovernanceIntelligenceFailure.LIMIT_EXCEEDED: (
        "Governance Intelligence output limit was exceeded"
    ),
}


class GovernanceIntelligenceAnalysisError(RuntimeError):
    """Expose one bounded failure without findings, source content, or provider output."""

    def __init__(self, reason: GovernanceIntelligenceFailure) -> None:
        super().__init__(_FAILURE_MESSAGES[reason])
        self.reason = reason


class GovernanceIntelligenceAnalysisType(StrEnum):
    """Explicit advisory purposes supported by the consumer-owned port."""

    POLICY_ANALYSIS = "policy_analysis"
    RISK_IDENTIFICATION = "risk_identification"
    CONTROL_SUGGESTION = "control_suggestion"
    EVIDENCE_ANALYSIS = "evidence_analysis"
    INTAKE_ASSISTANCE = "intake_assistance"


class GovernanceIntelligenceAuditStage(StrEnum):
    """Content-minimized lifecycle stages written to the audit chain."""

    ANALYSIS_REQUESTED = "analysis_requested"
    SOURCE_RESOLUTION_FAILED = "source_resolution_failed"
    SOURCES_VERIFIED = "sources_verified"
    ANALYSIS_COMPLETED = "analysis_completed"
    ANALYSIS_REJECTED = "analysis_rejected"
    ANALYSIS_DEPENDENCY_FAILED = "analysis_dependency_failed"


@dataclass(frozen=True, slots=True)
class GovernanceIntelligenceFindingAudit:
    """Minimal finding identity retained without statements or model response content."""

    finding_id: str
    finding_type: GovernanceFindingType
    agent_run_id: str


@dataclass(frozen=True, slots=True)
class GovernanceIntelligenceAuditRecord:
    """Bounded audit facts for one advisory analysis lifecycle stage."""

    stage: GovernanceIntelligenceAuditStage
    sequence: int
    analysis_type: GovernanceIntelligenceAnalysisType
    subject_id: str
    correlation_id: str
    administrator_access: bool
    references: tuple[GovernanceSourceReference, ...]
    source_total_bytes: int | None = None
    findings: tuple[GovernanceIntelligenceFindingAudit, ...] = ()
    failure_reason: str | None = None


class GovernedKnowledgeResolutionPort(Protocol):
    """Release only authorized, exact-version, digest-verified source bytes."""

    async def execute(
        self,
        *,
        references: tuple[GovernanceSourceReference, ...],
        access: GovernanceKnowledgeAccess,
    ) -> tuple[VerifiedGovernanceKnowledgeSource, ...]:
        """Resolve the complete source set or fail without partial results."""
        ...


class GovernanceIntelligencePort(Protocol):
    """Analyze governed subjects and return untrusted advisory candidates only."""

    async def analyze_policy(
        self,
        *,
        subject_id: str,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        """Suggest policy interpretations without deciding policy applicability."""
        ...

    async def identify_risks(
        self,
        *,
        subject_id: str,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        """Suggest risk candidates without assigning a governed risk state."""
        ...

    async def suggest_controls(
        self,
        *,
        subject_id: str,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        """Suggest control candidates without approving or activating controls."""
        ...

    async def analyze_evidence(
        self,
        *,
        subject_id: str,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        """Interpret source references without converting interpretations into evidence."""
        ...

    async def assist_intake(
        self,
        *,
        subject_id: str,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        """Suggest intake data without mutating the governed system of record."""
        ...


class GovernanceIntelligenceAuditPort(Protocol):
    """Append content-minimized analysis lifecycle evidence."""

    async def append(
        self,
        *,
        actor_id: str,
        record: GovernanceIntelligenceAuditRecord,
    ) -> None:
        """Append one audit stage without committing the surrounding transaction."""
        ...


class GovernanceIntelligenceTransactionPort(Protocol):
    """Commit or roll back one audit stage before analysis can continue."""

    async def commit(self) -> None:
        """Commit the pending audit stage."""
        ...

    async def rollback(self) -> None:
        """Discard a failed audit transaction."""
        ...


_ALLOWED_FINDING_TYPES: dict[
    GovernanceIntelligenceAnalysisType,
    frozenset[GovernanceFindingType],
] = {
    GovernanceIntelligenceAnalysisType.POLICY_ANALYSIS: frozenset(
        {GovernanceFindingType.POLICY_INTERPRETATION, GovernanceFindingType.EVIDENCE_GAP}
    ),
    GovernanceIntelligenceAnalysisType.RISK_IDENTIFICATION: frozenset(
        {GovernanceFindingType.RISK_CANDIDATE, GovernanceFindingType.EVIDENCE_GAP}
    ),
    GovernanceIntelligenceAnalysisType.CONTROL_SUGGESTION: frozenset(
        {GovernanceFindingType.CONTROL_CANDIDATE, GovernanceFindingType.EVIDENCE_GAP}
    ),
    GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS: frozenset(
        {GovernanceFindingType.EVIDENCE_INTERPRETATION, GovernanceFindingType.EVIDENCE_GAP}
    ),
    GovernanceIntelligenceAnalysisType.INTAKE_ASSISTANCE: frozenset(
        {GovernanceFindingType.INTAKE_SUGGESTION, GovernanceFindingType.EVIDENCE_GAP}
    ),
}

type _ReferenceKey = tuple[str, str, str | None, str | None, str]


class RunGovernanceIntelligenceAnalysis:
    """Resolve sources, invoke advisory analysis, validate output, and audit every release."""

    def __init__(
        self,
        knowledge: GovernedKnowledgeResolutionPort,
        intelligence: GovernanceIntelligencePort,
        audit: GovernanceIntelligenceAuditPort,
        transaction: GovernanceIntelligenceTransactionPort,
        *,
        max_sources: int,
        max_findings: int,
        analysis_timeout_seconds: float,
    ) -> None:
        """Initialize explicit boundaries and bounded analysis policy."""
        if not 1 <= max_sources <= 100:
            raise ValueError("Governance Intelligence max sources must be between 1 and 100")
        if not 1 <= max_findings <= 100:
            raise ValueError("Governance Intelligence max findings must be between 1 and 100")
        if not 0 < analysis_timeout_seconds <= 300:
            raise ValueError("Governance Intelligence timeout must be between 0 and 300 seconds")
        self._knowledge = knowledge
        self._intelligence = intelligence
        self._audit = audit
        self._transaction = transaction
        self._max_sources = max_sources
        self._max_findings = max_findings
        self._analysis_timeout_seconds = analysis_timeout_seconds

    async def execute(
        self,
        *,
        analysis_type: GovernanceIntelligenceAnalysisType,
        references: tuple[GovernanceSourceReference, ...],
        access: GovernanceKnowledgeAccess,
    ) -> tuple[GovernanceFindingEnvelope, ...]:
        """Return only bounded, source-bound, schema-validated advisory envelopes."""
        references = self._validate_request(analysis_type, references)
        await self._append_audit(
            actor_id=access.actor_id,
            record=self._audit_record(
                GovernanceIntelligenceAuditStage.ANALYSIS_REQUESTED,
                1,
                analysis_type,
                references,
                access,
            ),
        )
        try:
            sources = await self._knowledge.execute(references=references, access=access)
        except GovernanceKnowledgeResolutionError as exc:
            await self._append_audit(
                actor_id=access.actor_id,
                record=self._audit_record(
                    GovernanceIntelligenceAuditStage.SOURCE_RESOLUTION_FAILED,
                    2,
                    analysis_type,
                    references,
                    access,
                    failure_reason=exc.reason.value,
                ),
            )
            raise

        source_total_bytes = sum(source.size_bytes for source in sources)
        await self._append_audit(
            actor_id=access.actor_id,
            record=self._audit_record(
                GovernanceIntelligenceAuditStage.SOURCES_VERIFIED,
                2,
                analysis_type,
                references,
                access,
                source_total_bytes=source_total_bytes,
            ),
        )

        try:
            async with asyncio.timeout(self._analysis_timeout_seconds):
                raw_candidates = await self._analyze(analysis_type, sources, access)
        except TimeoutError as exc:
            await self._audit_analysis_failure(
                analysis_type,
                references,
                access,
                source_total_bytes,
                "timeout",
            )
            raise GovernanceIntelligenceAnalysisError(
                GovernanceIntelligenceFailure.DEPENDENCY_UNAVAILABLE
            ) from exc
        except GovernanceIntelligenceDependencyError as exc:
            await self._audit_analysis_failure(
                analysis_type,
                references,
                access,
                source_total_bytes,
                GovernanceIntelligenceFailure.DEPENDENCY_UNAVAILABLE.value,
            )
            raise GovernanceIntelligenceAnalysisError(
                GovernanceIntelligenceFailure.DEPENDENCY_UNAVAILABLE
            ) from exc
        except ValueError as exc:
            await self._audit_analysis_rejection(
                analysis_type,
                references,
                access,
                source_total_bytes,
                GovernanceIntelligenceFailure.OUTPUT_REJECTED,
            )
            raise GovernanceIntelligenceAnalysisError(
                GovernanceIntelligenceFailure.OUTPUT_REJECTED
            ) from exc

        try:
            candidates = self._validate_candidates(
                raw_candidates,
                analysis_type=analysis_type,
                references=references,
                correlation_id=access.correlation_id,
            )
        except GovernanceIntelligenceAnalysisError as exc:
            await self._audit_analysis_rejection(
                analysis_type,
                references,
                access,
                source_total_bytes,
                exc.reason,
            )
            raise

        findings = tuple(
            GovernanceIntelligenceFindingAudit(
                finding_id=str(candidate.finding_id),
                finding_type=candidate.finding_type,
                agent_run_id=str(candidate.provenance.agent_run_id),
            )
            for candidate in candidates
        )
        await self._append_audit(
            actor_id=access.actor_id,
            record=self._audit_record(
                GovernanceIntelligenceAuditStage.ANALYSIS_COMPLETED,
                3,
                analysis_type,
                references,
                access,
                source_total_bytes=source_total_bytes,
                findings=findings,
            ),
        )
        return tuple(GovernanceFindingEnvelope(candidate=candidate) for candidate in candidates)

    def _validate_request(
        self,
        analysis_type: object,
        references: object,
    ) -> tuple[GovernanceSourceReference, ...]:
        """Bound and revalidate source identities before writing request audit metadata."""
        if not isinstance(analysis_type, GovernanceIntelligenceAnalysisType):
            raise GovernanceIntelligenceAnalysisError(
                GovernanceIntelligenceFailure.INVALID_REQUEST
            )
        if not isinstance(references, tuple):
            raise GovernanceIntelligenceAnalysisError(
                GovernanceIntelligenceFailure.INVALID_REQUEST
            )
        if not references or len(references) > self._max_sources:
            raise GovernanceIntelligenceAnalysisError(
                GovernanceIntelligenceFailure.LIMIT_EXCEEDED
            )

        validated: list[GovernanceSourceReference] = []
        seen: set[_ReferenceKey] = set()
        digest_by_identity: dict[tuple[str, str], str] = {}
        for raw_reference in references:
            if not isinstance(raw_reference, GovernanceSourceReference):
                raise GovernanceIntelligenceAnalysisError(
                    GovernanceIntelligenceFailure.INVALID_REQUEST
                )
            try:
                source_reference = GovernanceSourceReference.model_validate(
                    raw_reference.model_dump(mode="python")
                )
            except ValueError as exc:
                raise GovernanceIntelligenceAnalysisError(
                    GovernanceIntelligenceFailure.INVALID_REQUEST
                ) from exc
            key = _reference_key(source_reference)
            identity = (source_reference.artifact_id, source_reference.version)
            prior_digest = digest_by_identity.setdefault(
                identity,
                source_reference.content_digest,
            )
            if key in seen or prior_digest != source_reference.content_digest:
                raise GovernanceIntelligenceAnalysisError(
                    GovernanceIntelligenceFailure.INVALID_REQUEST
                )
            seen.add(key)
            validated.append(source_reference)
        return tuple(validated)

    async def _analyze(
        self,
        analysis_type: GovernanceIntelligenceAnalysisType,
        sources: tuple[VerifiedGovernanceKnowledgeSource, ...],
        access: GovernanceKnowledgeAccess,
    ) -> object:
        """Dispatch one explicit advisory operation without dynamic authority methods."""
        if analysis_type is GovernanceIntelligenceAnalysisType.POLICY_ANALYSIS:
            return await self._intelligence.analyze_policy(
                subject_id=access.subject_id,
                sources=sources,
                correlation_id=access.correlation_id,
            )
        if analysis_type is GovernanceIntelligenceAnalysisType.RISK_IDENTIFICATION:
            return await self._intelligence.identify_risks(
                subject_id=access.subject_id,
                sources=sources,
                correlation_id=access.correlation_id,
            )
        if analysis_type is GovernanceIntelligenceAnalysisType.CONTROL_SUGGESTION:
            return await self._intelligence.suggest_controls(
                subject_id=access.subject_id,
                sources=sources,
                correlation_id=access.correlation_id,
            )
        if analysis_type is GovernanceIntelligenceAnalysisType.EVIDENCE_ANALYSIS:
            return await self._intelligence.analyze_evidence(
                subject_id=access.subject_id,
                sources=sources,
                correlation_id=access.correlation_id,
            )
        return await self._intelligence.assist_intake(
            subject_id=access.subject_id,
            sources=sources,
            correlation_id=access.correlation_id,
        )

    def _validate_candidates(
        self,
        raw_candidates: object,
        *,
        analysis_type: GovernanceIntelligenceAnalysisType,
        references: tuple[GovernanceSourceReference, ...],
        correlation_id: str,
    ) -> tuple[GovernanceFindingCandidate, ...]:
        """Revalidate untrusted adapter output and bind it to the verified source set."""
        if not isinstance(raw_candidates, tuple):
            raise GovernanceIntelligenceAnalysisError(
                GovernanceIntelligenceFailure.OUTPUT_REJECTED
            )
        if len(raw_candidates) > self._max_findings:
            raise GovernanceIntelligenceAnalysisError(
                GovernanceIntelligenceFailure.LIMIT_EXCEEDED
            )

        verified_keys = {_reference_key(reference) for reference in references}
        seen_finding_ids: set[str] = set()
        candidates: list[GovernanceFindingCandidate] = []
        for raw_candidate in raw_candidates:
            if not isinstance(raw_candidate, GovernanceFindingCandidate):
                raise GovernanceIntelligenceAnalysisError(
                    GovernanceIntelligenceFailure.OUTPUT_REJECTED
                )
            try:
                candidate = GovernanceFindingCandidate.model_validate(
                    raw_candidate.model_dump(mode="python")
                )
            except ValueError as exc:
                raise GovernanceIntelligenceAnalysisError(
                    GovernanceIntelligenceFailure.OUTPUT_REJECTED
                ) from exc
            finding_id = str(candidate.finding_id)
            cited_keys = [_reference_key(reference) for reference in candidate.sources]
            retrieved_keys = [
                _reference_key(reference) for reference in candidate.provenance.retrieved_sources
            ]
            if (
                finding_id in seen_finding_ids
                or candidate.finding_type not in _ALLOWED_FINDING_TYPES[analysis_type]
                or candidate.provenance.correlation_id != correlation_id
                or len(cited_keys) != len(set(cited_keys))
                or len(retrieved_keys) != len(set(retrieved_keys))
                or set(retrieved_keys) != verified_keys
                or not set(cited_keys).issubset(verified_keys)
            ):
                raise GovernanceIntelligenceAnalysisError(
                    GovernanceIntelligenceFailure.OUTPUT_REJECTED
                )
            seen_finding_ids.add(finding_id)
            candidates.append(candidate)
        return tuple(candidates)

    async def _audit_analysis_failure(
        self,
        analysis_type: GovernanceIntelligenceAnalysisType,
        references: tuple[GovernanceSourceReference, ...],
        access: GovernanceKnowledgeAccess,
        source_total_bytes: int,
        failure_reason: str,
    ) -> None:
        """Record a content-free dependency outcome after verified source access."""
        await self._append_audit(
            actor_id=access.actor_id,
            record=self._audit_record(
                GovernanceIntelligenceAuditStage.ANALYSIS_DEPENDENCY_FAILED,
                3,
                analysis_type,
                references,
                access,
                source_total_bytes=source_total_bytes,
                failure_reason=failure_reason,
            ),
        )

    async def _audit_analysis_rejection(
        self,
        analysis_type: GovernanceIntelligenceAnalysisType,
        references: tuple[GovernanceSourceReference, ...],
        access: GovernanceKnowledgeAccess,
        source_total_bytes: int,
        failure: GovernanceIntelligenceFailure,
    ) -> None:
        """Record rejection without retaining the untrusted output payload."""
        await self._append_audit(
            actor_id=access.actor_id,
            record=self._audit_record(
                GovernanceIntelligenceAuditStage.ANALYSIS_REJECTED,
                3,
                analysis_type,
                references,
                access,
                source_total_bytes=source_total_bytes,
                failure_reason=failure.value,
            ),
        )

    async def _append_audit(
        self,
        *,
        actor_id: str,
        record: GovernanceIntelligenceAuditRecord,
    ) -> None:
        """Commit every audit stage or fail before releasing analysis results."""
        try:
            await self._audit.append(actor_id=actor_id, record=record)
            await self._transaction.commit()
        except GovernanceIntelligenceDependencyError as exc:
            with suppress(GovernanceIntelligenceDependencyError):
                await self._transaction.rollback()
            raise GovernanceIntelligenceAnalysisError(
                GovernanceIntelligenceFailure.DEPENDENCY_UNAVAILABLE
            ) from exc

    @staticmethod
    def _audit_record(
        stage: GovernanceIntelligenceAuditStage,
        sequence: int,
        analysis_type: GovernanceIntelligenceAnalysisType,
        references: tuple[GovernanceSourceReference, ...],
        access: GovernanceKnowledgeAccess,
        *,
        source_total_bytes: int | None = None,
        findings: tuple[GovernanceIntelligenceFindingAudit, ...] = (),
        failure_reason: str | None = None,
    ) -> GovernanceIntelligenceAuditRecord:
        """Build bounded audit metadata without source or finding content."""
        return GovernanceIntelligenceAuditRecord(
            stage=stage,
            sequence=sequence,
            analysis_type=analysis_type,
            subject_id=access.subject_id,
            correlation_id=access.correlation_id,
            administrator_access=access.is_admin,
            references=references,
            source_total_bytes=source_total_bytes,
            findings=findings,
            failure_reason=failure_reason,
        )


def _reference_key(reference: GovernanceSourceReference) -> _ReferenceKey:
    """Return the complete immutable source identity used for output binding."""
    return (
        reference.artifact_id,
        reference.version,
        reference.node_id,
        reference.section,
        reference.content_digest,
    )
