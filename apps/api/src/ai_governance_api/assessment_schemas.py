"""HTTP boundary schemas and explicit mappings for structured assessments."""

from datetime import datetime
from typing import Annotated, Literal

from governance_schemas import EntityStatus, RiskTier
from pydantic import BaseModel, Field, field_validator

from ai_governance_api.domain.assessments import (
    AIImpactAnswers,
    AssessmentAnswers,
    AssessmentKind,
    AssessmentRecord,
    InternationalProcessingAnswers,
    RIPDAnswers,
    Subprocessor,
)


def _clean_strings(values: list[str]) -> list[str]:
    """Normalize non-empty list values while preserving first-seen order."""
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class AIImpactAnswersPayload(BaseModel):
    """HTTP payload for an AI impact assessment."""

    assessment_type: Literal["ai-impact-assessment"]
    affected_groups: list[str] = Field(min_length=1)
    intended_benefits: str = Field(min_length=10, max_length=5000)
    potential_harms: list[str] = Field(min_length=1)
    human_oversight: str = Field(min_length=10, max_length=5000)
    contestability: str = Field(min_length=10, max_length=5000)
    mitigation_measures: list[str] = Field(min_length=1)
    residual_risk: RiskTier

    @field_validator("affected_groups", "potential_harms", "mitigation_measures")
    @classmethod
    def clean_lists(cls, values: list[str]) -> list[str]:
        """Normalize human-entered list fields."""
        return _clean_strings(values)


class RIPDAnswersPayload(BaseModel):
    """HTTP payload for a Brazilian privacy impact report."""

    assessment_type: Literal["ripd"]
    controller_area: str = Field(min_length=2, max_length=200)
    processing_purpose: str = Field(min_length=10, max_length=5000)
    personal_data_categories: list[str] = Field(min_length=1)
    data_subjects: list[str] = Field(min_length=1)
    legal_basis: str = Field(min_length=3, max_length=1000)
    necessity_assessment: str = Field(min_length=10, max_length=5000)
    risk_scenarios: list[str] = Field(min_length=1)
    safeguards: list[str] = Field(min_length=1)
    residual_risk: RiskTier

    @field_validator(
        "personal_data_categories",
        "data_subjects",
        "risk_scenarios",
        "safeguards",
    )
    @classmethod
    def clean_lists(cls, values: list[str]) -> list[str]:
        """Normalize human-entered privacy list fields."""
        return _clean_strings(values)


class SubprocessorPayload(BaseModel):
    """HTTP representation of one international subprocessor."""

    name: str = Field(min_length=2, max_length=200)
    countries: list[str] = Field(min_length=1)
    purpose: str = Field(min_length=5, max_length=2000)

    @field_validator("countries")
    @classmethod
    def clean_countries(cls, values: list[str]) -> list[str]:
        """Normalize the subprocessor country list."""
        return _clean_strings(values)


class InternationalProcessingAnswersPayload(BaseModel):
    """HTTP payload for international AI data processing analysis."""

    assessment_type: Literal["international-processing-assessment"]
    data_categories: list[str] = Field(min_length=1)
    source_country: str = Field(min_length=2, max_length=100)
    inference_countries: list[str] = Field(min_length=1)
    storage_regions: list[str] = Field(min_length=1)
    log_regions: list[str] = Field(min_length=1)
    subprocessors: list[SubprocessorPayload] = Field(default_factory=list)
    transfer_mechanism: str = Field(min_length=3, max_length=1000)
    legal_basis: str = Field(min_length=3, max_length=1000)
    safeguards: list[str] = Field(min_length=1)
    residual_risk: RiskTier

    @field_validator(
        "data_categories",
        "inference_countries",
        "storage_regions",
        "log_regions",
        "safeguards",
    )
    @classmethod
    def clean_lists(cls, values: list[str]) -> list[str]:
        """Normalize international processing list fields."""
        return _clean_strings(values)


type AssessmentAnswersPayload = Annotated[
    AIImpactAnswersPayload | RIPDAnswersPayload | InternationalProcessingAnswersPayload,
    Field(discriminator="assessment_type"),
]


class AssessmentWriteRequest(BaseModel):
    """Versioned create-or-update request for a structured assessment."""

    expected_version: int | None = Field(default=None, ge=1)
    answers: AssessmentAnswersPayload


class AssessmentSubmitRequest(BaseModel):
    """Optimistic-concurrency request to submit an assessment."""

    expected_version: int = Field(ge=1)


class AssessmentRead(BaseModel):
    """HTTP representation of a structured assessment domain record."""

    id: str
    initiative_id: str
    assessment_type: AssessmentKind
    schema_version: str
    status: EntityStatus
    answers: AssessmentAnswersPayload
    risk_score: int
    risk_tier: RiskTier
    assessed_by: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, record: AssessmentRecord) -> "AssessmentRead":
        """Map a pure domain record to the HTTP response contract."""
        return cls(
            id=record.id,
            initiative_id=record.initiative_id,
            assessment_type=record.kind,
            schema_version=record.schema_version,
            status=record.status,
            answers=_to_payload(record.answers),
            risk_score=record.risk_score,
            risk_tier=record.risk_tier,
            assessed_by=record.assessed_by,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


def to_domain_answers(payload: AssessmentAnswersPayload) -> AssessmentAnswers:
    """Map a validated HTTP payload to a pure definition-specific domain value."""
    if isinstance(payload, AIImpactAnswersPayload):
        return AIImpactAnswers(
            affected_groups=tuple(payload.affected_groups),
            intended_benefits=payload.intended_benefits,
            potential_harms=tuple(payload.potential_harms),
            human_oversight=payload.human_oversight,
            contestability=payload.contestability,
            mitigation_measures=tuple(payload.mitigation_measures),
            residual_risk=payload.residual_risk,
        )
    if isinstance(payload, RIPDAnswersPayload):
        return RIPDAnswers(
            controller_area=payload.controller_area,
            processing_purpose=payload.processing_purpose,
            personal_data_categories=tuple(payload.personal_data_categories),
            data_subjects=tuple(payload.data_subjects),
            legal_basis=payload.legal_basis,
            necessity_assessment=payload.necessity_assessment,
            risk_scenarios=tuple(payload.risk_scenarios),
            safeguards=tuple(payload.safeguards),
            residual_risk=payload.residual_risk,
        )
    return InternationalProcessingAnswers(
        data_categories=tuple(payload.data_categories),
        source_country=payload.source_country,
        inference_countries=tuple(payload.inference_countries),
        storage_regions=tuple(payload.storage_regions),
        log_regions=tuple(payload.log_regions),
        subprocessors=tuple(
            Subprocessor(
                name=item.name,
                countries=tuple(item.countries),
                purpose=item.purpose,
            )
            for item in payload.subprocessors
        ),
        transfer_mechanism=payload.transfer_mechanism,
        legal_basis=payload.legal_basis,
        safeguards=tuple(payload.safeguards),
        residual_risk=payload.residual_risk,
    )


def _to_payload(answers: AssessmentAnswers) -> AssessmentAnswersPayload:
    """Map pure domain answers to their discriminated HTTP representation."""
    if isinstance(answers, AIImpactAnswers):
        return AIImpactAnswersPayload(
            assessment_type=AssessmentKind.AI_IMPACT.value,
            affected_groups=list(answers.affected_groups),
            intended_benefits=answers.intended_benefits,
            potential_harms=list(answers.potential_harms),
            human_oversight=answers.human_oversight,
            contestability=answers.contestability,
            mitigation_measures=list(answers.mitigation_measures),
            residual_risk=answers.residual_risk,
        )
    if isinstance(answers, RIPDAnswers):
        return RIPDAnswersPayload(
            assessment_type=AssessmentKind.RIPD.value,
            controller_area=answers.controller_area,
            processing_purpose=answers.processing_purpose,
            personal_data_categories=list(answers.personal_data_categories),
            data_subjects=list(answers.data_subjects),
            legal_basis=answers.legal_basis,
            necessity_assessment=answers.necessity_assessment,
            risk_scenarios=list(answers.risk_scenarios),
            safeguards=list(answers.safeguards),
            residual_risk=answers.residual_risk,
        )
    return InternationalProcessingAnswersPayload(
        assessment_type=AssessmentKind.INTERNATIONAL_PROCESSING.value,
        data_categories=list(answers.data_categories),
        source_country=answers.source_country,
        inference_countries=list(answers.inference_countries),
        storage_regions=list(answers.storage_regions),
        log_regions=list(answers.log_regions),
        subprocessors=[
            SubprocessorPayload(
                name=item.name,
                countries=list(item.countries),
                purpose=item.purpose,
            )
            for item in answers.subprocessors
        ],
        transfer_mechanism=answers.transfer_mechanism,
        legal_basis=answers.legal_basis,
        safeguards=list(answers.safeguards),
        residual_risk=answers.residual_risk,
    )
