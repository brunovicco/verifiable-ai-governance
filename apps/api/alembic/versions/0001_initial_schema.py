"""Initial governance inventory schema.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# The original ORM used non-native SQLAlchemy Enums. On PostgreSQL those columns
# materialized as VARCHAR sized from the historical enum member names. Pinning the
# physical types here keeps revision 0001 independent from today's domain enums.
DECISION_IMPACT = sa.String(length=16)
DATA_CLASSIFICATION = sa.String(length=12)
AUTONOMY_LEVEL = sa.String(length=23)
HOSTING_MODEL = sa.String(length=13)
ENTITY_STATUS = sa.String(length=12)
RISK_TIER = sa.String(length=8)
APPROVAL_AREA = sa.String(length=14)
APPROVAL_STATUS = sa.String(length=12)


def _versioned_columns() -> tuple[sa.Column, ...]:
    """Return the columns present on every mutable entity in revision 0001."""
    return (
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    """Create only the schema that belonged to the initial revision."""
    op.create_table(
        "initiatives",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("business_owner_id", sa.String(length=200), nullable=False),
        sa.Column("business_area", sa.String(length=200), nullable=False),
        sa.Column("intended_users", sa.Text(), nullable=False),
        sa.Column("decision_impact", DECISION_IMPACT, nullable=False),
        sa.Column("data_classification", DATA_CLASSIFICATION, nullable=False),
        sa.Column("autonomy_level", AUTONOMY_LEVEL, nullable=False),
        sa.Column("hosting_model", HOSTING_MODEL, nullable=False),
        sa.Column("affects_rights", sa.Boolean(), nullable=False),
        sa.Column("executes_actions", sa.Boolean(), nullable=False),
        sa.Column("personal_data", sa.Boolean(), nullable=False),
        sa.Column("sensitive_data", sa.Boolean(), nullable=False),
        sa.Column("children_data", sa.Boolean(), nullable=False),
        sa.Column("external_facing", sa.Boolean(), nullable=False),
        sa.Column("regulated_context", sa.Boolean(), nullable=False),
        sa.Column("international_processing", sa.Boolean(), nullable=False),
        sa.Column("inference_countries", sa.JSON(), nullable=False),
        sa.Column("uses_rag", sa.Boolean(), nullable=False),
        sa.Column("uses_agents", sa.Boolean(), nullable=False),
        sa.Column("uses_mcp", sa.Boolean(), nullable=False),
        sa.Column("uses_custom_model", sa.Boolean(), nullable=False),
        sa.Column("status", ENTITY_STATUS, nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_tier", RISK_TIER, nullable=False),
        sa.Column("policy_id", sa.String(length=100), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("required_documents", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        *_versioned_columns(),
    )
    op.create_index(
        "ix_initiatives_business_owner_id",
        "initiatives",
        ["business_owner_id"],
    )

    op.create_table(
        "ai_systems",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "initiative_id",
            sa.String(length=36),
            sa.ForeignKey("initiatives.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.String(length=200), nullable=False),
        sa.Column("status", ENTITY_STATUS, nullable=False),
        sa.Column("risk_tier", RISK_TIER, nullable=False),
        sa.Column("production", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_versioned_columns(),
    )
    op.create_index("ix_ai_systems_initiative_id", "ai_systems", ["initiative_id"])

    op.create_table(
        "model_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "ai_system_id",
            sa.String(length=36),
            sa.ForeignKey("ai_systems.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=200), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("deployment_region", sa.String(length=100), nullable=False),
        sa.Column("approved_use_cases", sa.JSON(), nullable=False),
        sa.Column("prohibited_use_cases", sa.JSON(), nullable=False),
        sa.Column("allowed_data_classes", sa.JSON(), nullable=False),
        sa.Column("status", ENTITY_STATUS, nullable=False),
        sa.Column("evaluation_baseline", sa.JSON(), nullable=False),
        sa.Column("deprecation_date", sa.DateTime(timezone=True)),
        *_versioned_columns(),
    )
    op.create_index("ix_model_assets_ai_system_id", "model_assets", ["ai_system_id"])

    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "ai_system_id",
            sa.String(length=36),
            sa.ForeignKey("ai_systems.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.String(length=200), nullable=False),
        sa.Column("autonomy_level", AUTONOMY_LEVEL, nullable=False),
        sa.Column("allowed_models", sa.JSON(), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("max_cost", sa.Float()),
        sa.Column("max_runtime_seconds", sa.Integer()),
        sa.Column("human_approval_points", sa.JSON(), nullable=False),
        sa.Column("kill_switch_enabled", sa.Boolean(), nullable=False),
        sa.Column("status", ENTITY_STATUS, nullable=False),
        *_versioned_columns(),
    )
    op.create_index("ix_agents_ai_system_id", "agents", ["ai_system_id"])

    op.create_table(
        "assessments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "initiative_id",
            sa.String(length=36),
            sa.ForeignKey("initiatives.id"),
            nullable=False,
        ),
        sa.Column("assessment_type", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("status", ENTITY_STATUS, nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("risk_score", sa.Integer()),
        sa.Column("risk_tier", RISK_TIER),
        sa.Column("assessed_by", sa.String(length=200), nullable=False),
        *_versioned_columns(),
    )
    op.create_index("ix_assessments_initiative_id", "assessments", ["initiative_id"])

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "initiative_id",
            sa.String(length=36),
            sa.ForeignKey("initiatives.id"),
            nullable=False,
        ),
        sa.Column("area", APPROVAL_AREA, nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", APPROVAL_STATUS, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_by", sa.String(length=200)),
        sa.Column("comments", sa.Text()),
        *_versioned_columns(),
        sa.UniqueConstraint(
            "initiative_id",
            "area",
            name="uq_approval_initiative_area",
        ),
    )
    op.create_index("ix_approvals_initiative_id", "approvals", ["initiative_id"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "initiative_id",
            sa.String(length=36),
            sa.ForeignKey("initiatives.id"),
            nullable=False,
        ),
        sa.Column("approval_id", sa.String(length=36), sa.ForeignKey("approvals.id")),
        sa.Column("kind", sa.String(length=100), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("supplied_by", sa.String(length=200), nullable=False),
        sa.Column("trusted_source", sa.Boolean(), nullable=False),
        *_versioned_columns(),
    )
    op.create_index("ix_evidence_initiative_id", "evidence", ["initiative_id"])
    op.create_index("ix_evidence_approval_id", "evidence", ["approval_id"])

    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "ai_system_id",
            sa.String(length=36),
            sa.ForeignKey("ai_systems.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_id", sa.String(length=200), nullable=False),
        sa.Column("containment", sa.Text()),
        *_versioned_columns(),
    )
    op.create_index("ix_incidents_ai_system_id", "incidents", ["ai_system_id"])

    op.create_table(
        "international_processing",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "initiative_id",
            sa.String(length=36),
            sa.ForeignKey("initiatives.id"),
            nullable=False,
        ),
        sa.Column("data_categories", sa.JSON(), nullable=False),
        sa.Column("source_country", sa.String(length=100), nullable=False),
        sa.Column("inference_countries", sa.JSON(), nullable=False),
        sa.Column("storage_regions", sa.JSON(), nullable=False),
        sa.Column("log_regions", sa.JSON(), nullable=False),
        sa.Column("subprocessors", sa.JSON(), nullable=False),
        sa.Column("transfer_mechanism", sa.String(length=200)),
        sa.Column("legal_basis", sa.String(length=200)),
        sa.Column("safeguards", sa.JSON(), nullable=False),
        sa.Column("residual_risk", RISK_TIER),
        sa.Column("privacy_approved", sa.Boolean(), nullable=False),
        *_versioned_columns(),
    )
    op.create_index(
        "ix_international_processing_initiative_id",
        "international_processing",
        ["initiative_id"],
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("entity_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64)),
        sa.Column("event_hash", sa.String(length=64), nullable=False, unique=True),
    )
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])


def downgrade() -> None:
    """Drop only objects owned by the initial revision, in dependency order."""
    op.drop_table("audit_events")
    op.drop_table("international_processing")
    op.drop_table("incidents")
    op.drop_table("evidence")
    op.drop_table("approvals")
    op.drop_table("assessments")
    op.drop_table("agents")
    op.drop_table("model_assets")
    op.drop_table("ai_systems")
    op.drop_table("initiatives")
