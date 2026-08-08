"""SQLAlchemy persistence models for governance aggregates and audit events."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

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
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ai_governance_api.domain.asset_registry import (
    AssetReviewState,
    asset_review_state,
)
from ai_governance_api.domain.incidents import (
    ExceptionStatus,
    IncidentStatus,
)


def new_id() -> str:
    """Return a UUID string suitable for public entity identifiers."""
    return str(uuid4())


def utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base shared by all persistence models."""

    pass


class VersionedMixin:
    """Add optimistic versioning and lifecycle timestamps to mutable entities."""

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ReviewableAssetMixin:
    """Add current review evidence to a governed operational asset."""

    approved_scope_digest: Mapped[str | None] = mapped_column(String(64))
    reviewed_by: Mapped[str | None] = mapped_column(String(200))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    review_reference: Mapped[str | None] = mapped_column(String(100))

    @property
    def review_state(self) -> AssetReviewState:
        """Return current review validity while preserving lifecycle status."""
        deadline = self.next_review_at
        if deadline is not None and (deadline.tzinfo is None or deadline.utcoffset() is None):
            deadline = deadline.replace(tzinfo=UTC)
        return asset_review_state(
            approved_scope_digest=self.approved_scope_digest,
            next_review_at=deadline,
            now=datetime.now(UTC),
        )


class Initiative(VersionedMixin, Base):
    """Business proposal evaluated by the governance policy."""

    __tablename__ = "initiatives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    business_owner_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    business_area: Mapped[str] = mapped_column(String(200), nullable=False)
    intended_users: Mapped[str] = mapped_column(Text, nullable=False)
    decision_impact: Mapped[DecisionImpact] = mapped_column(
        Enum(DecisionImpact, native_enum=False), nullable=False
    )
    data_classification: Mapped[DataClassification] = mapped_column(
        Enum(DataClassification, native_enum=False), nullable=False
    )
    autonomy_level: Mapped[AutonomyLevel] = mapped_column(
        Enum(AutonomyLevel, native_enum=False), nullable=False
    )
    hosting_model: Mapped[HostingModel] = mapped_column(
        Enum(HostingModel, native_enum=False), nullable=False
    )
    affects_rights: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    executes_actions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    personal_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sensitive_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    children_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    external_facing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    regulated_context: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    international_processing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    inference_countries: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    uses_rag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uses_agents: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uses_mcp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uses_custom_model: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False), default=EntityStatus.DRAFT, nullable=False
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_tier: Mapped[RiskTier] = mapped_column(Enum(RiskTier, native_enum=False), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    required_documents: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_review_round: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="initiative", cascade="all, delete-orphan", lazy="selectin"
    )
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="initiative")
    systems: Mapped[list["AISystem"]] = relationship(back_populates="initiative", lazy="selectin")
    review_submissions: Mapped[list["ReviewSubmission"]] = relationship(
        back_populates="initiative", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def current_approvals(self) -> list["Approval"]:
        """Return only gates belonging to the active review projection."""
        return [
            approval
            for approval in self.approvals
            if approval.review_round == self.current_review_round
        ]


class AISystem(VersionedMixin, Base):
    """Operational AI system created from an approved initiative."""

    __tablename__ = "ai_systems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    initiative_id: Mapped[str] = mapped_column(
        ForeignKey("initiatives.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False), default=EntityStatus.DRAFT, nullable=False
    )
    risk_tier: Mapped[RiskTier] = mapped_column(Enum(RiskTier, native_enum=False), nullable=False)
    production: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    initiative: Mapped[Initiative] = relationship(back_populates="systems")
    models: Mapped[list["ModelAsset"]] = relationship(back_populates="ai_system", lazy="selectin")
    agents: Mapped[list["Agent"]] = relationship(back_populates="ai_system", lazy="selectin")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="ai_system", lazy="selectin")


class ModelAsset(ReviewableAssetMixin, VersionedMixin, Base):
    """Versioned model registered within an AI system."""

    __tablename__ = "model_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ai_system_id: Mapped[str] = mapped_column(
        ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(200), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    routing_group: Mapped[str] = mapped_column(String(100), nullable=False)
    deployment_region: Mapped[str] = mapped_column(String(100), nullable=False)
    approved_use_cases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    prohibited_use_cases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allowed_data_classes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False), default=EntityStatus.DRAFT, nullable=False
    )
    evaluation_baseline: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    deprecation_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ai_system: Mapped[AISystem] = relationship(back_populates="models")


class Agent(ReviewableAssetMixin, VersionedMixin, Base):
    """Governed agent with explicit tools, permissions, and limits."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ai_system_id: Mapped[str] = mapped_column(
        ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(100), nullable=False)
    deployment_region: Mapped[str] = mapped_column(String(100), nullable=False)
    autonomy_level: Mapped[AutonomyLevel] = mapped_column(
        Enum(AutonomyLevel, native_enum=False), nullable=False
    )
    allowed_models: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    max_cost: Mapped[float | None] = mapped_column(Float)
    max_runtime_seconds: Mapped[int | None] = mapped_column(Integer)
    human_approval_points: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    kill_switch_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    kill_switch_engaged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    kill_switch_engaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kill_switch_engaged_by: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False), default=EntityStatus.DRAFT, nullable=False
    )

    ai_system: Mapped[AISystem] = relationship(back_populates="agents")


class RuntimeControlTransitionEntry(Base):
    """Monotonic durable transition projected to runtime enforcement storage."""

    __tablename__ = "runtime_control_transitions"
    __table_args__ = (
        CheckConstraint("control_epoch > 0", name="ck_runtime_control_epoch_positive"),
        CheckConstraint(
            "revoked_through_agent_version > 0",
            name="ck_runtime_control_revoked_version_positive",
        ),
        CheckConstraint(
            "previous_state IN ('active', 'inactive')",
            name="ck_runtime_control_previous_state",
        ),
        CheckConstraint(
            "target_state IN ('active', 'inactive')",
            name="ck_runtime_control_target_state",
        ),
        CheckConstraint(
            "status IN ('pending', 'applied')",
            name="ck_runtime_control_status",
        ),
        UniqueConstraint(
            "agent_id",
            "control_epoch",
            name="uq_runtime_control_agent_epoch",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id"), nullable=False, index=True
    )
    ai_system_id: Mapped[str] = mapped_column(
        ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    control_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_state: Mapped[str] = mapped_column(String(20), nullable=False)
    target_state: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    revoked_through_agent_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(200), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"))
    evidence_reference: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class ModelRoutingDecisionEntry(Base):
    """Durable lifecycle and provenance for one runtime routing attempt."""

    __tablename__ = "model_routing_decisions"
    __table_args__ = (
        UniqueConstraint(
            "router_decision_id",
            name="uq_model_routing_decisions_router_decision_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ai_system_id: Mapped[str] = mapped_column(
        ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    initiative_id: Mapped[str] = mapped_column(
        ForeignKey("initiatives.id"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(200), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    scope_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    workload: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    data_classification: Mapped[str] = mapped_column(String(20), nullable=False)
    context_tokens_estimated: Mapped[int] = mapped_column(Integer, nullable=False)
    max_output_tokens_estimated: Mapped[int] = mapped_column(Integer, nullable=False)
    structured_output_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    max_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    max_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    decision_source: Mapped[str | None] = mapped_column(String(40))
    router_decision_id: Mapped[str | None] = mapped_column(String(200))
    router_outcome: Mapped[str | None] = mapped_column(String(20))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selected_model_group: Mapped[str | None] = mapped_column(String(100))
    rejected_model_group: Mapped[str | None] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(Text)
    reason_code: Mapped[str | None] = mapped_column(String(100))
    observed_value: Mapped[str | None] = mapped_column(String(1000))
    required_value: Mapped[str | None] = mapped_column(String(1000))
    rejected_candidates: Mapped[list[dict[str, str]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    policy_id: Mapped[str | None] = mapped_column(String(200))
    policy_version: Mapped[str | None] = mapped_column(String(100))
    policy_digest: Mapped[str | None] = mapped_column(String(64), index=True)
    service_version: Mapped[str | None] = mapped_column(String(100))
    environment: Mapped[str | None] = mapped_column(String(100))
    violation_event_id: Mapped[str | None] = mapped_column(String(36), unique=True, index=True)
    violation_category: Mapped[str | None] = mapped_column(String(40), index=True)
    violation_code: Mapped[str | None] = mapped_column(String(100), index=True)
    violation_digest: Mapped[str | None] = mapped_column(String(64))
    violation_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Assessment(VersionedMixin, Base):
    """Versioned assessment answers and resulting risk classification."""

    __tablename__ = "assessments"
    __table_args__ = (
        UniqueConstraint(
            "initiative_id",
            "assessment_type",
            name="uq_assessment_initiative_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    initiative_id: Mapped[str] = mapped_column(
        ForeignKey("initiatives.id"), nullable=False, index=True
    )
    assessment_type: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False), default=EntityStatus.DRAFT, nullable=False
    )
    answers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    risk_score: Mapped[int | None] = mapped_column(Integer)
    risk_tier: Mapped[RiskTier | None] = mapped_column(Enum(RiskTier, native_enum=False))
    assessed_by: Mapped[str] = mapped_column(String(200), nullable=False)

    initiative: Mapped[Initiative] = relationship(back_populates="assessments")


class Approval(VersionedMixin, Base):
    """Approval gate assigned to one governance area."""

    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint(
            "initiative_id",
            "review_round",
            "area",
            name="uq_approval_initiative_round_area",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    initiative_id: Mapped[str] = mapped_column(
        ForeignKey("initiatives.id"), nullable=False, index=True
    )
    review_submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("review_submissions.id"), index=True
    )
    review_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    area: Mapped[ApprovalArea] = mapped_column(
        Enum(ApprovalArea, native_enum=False), nullable=False
    )
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, native_enum=False), nullable=False
    )
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(200))
    comments: Mapped[str | None] = mapped_column(Text)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    initiative: Mapped[Initiative] = relationship(back_populates="approvals")
    review_submission: Mapped["ReviewSubmission | None"] = relationship(back_populates="approvals")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="approval")


class ReviewSubmission(VersionedMixin, Base):
    """Immutable submitted snapshot plus the mutable outcome of one review round."""

    __tablename__ = "review_submissions"
    __table_args__ = (
        UniqueConstraint(
            "initiative_id",
            "review_round",
            name="uq_review_submission_initiative_round",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    initiative_id: Mapped[str] = mapped_column(
        ForeignKey("initiatives.id"), nullable=False, index=True
    )
    review_round: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False), nullable=False
    )
    submitted_by: Mapped[str] = mapped_column(String(200), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision_summary: Mapped[str] = mapped_column(Text, nullable=False)
    policy_id: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_tier: Mapped[RiskTier] = mapped_column(Enum(RiskTier, native_enum=False), nullable=False)
    initiative_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    assessment_snapshots: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)

    initiative: Mapped[Initiative] = relationship(back_populates="review_submissions")
    approvals: Mapped[list[Approval]] = relationship(back_populates="review_submission")


class Evidence(VersionedMixin, Base):
    """Evidence reference and digest supporting a governance decision."""

    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    initiative_id: Mapped[str] = mapped_column(
        ForeignKey("initiatives.id"), nullable=False, index=True
    )
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"), index=True)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    supplied_by: Mapped[str] = mapped_column(String(200), nullable=False)
    trusted_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    scan_status: Mapped[str] = mapped_column(String(50), default="not_applicable", nullable=False)
    scanner: Mapped[str | None] = mapped_column(String(100))
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_bucket: Mapped[str | None] = mapped_column(String(255))
    storage_key: Mapped[str | None] = mapped_column(String(1024))

    approval: Mapped[Approval | None] = relationship(back_populates="evidence")


class Incident(VersionedMixin, Base):
    """Operational incident associated with an AI system."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ai_system_id: Mapped[str] = mapped_column(
        ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[RiskTier] = mapped_column(Enum(RiskTier, native_enum=False), nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, native_enum=False), default=IncidentStatus.OPEN, nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(200), nullable=False)
    containment: Mapped[str | None] = mapped_column(Text)
    remediation_owner_id: Mapped[str | None] = mapped_column(String(200))
    remediation_description: Mapped[str | None] = mapped_column(Text)
    remediation_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ai_system: Mapped[AISystem] = relationship(back_populates="incidents")
    exceptions: Mapped[list["PolicyException"]] = relationship(
        back_populates="incident", lazy="selectin"
    )


class PolicyException(VersionedMixin, Base):
    """Temporary, expiring, independently-approved exception to a governance control."""

    __tablename__ = "policy_exceptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    ai_system_id: Mapped[str] = mapped_column(
        ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    requested_by: Mapped[str] = mapped_column(String(200), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    scope_description: Mapped[str] = mapped_column(Text, nullable=False)
    compensating_controls: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[ExceptionStatus] = mapped_column(
        Enum(ExceptionStatus, native_enum=False), default=ExceptionStatus.PENDING, nullable=False
    )
    decided_by: Mapped[str | None] = mapped_column(String(200))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)

    incident: Mapped[Incident] = relationship(back_populates="exceptions")


class InternationalProcessing(VersionedMixin, Base):
    """Cross-border processing record and its safeguards."""

    __tablename__ = "international_processing"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    initiative_id: Mapped[str] = mapped_column(
        ForeignKey("initiatives.id"), nullable=False, index=True
    )
    data_categories: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_country: Mapped[str] = mapped_column(String(100), nullable=False)
    inference_countries: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    storage_regions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    log_regions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    subprocessors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    transfer_mechanism: Mapped[str | None] = mapped_column(String(200))
    legal_basis: Mapped[str | None] = mapped_column(String(200))
    safeguards: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    residual_risk: Mapped[RiskTier | None] = mapped_column(Enum(RiskTier, native_enum=False))
    privacy_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DirectoryAuthorizationCacheEntry(VersionedMixin, Base):
    """Shared, content-minimized authorization snapshot or invalidation marker."""

    __tablename__ = "directory_authorization_cache"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "object_id",
            name="uq_directory_authorization_cache_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    catalog_id: Mapped[str | None] = mapped_column(String(100))
    catalog_version: Mapped[str | None] = mapped_column(String(50))
    catalog_digest: Mapped[str | None] = mapped_column(String(64), index=True)
    approval_areas: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    matched_mapping_ids: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    source_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    original_group_resolution_source: Mapped[str | None] = mapped_column(String(50))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )


class DirectoryAccessRestrictionEntry(VersionedMixin, Base):
    """Current emergency platform-access state for one Entra identity."""

    __tablename__ = "directory_access_restrictions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "object_id",
            name="uq_directory_access_restrictions_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class AuditEvent(Base):
    """Append-only event linked into a tamper-evident hash chain."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    entity_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
