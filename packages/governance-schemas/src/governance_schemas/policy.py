from pydantic import BaseModel, Field

from governance_schemas.enums import (
    ApprovalArea,
    AutonomyLevel,
    DataClassification,
    DecisionImpact,
    HostingModel,
    RiskTier,
)


class PolicyContext(BaseModel):
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
    uses_rag: bool = False
    uses_agents: bool = False
    uses_mcp: bool = False
    uses_custom_model: bool = False


class RiskBreakdown(BaseModel):
    impact: int = Field(ge=0, le=30)
    data: int = Field(ge=0, le=25)
    autonomy: int = Field(ge=0, le=25)
    exposure: int = Field(ge=0, le=10)
    regulatory: int = Field(ge=0, le=10)

    @property
    def total(self) -> int:
        return self.impact + self.data + self.autonomy + self.exposure + self.regulatory


class ApprovalRequirement(BaseModel):
    area: ApprovalArea
    required: bool
    reason: str


class PolicyDecision(BaseModel):
    policy_id: str = "baseline-governance-policy"
    policy_version: str = "1.0.0"
    score: int = Field(ge=0, le=100)
    tier: RiskTier
    breakdown: RiskBreakdown
    approvals: list[ApprovalRequirement]
    required_documents: list[str]
    blocked_reasons: list[str] = Field(default_factory=list)

    @property
    def can_submit(self) -> bool:
        return not self.blocked_reasons
