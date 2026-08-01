"""Pure domain types and lifecycle rules for structured assessments."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from governance_schemas import EntityStatus, RiskTier

ASSESSABLE_INITIATIVE_STATUSES = {
    EntityStatus.DRAFT,
    EntityStatus.UNDER_REVIEW,
    EntityStatus.CHANGES_REQUESTED,
    EntityStatus.APPROVED,
    EntityStatus.ACTIVE,
}
RISK_SCORES = {
    RiskTier.LOW: 15,
    RiskTier.MEDIUM: 40,
    RiskTier.HIGH: 70,
    RiskTier.CRITICAL: 95,
}


class AssessmentKind(StrEnum):
    """Supported structured assessment definitions."""

    AI_IMPACT = "ai-impact-assessment"
    RIPD = "ripd"
    INTERNATIONAL_PROCESSING = "international-processing-assessment"


SCHEMA_VERSIONS = {
    AssessmentKind.AI_IMPACT: "1.0.0",
    AssessmentKind.RIPD: "1.0.0",
    AssessmentKind.INTERNATIONAL_PROCESSING: "1.0.0",
}


class AssessmentDomainError(Exception):
    """Base class for expected assessment-domain rule violations."""


class AssessmentNotApplicable(AssessmentDomainError):
    """Raised when an assessment does not apply to an initiative."""


class AssessmentNotEditable(AssessmentDomainError):
    """Raised when a non-draft assessment is changed."""


class AssessmentTypeMismatch(AssessmentDomainError):
    """Raised when the selected definition and answer type differ."""


@dataclass(frozen=True, slots=True)
class AssessmentActor:
    """Authenticated actor relevant to assessment authorization."""

    user_id: str
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class InitiativeAssessmentContext:
    """Minimal initiative facts consumed by assessment policies."""

    id: str
    business_owner_id: str
    status: EntityStatus
    personal_data: bool
    international_processing: bool


@dataclass(frozen=True, slots=True)
class Subprocessor:
    """External processor participating in an international data flow."""

    name: str
    countries: tuple[str, ...]
    purpose: str


@dataclass(frozen=True, slots=True)
class AIImpactAnswers:
    """Structured answers for an AI impact assessment."""

    affected_groups: tuple[str, ...]
    intended_benefits: str
    potential_harms: tuple[str, ...]
    human_oversight: str
    contestability: str
    mitigation_measures: tuple[str, ...]
    residual_risk: RiskTier


@dataclass(frozen=True, slots=True)
class RIPDAnswers:
    """Structured privacy impact answers aligned to a RIPD workflow."""

    controller_area: str
    processing_purpose: str
    personal_data_categories: tuple[str, ...]
    data_subjects: tuple[str, ...]
    legal_basis: str
    necessity_assessment: str
    risk_scenarios: tuple[str, ...]
    safeguards: tuple[str, ...]
    residual_risk: RiskTier


@dataclass(frozen=True, slots=True)
class InternationalProcessingAnswers:
    """Structured international processing and transfer assessment answers."""

    data_categories: tuple[str, ...]
    source_country: str
    inference_countries: tuple[str, ...]
    storage_regions: tuple[str, ...]
    log_regions: tuple[str, ...]
    subprocessors: tuple[Subprocessor, ...]
    transfer_mechanism: str
    legal_basis: str
    safeguards: tuple[str, ...]
    residual_risk: RiskTier


type AssessmentAnswers = AIImpactAnswers | RIPDAnswers | InternationalProcessingAnswers


@dataclass(frozen=True, slots=True)
class AssessmentRecord:
    """Versioned domain representation of a persisted assessment."""

    id: str
    initiative_id: str
    kind: AssessmentKind
    schema_version: str
    status: EntityStatus
    answers: AssessmentAnswers
    risk_score: int
    risk_tier: RiskTier
    assessed_by: str
    version: int
    created_at: datetime
    updated_at: datetime


def answer_kind(answers: AssessmentAnswers) -> AssessmentKind:
    """Return the assessment definition represented by an answer value."""
    if isinstance(answers, AIImpactAnswers):
        return AssessmentKind.AI_IMPACT
    if isinstance(answers, RIPDAnswers):
        return AssessmentKind.RIPD
    return AssessmentKind.INTERNATIONAL_PROCESSING


def validate_definition(kind: AssessmentKind, answers: AssessmentAnswers) -> None:
    """Require the selected assessment definition to match its answer contract."""
    if answer_kind(answers) is not kind:
        raise AssessmentTypeMismatch("Assessment type does not match the answer contract")


def validate_applicability(
    kind: AssessmentKind,
    initiative: InitiativeAssessmentContext,
) -> None:
    """Ensure the initiative state and facts permit the requested assessment."""
    if initiative.status not in ASSESSABLE_INITIATIVE_STATUSES:
        raise AssessmentNotApplicable("Initiative is not open for assessment")
    if kind is AssessmentKind.RIPD and not initiative.personal_data:
        raise AssessmentNotApplicable("RIPD requires declared personal data processing")
    if (
        kind is AssessmentKind.INTERNATIONAL_PROCESSING
        and not initiative.international_processing
    ):
        raise AssessmentNotApplicable(
            "International processing assessment requires a declared cross-border flow"
        )


def risk_score(answers: AssessmentAnswers) -> int:
    """Map the structured residual-risk decision to a stable numeric score."""
    return RISK_SCORES[answers.residual_risk]


def update_draft(
    record: AssessmentRecord,
    answers: AssessmentAnswers,
    actor_id: str,
    occurred_at: datetime,
) -> AssessmentRecord:
    """Return a new version of an editable assessment."""
    if record.status is not EntityStatus.DRAFT:
        raise AssessmentNotEditable("Only draft assessments can be updated")
    validate_definition(record.kind, answers)
    return replace(
        record,
        answers=answers,
        risk_score=risk_score(answers),
        risk_tier=answers.residual_risk,
        assessed_by=actor_id,
        version=record.version + 1,
        updated_at=occurred_at,
    )


def submit_draft(record: AssessmentRecord, occurred_at: datetime) -> AssessmentRecord:
    """Move a complete draft assessment to independent review."""
    if record.status is not EntityStatus.DRAFT:
        raise AssessmentNotEditable("Only draft assessments can be submitted")
    return replace(
        record,
        status=EntityStatus.UNDER_REVIEW,
        version=record.version + 1,
        updated_at=occurred_at,
    )


def reopen_for_changes(record: AssessmentRecord, occurred_at: datetime) -> AssessmentRecord:
    """Return a new editable version after an independent change request."""
    if record.status is not EntityStatus.UNDER_REVIEW:
        raise AssessmentNotEditable("Only assessments under review can be reopened")
    return replace(
        record,
        status=EntityStatus.DRAFT,
        version=record.version + 1,
        updated_at=occurred_at,
    )
