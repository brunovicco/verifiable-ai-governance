"""Contract tests for advisory Governance Intelligence findings."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from governance_schemas import (
    AgentRunProvenance,
    ExternalTaxonomyReference,
    GovernanceFindingCandidate,
    GovernanceFindingEnvelope,
    GovernanceFindingType,
    GovernanceSourceReference,
)
from pydantic import ValidationError

NOW = datetime(2026, 8, 16, 18, 30, tzinfo=UTC)
FINDING_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")


def source_reference() -> GovernanceSourceReference:
    """Return one deterministic source locator."""
    return GovernanceSourceReference(
        artifact_id="policy:acceptable-ai-use",
        version="3.1",
        node_id="clause:4.2.3",
        section="4.2.3",
        content_digest="a" * 64,
    )


def provenance() -> AgentRunProvenance:
    """Return minimal, content-free agent-run provenance."""
    return AgentRunProvenance(
        agent_run_id=RUN_ID,
        agent_name="risk_mapper",
        provider="provider-neutral",
        model="governance-analysis-model",
        model_version="2026.08",
        prompt_config_version="risk-mapping-v1",
        retrieval_query_reference="query:4de78b5f",
        retrieved_sources=(source_reference(),),
        tool_call_references=("tool-call:resolve-policy",),
        created_at=NOW,
        correlation_id="corr:gi-0-test",
    )


def finding(**overrides: object) -> GovernanceFindingCandidate:
    """Return one valid advisory finding with optional field overrides."""
    values: dict[str, object] = {
        "finding_id": FINDING_ID,
        "finding_type": GovernanceFindingType.RISK_CANDIDATE,
        "statement": "The policy language may require an additional human review gate.",
        "confidence": 0.91,
        "sources": (source_reference(),),
        "external_taxonomy_references": (
            ExternalTaxonomyReference(
                provider="nist",
                taxonomy="ai-rmf",
                identifier="GOVERN-1.2",
                version="1.0",
                reference_uri="https://airc.nist.gov/AI_RMF_Knowledge_Base/Playbook",
            ),
        ),
        "provenance": provenance(),
    }
    values.update(overrides)
    return GovernanceFindingCandidate(**values)


def test_valid_finding_envelope_is_accepted() -> None:
    envelope = GovernanceFindingEnvelope(candidate=finding())

    payload = envelope.model_dump(mode="json")
    assert payload["schema_version"] == "1.0"
    assert payload["candidate"]["finding_type"] == "risk_candidate"
    assert payload["candidate"]["trust_level"] == "untrusted"
    assert payload["candidate"]["advisory_only"] is True


def test_valid_source_provenance_and_taxonomy_references_are_accepted() -> None:
    candidate = finding()

    assert candidate.sources[0].node_id == "clause:4.2.3"
    assert candidate.provenance.retrieved_sources == candidate.sources
    assert candidate.external_taxonomy_references[0].provider == "nist"


@pytest.mark.parametrize("confidence", [0.0, 1.0])
def test_confidence_boundaries_remain_advisory(confidence: float) -> None:
    candidate = finding(confidence=confidence)

    assert candidate.confidence == confidence
    assert candidate.trust_level == "untrusted"
    assert candidate.advisory_only is True


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_confidence_outside_unit_interval_is_rejected(confidence: float) -> None:
    with pytest.raises(ValidationError):
        finding(confidence=confidence)


@pytest.mark.parametrize(
    ("marker", "value"),
    [("trust_level", "trusted"), ("advisory_only", False)],
)
def test_advisory_trust_markers_cannot_be_escalated(marker: str, value: object) -> None:
    payload = finding().model_dump(mode="python")
    payload[marker] = value

    with pytest.raises(ValidationError):
        GovernanceFindingCandidate.model_validate(payload)


@pytest.mark.parametrize(
    "authority_field",
    [
        "approved",
        "authorized",
        "compliant",
        "approval_status",
        "authorization_status",
        "release_authorized",
        "runtime_authorized",
        "control_approved",
    ],
)
def test_authority_fields_are_rejected(authority_field: str) -> None:
    payload = finding().model_dump(mode="python")
    payload[authority_field] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GovernanceFindingCandidate.model_validate(payload)


@pytest.mark.parametrize("forbidden_field", ["chain_of_thought", "full_prompt", "document_content"])
def test_observability_dumping_fields_are_rejected(forbidden_field: str) -> None:
    payload = provenance().model_dump(mode="python")
    payload[forbidden_field] = "sensitive content"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AgentRunProvenance.model_validate(payload)


def test_invalid_source_digest_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GovernanceSourceReference(
            artifact_id="policy:acceptable-ai-use",
            version="3.1",
            content_digest="sha256:not-a-project-digest",
        )


def test_external_taxonomy_rejects_unsafe_reference_uri() -> None:
    with pytest.raises(ValidationError):
        ExternalTaxonomyReference(
            provider="example-provider",
            taxonomy="internal-framework",
            identifier="CONTROL-1",
            reference_uri="javascript:alert(1)",
        )


def test_source_requires_versioned_artifact_identity() -> None:
    payload = source_reference().model_dump(mode="python")
    payload.pop("version")

    with pytest.raises(ValidationError):
        GovernanceSourceReference.model_validate(payload)


def test_agent_run_provenance_rejects_missing_required_identity() -> None:
    payload = provenance().model_dump(mode="python")
    payload.pop("provider")

    with pytest.raises(ValidationError):
        AgentRunProvenance.model_validate(payload)


def test_agent_run_provenance_requires_utc_timestamp() -> None:
    payload = provenance().model_dump(mode="python")
    payload["created_at"] = NOW.replace(tzinfo=None)

    with pytest.raises(ValidationError, match="timezone-aware"):
        AgentRunProvenance.model_validate(payload)


def test_finding_requires_at_least_one_source() -> None:
    with pytest.raises(ValidationError):
        finding(sources=())


def test_envelope_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValidationError):
        GovernanceFindingEnvelope.model_validate(
            {"schema_version": "2.0", "candidate": finding().model_dump(mode="python")}
        )
