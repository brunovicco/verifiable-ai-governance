"""Strict advisory contracts for untrusted Governance Intelligence findings."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

GOVERNANCE_FINDING_SCHEMA_VERSION: Literal["1.0"] = "1.0"

_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_Identifier = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
    ),
]
_ShortText = Annotated[str, Field(min_length=1, max_length=300)]
_Statement = Annotated[str, Field(min_length=1, max_length=4000)]
_ReferenceUri = Annotated[
    str,
    Field(
        min_length=3,
        max_length=2048,
        pattern=r"^(?:https?://|urn:)[^\s]+$",
    ),
]


class _AdvisoryContractModel(BaseModel):
    """Immutable closed model for non-authoritative intelligence records."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class GovernanceFindingType(StrEnum):
    """Small initial taxonomy of advisory Governance Intelligence findings."""

    POLICY_INTERPRETATION = "policy_interpretation"
    RISK_CANDIDATE = "risk_candidate"
    CONTROL_CANDIDATE = "control_candidate"
    EVIDENCE_GAP = "evidence_gap"
    EVIDENCE_INTERPRETATION = "evidence_interpretation"
    INTAKE_SUGGESTION = "intake_suggestion"


class GovernanceSourceReference(_AdvisoryContractModel):
    """Content-free locator for a versioned source supporting a finding."""

    artifact_id: _Identifier
    version: _Identifier
    node_id: _Identifier | None = None
    section: str | None = Field(default=None, min_length=1, max_length=200)
    content_digest: _Digest


class ExternalTaxonomyReference(_AdvisoryContractModel):
    """Vendor-neutral locator for an item in an external taxonomy."""

    provider: _ShortText
    taxonomy: _ShortText
    identifier: _ShortText
    version: _ShortText | None = None
    reference_uri: _ReferenceUri | None = None


class AgentRunProvenance(_AdvisoryContractModel):
    """Content-minimized provenance for the agent run that produced a finding."""

    agent_run_id: UUID
    agent_name: _Identifier
    provider: _ShortText
    model: _ShortText
    model_version: _ShortText | None = None
    prompt_config_version: _Identifier
    retrieval_query_reference: _Identifier | None = None
    retrieved_sources: tuple[GovernanceSourceReference, ...] = ()
    tool_call_references: tuple[_Identifier, ...] = ()
    created_at: datetime
    correlation_id: _Identifier

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        """Require explicit UTC so provenance can be ordered unambiguously."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Agent run timestamp must be timezone-aware")
        if value.utcoffset() != timedelta(0):
            raise ValueError("Agent run timestamp must be expressed in UTC")
        return value.astimezone(UTC)


class GovernanceFindingCandidate(_AdvisoryContractModel):
    """Validated recommendation that has no governance decision authority."""

    finding_id: UUID
    finding_type: GovernanceFindingType
    statement: _Statement
    confidence: float = Field(ge=0.0, le=1.0)
    sources: tuple[GovernanceSourceReference, ...] = Field(min_length=1)
    external_taxonomy_references: tuple[ExternalTaxonomyReference, ...] = ()
    provenance: AgentRunProvenance
    trust_level: Literal["untrusted"] = "untrusted"
    advisory_only: Literal[True] = True


class GovernanceFindingEnvelope(_AdvisoryContractModel):
    """Versioned wire envelope for one untrusted advisory finding candidate."""

    schema_version: Literal["1.0"] = GOVERNANCE_FINDING_SCHEMA_VERSION
    candidate: GovernanceFindingCandidate


class UnsupportedGovernanceFindingSchemaVersion(ValueError):
    """Report an absent or unsupported Governance Finding wire version."""

    def __init__(self, received_version: object) -> None:
        rendered = repr(received_version)
        if len(rendered) > 80:
            rendered = f"{rendered[:77]}..."
        super().__init__(f"Unsupported Governance Finding schema version: {rendered}")


_GOVERNANCE_FINDING_ENVELOPE_MODELS: Mapping[
    str, type[GovernanceFindingEnvelope]
] = MappingProxyType(
    {
        GOVERNANCE_FINDING_SCHEMA_VERSION: GovernanceFindingEnvelope,
    }
)
SUPPORTED_GOVERNANCE_FINDING_SCHEMA_VERSIONS: frozenset[str] = frozenset(
    _GOVERNANCE_FINDING_ENVELOPE_MODELS
)


def parse_governance_finding(
    payload: Mapping[str, object],
) -> GovernanceFindingEnvelope:
    """Parse one explicitly versioned finding or fail closed for unknown versions."""
    schema_version = payload.get("schema_version")
    model = (
        _GOVERNANCE_FINDING_ENVELOPE_MODELS.get(schema_version)
        if isinstance(schema_version, str)
        else None
    )
    if model is None:
        raise UnsupportedGovernanceFindingSchemaVersion(schema_version)
    return model.model_validate(dict(payload))
