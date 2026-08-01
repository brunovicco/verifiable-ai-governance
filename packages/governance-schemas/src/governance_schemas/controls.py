"""Typed contracts for versioned governance controls and applicability results."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from governance_schemas.enums import (
    AutonomyLevel,
    DataClassification,
    DecisionImpact,
    HostingModel,
    RiskTier,
)
from governance_schemas.policy import PolicyContext


class ControlDomain(StrEnum):
    """Stable domains used to organize the baseline control catalog."""

    ORGANIZATION = "organization"
    RISK = "risk"
    HUMAN_OVERSIGHT = "human_oversight"
    DATA = "data"
    MODEL = "model"
    AGENT = "agent"
    SECURITY = "security"
    OPERATIONS = "operations"
    EVIDENCE = "evidence"
    CHANGE = "change"


class ControlType(StrEnum):
    """Purpose of a control in relation to a risk event."""

    PREVENTIVE = "preventive"
    DETECTIVE = "detective"
    CORRECTIVE = "corrective"


class ControlFlag(StrEnum):
    """Boolean policy facts that a declarative rule may evaluate."""

    AFFECTS_RIGHTS = "affects_rights"
    EXECUTES_ACTIONS = "executes_actions"
    PERSONAL_DATA = "personal_data"
    SENSITIVE_DATA = "sensitive_data"
    CHILDREN_DATA = "children_data"
    EXTERNAL_FACING = "external_facing"
    REGULATED_CONTEXT = "regulated_context"
    INTERNATIONAL_PROCESSING = "international_processing"
    USES_RAG = "uses_rag"
    USES_AGENTS = "uses_agents"
    USES_MCP = "uses_mcp"
    USES_CUSTOM_MODEL = "uses_custom_model"


class ControlApplicability(BaseModel):
    """Declarative selectors used to decide whether a control applies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    always: bool = False
    match: Literal["any", "all"] = "any"
    risk_tiers: tuple[RiskTier, ...] = ()
    flags_any: tuple[ControlFlag, ...] = ()
    flags_all: tuple[ControlFlag, ...] = ()
    decision_impacts: tuple[DecisionImpact, ...] = ()
    data_classifications: tuple[DataClassification, ...] = ()
    autonomy_levels: tuple[AutonomyLevel, ...] = ()
    hosting_models: tuple[HostingModel, ...] = ()

    @model_validator(mode="after")
    def require_selector(self) -> "ControlApplicability":
        """Reject ambiguous rules with no applicability condition."""
        selectors = (
            self.risk_tiers,
            self.flags_any,
            self.flags_all,
            self.decision_impacts,
            self.data_classifications,
            self.autonomy_levels,
            self.hosting_models,
        )
        if self.always and any(selectors):
            raise ValueError("An always-applicable control cannot define selectors")
        if not self.always and not any(selectors):
            raise ValueError("A control must be always applicable or define selectors")
        return self


class ControlDefinition(BaseModel):
    """One auditable governance control loaded from the versioned catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    control_id: str = Field(pattern=r"^GOV-[A-Z]{3}-\d{3}$")
    title: str = Field(min_length=3, max_length=200)
    domain: ControlDomain
    objective: str = Field(min_length=10, max_length=2000)
    control_type: ControlType
    owner: str = Field(min_length=2, max_length=200)
    review_frequency: str = Field(min_length=2, max_length=100)
    requirements: tuple[str, ...] = Field(min_length=1)
    evidence: tuple[str, ...] = Field(min_length=1)
    implementation_reference: str | None = Field(default=None, max_length=500)
    applicability: ControlApplicability


class ControlCatalog(BaseModel):
    """Versioned collection of unique control definitions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_id: str = Field(min_length=3, max_length=100)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    controls: tuple[ControlDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_ids(self) -> "ControlCatalog":
        """Reject duplicate control identifiers to preserve deterministic evidence."""
        identifiers = [control.control_id for control in self.controls]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Control identifiers must be unique")
        return self


class ControlContext(PolicyContext):
    """Initiative policy facts plus its evaluated risk tier."""

    risk_tier: RiskTier


class ControlEvaluation(BaseModel):
    """Explain whether one catalog control applies to a context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    control: ControlDefinition
    applicable: bool
    reasons: tuple[str, ...] = Field(min_length=1)


class InitiativeControlReport(BaseModel):
    """Versioned applicability report derived for one initiative."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    initiative_id: str
    catalog_id: str
    catalog_version: str
    controls: tuple[ControlEvaluation, ...]
