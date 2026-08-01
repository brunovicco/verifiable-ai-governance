"""Shared governance taxonomy values."""

from enum import StrEnum


class RiskTier(StrEnum):
    """Business-facing risk classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionImpact(StrEnum):
    """Materiality of decisions influenced by an AI initiative."""

    INFORMATIONAL = "informational"
    OPERATIONAL = "operational"
    MATERIAL = "material"
    RIGHTS_OR_SAFETY = "rights_or_safety"


class DataClassification(StrEnum):
    """Sensitivity classification for data handled by an initiative."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class AutonomyLevel(StrEnum):
    """Increasing levels of AI system action autonomy."""

    A0_INFORMATION = "a0_information"
    A1_RECOMMENDATION = "a1_recommendation"
    A2_PREPARE_FOR_APPROVAL = "a2_prepare_for_approval"
    A3_REVERSIBLE_ACTIONS = "a3_reversible_actions"
    A4_HIGH_IMPACT_ACTIONS = "a4_high_impact_actions"
    A5_HIGH_AUTONOMY = "a5_high_autonomy"


class HostingModel(StrEnum):
    """Deployment ownership model for an AI capability."""

    SAAS = "saas"
    CLOUD_MANAGED = "cloud_managed"
    SELF_HOSTED = "self_hosted"
    HYBRID = "hybrid"


class ApprovalArea(StrEnum):
    """Organizational functions participating in governance gates."""

    BUSINESS = "business"
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    INFRASTRUCTURE = "infrastructure"
    DEVOPS = "devops"
    PRIVACY = "privacy"
    LEGAL = "legal"
    COMPLIANCE = "compliance"
    DATA = "data"


class ApprovalStatus(StrEnum):
    """Lifecycle state of an approval gate."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class EntityStatus(StrEnum):
    """Shared lifecycle states for versioned governance entities."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"
