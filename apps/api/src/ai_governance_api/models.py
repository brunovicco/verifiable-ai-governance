"""SQLAlchemy persistence models for governance aggregates and audit events."""

from datetime import UTC, datetime
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
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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

    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="initiative", cascade="all, delete-orphan", lazy="selectin"
    )
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="initiative")
    systems: Mapped[list["AISystem"]] = relationship(
        back_populates="initiative", lazy="selectin"
    )


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
    models: Mapped[list["ModelAsset"]] = relationship(
        back_populates="ai_system", lazy="selectin"
    )
    agents: Mapped[list["Agent"]] = relationship(
        back_populates="ai_system", lazy="selectin"
    )


class ModelAsset(VersionedMixin, Base):
    """Versioned model registered within an AI system."""

    __tablename__ = "model_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ai_system_id: Mapped[str] = mapped_column(
        ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(200), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
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


class Agent(VersionedMixin, Base):
    """Governed agent with explicit tools, permissions, and limits."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ai_system_id: Mapped[str] = mapped_column(
        ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(200), nullable=False)
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
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False), default=EntityStatus.DRAFT, nullable=False
    )

    ai_system: Mapped[AISystem] = relationship(back_populates="agents")


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
        UniqueConstraint("initiative_id", "area", name="uq_approval_initiative_area"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    initiative_id: Mapped[str] = mapped_column(
        ForeignKey("initiatives.id"), nullable=False, index=True
    )
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

    initiative: Mapped[Initiative] = relationship(back_populates="approvals")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="approval")


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
    scan_status: Mapped[str] = mapped_column(
        String(50), default="not_applicable", nullable=False
    )
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
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(200), nullable=False)
    containment: Mapped[str | None] = mapped_column(Text)


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
