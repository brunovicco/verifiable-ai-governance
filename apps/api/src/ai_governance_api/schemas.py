from datetime import datetime

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


class InitiativeCreate(BaseModel):
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
        return sorted({country.strip() for country in countries if country.strip()})

    @model_validator(mode="after")
    def validate_locations(self) -> "InitiativeCreate":
        if self.international_processing and not self.inference_countries:
            raise ValueError("Informe ao menos um país quando houver processamento internacional.")
        return self


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    area: ApprovalArea
    required: bool
    reason: str
    status: ApprovalStatus
    decided_by: str | None
    comments: str | None
    version: int


class InitiativeRead(BaseModel):
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
    version: int
    created_at: datetime
    updated_at: datetime


class InitiativeDetail(InitiativeRead):
    decision_impact: DecisionImpact
    data_classification: DataClassification
    autonomy_level: AutonomyLevel
    hosting_model: HostingModel
    international_processing: bool
    inference_countries: list[str]
    approvals: list[ApprovalRead] = Field(default_factory=list)


class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalStatus
    comments: str = Field(min_length=5, max_length=4000)
    evidence_uri: str = Field(min_length=3, max_length=2000)
    expected_version: int = Field(ge=1)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: ApprovalStatus) -> ApprovalStatus:
        if value not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise ValueError("A decisão deve ser approved ou rejected")
        return value


class SubmissionRequest(BaseModel):
    expected_version: int = Field(ge=1)


class AuditEventRead(BaseModel):
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
