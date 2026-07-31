from enum import StrEnum


class RiskTier(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionImpact(StrEnum):
    INFORMATIONAL = "informational"
    OPERATIONAL = "operational"
    MATERIAL = "material"
    RIGHTS_OR_SAFETY = "rights_or_safety"


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class AutonomyLevel(StrEnum):
    A0_INFORMATION = "a0_information"
    A1_RECOMMENDATION = "a1_recommendation"
    A2_PREPARE_FOR_APPROVAL = "a2_prepare_for_approval"
    A3_REVERSIBLE_ACTIONS = "a3_reversible_actions"
    A4_HIGH_IMPACT_ACTIONS = "a4_high_impact_actions"
    A5_HIGH_AUTONOMY = "a5_high_autonomy"


class HostingModel(StrEnum):
    SAAS = "saas"
    CLOUD_MANAGED = "cloud_managed"
    SELF_HOSTED = "self_hosted"
    HYBRID = "hybrid"


class ApprovalArea(StrEnum):
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
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class EntityStatus(StrEnum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"
