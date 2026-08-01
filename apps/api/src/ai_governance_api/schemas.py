"""Validated HTTP request and response schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from governance_schemas import (
    ApprovalArea,
    ApprovalStatus,
    AutonomyLevel,
    DataClassification,
    DecisionImpact,
    EntityStatus,
    HostingModel,
    RiskTier,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_governance_api.domain.directory_access import (
    DirectoryAccessBlockReason,
    DirectoryAccessRestoreReason,
)
from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationInvalidationReason,
)
from ai_governance_api.domain.identity import (
    DirectoryAccountType,
    DirectoryGroupResolutionSource,
)


def _clean_strings(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value.strip()})


class CorporateDirectoryProfileRead(BaseModel):
    """Minimal Graph profile safe to expose to the authenticated user."""

    display_name: str | None = None
    email_or_upn: str | None = None
    department: str | None = None
    user_type: str | None = None
    source: str = "microsoft_graph"


class AuthorizationProvenanceRead(BaseModel):
    """Catalog evidence safe to expose to the authenticated principal."""

    catalog_id: str
    catalog_version: str
    catalog_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    matched_mapping_ids: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    group_resolution_source: DirectoryGroupResolutionSource = (
        DirectoryGroupResolutionSource.NONE
    )


class PrincipalRead(BaseModel):
    """Authenticated identity information safe to expose to its owner."""

    user_id: str
    email: str | None = None
    approval_areas: list[ApprovalArea] = Field(default_factory=list)
    is_admin: bool = False
    tenant_id: str | None = None
    object_id: str | None = None
    account_type: DirectoryAccountType | None = None
    authorization_provenance: AuthorizationProvenanceRead | None = None
    directory_profile: CorporateDirectoryProfileRead | None = None


class DirectoryAuthorizationCacheInvalidationRequest(BaseModel):
    """Administrative command for one stable Entra identity cache key."""

    tenant_id: UUID
    object_id: UUID
    reason: DirectoryAuthorizationInvalidationReason
    reference: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
    )

    @field_validator("reference")
    @classmethod
    def clean_reference(cls, value: str | None) -> str | None:
        """Trim the optional ticket reference without accepting free-form content."""
        return value.strip() if value is not None else None


class DirectoryAuthorizationCacheInvalidationRead(BaseModel):
    """Content-minimized result of a distributed cache invalidation."""

    cache_entry_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    invalidated_at: datetime
    version: int = Field(ge=1)


class DirectoryAccessChangeRequest(BaseModel):
    """Shared bounded input for an administrative directory-access change."""

    tenant_id: UUID
    object_id: UUID
    reference: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
    )

    @field_validator("reference")
    @classmethod
    def clean_reference(cls, value: str | None) -> str | None:
        """Trim the optional ticket reference without accepting free-form content."""
        return value.strip() if value is not None else None


class DirectoryAccessBlockRequest(DirectoryAccessChangeRequest):
    """Administrative request to suspend one directory identity."""

    reason: DirectoryAccessBlockReason


class DirectoryAccessRestoreRequest(DirectoryAccessChangeRequest):
    """Administrative request to restore one directory identity."""

    reason: DirectoryAccessRestoreReason


class DirectoryAccessStateRead(BaseModel):
    """Content-minimized result of an emergency access-state change."""

    restriction_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    blocked: bool
    changed_at: datetime
    version: int = Field(ge=1)


class ModelAssetCreate(BaseModel):
    """Input for registering a model asset."""

    provider: str = Field(min_length=2, max_length=200)
    model_name: str = Field(min_length=2, max_length=200)
    model_version: str = Field(min_length=1, max_length=100)
    deployment_region: str = Field(min_length=2, max_length=100)
    approved_use_cases: list[str] = Field(default_factory=list)
    prohibited_use_cases: list[str] = Field(default_factory=list)
    allowed_data_classes: list[DataClassification] = Field(default_factory=list)
    evaluation_baseline: dict[str, Any] = Field(default_factory=dict)
    deprecation_date: datetime | None = None

    @field_validator("approved_use_cases", "prohibited_use_cases")
    @classmethod
    def clean_use_cases(cls, values: list[str]) -> list[str]:
        """Normalize model use-case lists."""
        return _clean_strings(values)


class ModelAssetUpdate(BaseModel):
    """Partial update for a versioned model asset."""

    expected_version: int = Field(ge=1)
    provider: str | None = Field(default=None, min_length=2, max_length=200)
    model_name: str | None = Field(default=None, min_length=2, max_length=200)
    model_version: str | None = Field(default=None, min_length=1, max_length=100)
    deployment_region: str | None = Field(default=None, min_length=2, max_length=100)
    approved_use_cases: list[str] | None = None
    prohibited_use_cases: list[str] | None = None
    allowed_data_classes: list[DataClassification] | None = None
    evaluation_baseline: dict[str, Any] | None = None
    deprecation_date: datetime | None = None

    @field_validator("approved_use_cases", "prohibited_use_cases")
    @classmethod
    def clean_optional_use_cases(cls, values: list[str] | None) -> list[str] | None:
        """Normalize optional model use-case lists."""
        return _clean_strings(values) if values is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "ModelAssetUpdate":
        """Reject updates that contain only the concurrency version."""
        if self.model_fields_set == {"expected_version"}:
            raise ValueError("Informe ao menos um campo para atualizar.")
        return self


class AgentCreate(BaseModel):
    """Input for registering a governed agent."""

    name: str = Field(min_length=2, max_length=200)
    purpose: str = Field(min_length=10, max_length=5000)
    owner_id: str | None = Field(default=None, min_length=3, max_length=200)
    autonomy_level: AutonomyLevel
    allowed_models: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    max_cost: float | None = Field(default=None, ge=0)
    max_runtime_seconds: int | None = Field(default=None, ge=1)
    human_approval_points: list[str] = Field(default_factory=list)
    kill_switch_enabled: bool = True

    @field_validator("allowed_models", "tools", "permissions", "human_approval_points")
    @classmethod
    def clean_lists(cls, values: list[str]) -> list[str]:
        """Normalize agent capability and control lists."""
        return _clean_strings(values)


class AgentUpdate(BaseModel):
    """Partial update for a versioned agent."""

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=200)
    purpose: str | None = Field(default=None, min_length=10, max_length=5000)
    owner_id: str | None = Field(default=None, min_length=3, max_length=200)
    autonomy_level: AutonomyLevel | None = None
    allowed_models: list[str] | None = None
    tools: list[str] | None = None
    permissions: list[str] | None = None
    max_cost: float | None = Field(default=None, ge=0)
    max_runtime_seconds: int | None = Field(default=None, ge=1)
    human_approval_points: list[str] | None = None
    kill_switch_enabled: bool | None = None

    @field_validator("allowed_models", "tools", "permissions", "human_approval_points")
    @classmethod
    def clean_optional_lists(cls, values: list[str] | None) -> list[str] | None:
        """Normalize optional agent capability and control lists."""
        return _clean_strings(values) if values is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "AgentUpdate":
        """Reject updates that contain only the concurrency version."""
        if self.model_fields_set == {"expected_version"}:
            raise ValueError("Informe ao menos um campo para atualizar.")
        return self


class AISystemCreate(BaseModel):
    """Input for creating an AI system from an approved initiative."""

    name: str = Field(min_length=3, max_length=200)
    purpose: str = Field(min_length=20, max_length=5000)
    owner_id: str | None = Field(default=None, min_length=3, max_length=200)
    production: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AISystemUpdate(BaseModel):
    """Partial update for a versioned AI system."""

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=3, max_length=200)
    purpose: str | None = Field(default=None, min_length=20, max_length=5000)
    owner_id: str | None = Field(default=None, min_length=3, max_length=200)
    production: bool | None = None
    metadata_json: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "AISystemUpdate":
        """Reject updates that contain only the concurrency version."""
        if self.model_fields_set == {"expected_version"}:
            raise ValueError("Informe ao menos um campo para atualizar.")
        return self


class RetirementRequest(BaseModel):
    """Versioned request to retire an inventory entity."""

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)


class ModelAssetRead(BaseModel):
    """Serialized model asset returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    ai_system_id: str
    provider: str
    model_name: str
    model_version: str
    deployment_region: str
    approved_use_cases: list[str]
    prohibited_use_cases: list[str]
    allowed_data_classes: list[str]
    status: EntityStatus
    evaluation_baseline: dict[str, Any]
    deprecation_date: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class AgentRead(BaseModel):
    """Serialized governed agent returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    ai_system_id: str
    name: str
    purpose: str
    owner_id: str
    autonomy_level: AutonomyLevel
    allowed_models: list[str]
    tools: list[str]
    permissions: list[str]
    max_cost: float | None
    max_runtime_seconds: int | None
    human_approval_points: list[str]
    kill_switch_enabled: bool
    status: EntityStatus
    version: int
    created_at: datetime
    updated_at: datetime


class AISystemRead(BaseModel):
    """Serialized AI system summary returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    initiative_id: str
    name: str
    purpose: str
    owner_id: str
    status: EntityStatus
    risk_tier: RiskTier
    production: bool
    metadata_json: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


class AISystemDetail(AISystemRead):
    """AI system summary including registered models and agents."""

    models: list[ModelAssetRead] = Field(default_factory=list)
    agents: list[AgentRead] = Field(default_factory=list)


class InitiativeCreate(BaseModel):
    """Input for creating and preliminarily evaluating an initiative."""

    name: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=20, max_length=5000)
    business_area: str = Field(min_length=2, max_length=200)
    intended_users: str = Field(min_length=3, max_length=2000)
    decision_impact: DecisionImpact
    data_classification: DataClassification
    autonomy_level: AutonomyLevel
    hosting_model: HostingModel
    affects_rights: bool = False
    executes_actions: bool = False
    personal_data: bool = False
    sensitive_data: bool = False
    children_data: bool = False
    external_facing: bool = False
    regulated_context: bool = False
    international_processing: bool = False
    inference_countries: list[str] = Field(default_factory=list)
    uses_rag: bool = False
    uses_agents: bool = False
    uses_mcp: bool = False
    uses_custom_model: bool = False

    @field_validator("inference_countries")
    @classmethod
    def clean_countries(cls, countries: list[str]) -> list[str]:
        """Normalize the list of inference countries."""
        return sorted({country.strip() for country in countries if country.strip()})

    @model_validator(mode="after")
    def validate_locations(self) -> "InitiativeCreate":
        """Require locations for declared international processing."""
        if self.international_processing and not self.inference_countries:
            raise ValueError("Informe ao menos um país quando houver processamento internacional.")
        return self


class ApprovalRead(BaseModel):
    """Serialized governance approval gate."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    review_submission_id: str | None
    review_round: int
    area: ApprovalArea
    required: bool
    reason: str
    status: ApprovalStatus
    decided_by: str | None
    comments: str | None
    version: int


class InitiativeRead(BaseModel):
    """Serialized initiative summary returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    business_owner_id: str
    business_area: str
    intended_users: str
    status: EntityStatus
    risk_score: int
    risk_tier: RiskTier
    policy_id: str
    policy_version: str
    required_documents: list[str]
    current_review_round: int
    version: int
    created_at: datetime
    updated_at: datetime


class InitiativeDetail(InitiativeRead):
    """Initiative summary including policy inputs, gates, and systems."""

    decision_impact: DecisionImpact
    data_classification: DataClassification
    autonomy_level: AutonomyLevel
    hosting_model: HostingModel
    international_processing: bool
    inference_countries: list[str]
    affects_rights: bool
    executes_actions: bool
    personal_data: bool
    sensitive_data: bool
    children_data: bool
    external_facing: bool
    regulated_context: bool
    uses_rag: bool
    uses_agents: bool
    uses_mcp: bool
    uses_custom_model: bool
    approvals: list[ApprovalRead] = Field(
        default_factory=list,
        validation_alias="current_approvals",
    )
    systems: list[AISystemRead] = Field(default_factory=list)


class ApprovalDecisionRequest(BaseModel):
    """Input for an approval or rejection decision."""

    decision: ApprovalStatus
    comments: str = Field(min_length=5, max_length=4000)
    evidence_uri: str = Field(min_length=3, max_length=2000)
    expected_version: int = Field(ge=1)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: ApprovalStatus) -> ApprovalStatus:
        """Accept only terminal approval decisions."""
        if value not in {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.CHANGES_REQUESTED,
        }:
            raise ValueError("A decisão deve ser approved, rejected ou changes_requested")
        return value


class SubmissionRequest(BaseModel):
    """Versioned request to submit a draft initiative."""

    expected_version: int = Field(ge=1)
    revision_summary: str | None = Field(default=None, min_length=5, max_length=2000)


class InitiativeRevisionRequest(BaseModel):
    """Versioned proposal adjustments saved before a new review round."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    change_reason: str = Field(min_length=5, max_length=2000)
    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=20, max_length=5000)
    business_area: str | None = Field(default=None, min_length=2, max_length=200)
    intended_users: str | None = Field(default=None, min_length=3, max_length=2000)
    decision_impact: DecisionImpact | None = None
    data_classification: DataClassification | None = None
    autonomy_level: AutonomyLevel | None = None
    hosting_model: HostingModel | None = None
    affects_rights: bool | None = None
    executes_actions: bool | None = None
    personal_data: bool | None = None
    sensitive_data: bool | None = None
    children_data: bool | None = None
    external_facing: bool | None = None
    regulated_context: bool | None = None
    international_processing: bool | None = None
    inference_countries: list[str] | None = None
    uses_rag: bool | None = None
    uses_agents: bool | None = None
    uses_mcp: bool | None = None
    uses_custom_model: bool | None = None

    @field_validator("inference_countries")
    @classmethod
    def clean_optional_countries(cls, countries: list[str] | None) -> list[str] | None:
        """Normalize an explicitly supplied country list."""
        return _clean_strings(countries) if countries is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "InitiativeRevisionRequest":
        """Reject revision commands that do not change proposal facts."""
        if self.model_fields_set <= {"expected_version", "change_reason"}:
            raise ValueError("Informe ao menos um campo da proposta para atualizar.")
        return self

    def changes(self) -> dict[str, object]:
        """Return only explicitly supplied proposal fields."""
        return self.model_dump(
            exclude={"expected_version", "change_reason"},
            exclude_unset=True,
            exclude_none=True,
        )


class InitiativeResubmissionRequest(BaseModel):
    """Versioned request to create a new immutable review round."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    revision_summary: str = Field(min_length=10, max_length=2000)


class ReviewSubmissionRead(BaseModel):
    """Content-minimized history of one immutable review submission."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    initiative_id: str
    review_round: int
    status: EntityStatus
    submitted_by: str
    submitted_at: datetime
    resolved_at: datetime | None
    revision_summary: str
    policy_id: str
    policy_version: str
    risk_score: int
    risk_tier: RiskTier
    approvals: list[ApprovalRead] = Field(default_factory=list)


class AuditEventRead(BaseModel):
    """Serialized tamper-evident audit event."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    occurred_at: datetime
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    entity_version: int
    payload: dict[str, object]
    previous_hash: str | None
    event_hash: str
