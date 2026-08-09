"""Add deterministic advisory runtime-response recommendation evidence.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create append-only Runtime Assurance response recommendation evidence."""
    op.create_table(
        "runtime_assurance_response_recommendations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "promotion_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_incident_promotions.id"),
            nullable=False,
        ),
        sa.Column(
            "evaluation_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_evaluations.id"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(length=36),
            sa.ForeignKey("agents.id"),
            nullable=False,
        ),
        sa.Column(
            "ai_system_id",
            sa.String(length=36),
            sa.ForeignKey("ai_systems.id"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            sa.String(length=36),
            sa.ForeignKey("incidents.id"),
            nullable=False,
        ),
        sa.Column("breach_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("policy_id", sa.String(length=100), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("policy_digest", sa.String(length=64), nullable=False),
        sa.Column("incident_status", sa.String(length=30), nullable=False),
        sa.Column("incident_severity", sa.String(length=20), nullable=False),
        sa.Column("incident_version", sa.Integer(), nullable=False),
        sa.Column("kill_switch_enabled", sa.Boolean(), nullable=False),
        sa.Column("kill_switch_engaged", sa.Boolean(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("rationale_codes", sa.JSON(), nullable=False),
        sa.Column("advisory_only", sa.Boolean(), nullable=False),
        sa.Column("generated_by", sa.String(length=200), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recommendation_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "promotion_id",
            name="uq_runtime_assurance_response_recommendation_promotion",
        ),
        sa.CheckConstraint(
            "incident_status IN ('open', 'contained', 'remediating')",
            name="ck_runtime_assurance_response_incident_status",
        ),
        sa.CheckConstraint(
            "incident_severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_runtime_assurance_response_incident_severity",
        ),
        sa.CheckConstraint(
            "incident_version > 0",
            name="ck_runtime_assurance_response_incident_version",
        ),
        sa.CheckConstraint(
            "advisory_only = true",
            name="ck_runtime_assurance_response_advisory_only",
        ),
        sa.CheckConstraint(
            "version = 1",
            name="ck_runtime_assurance_response_version",
        ),
    )
    op.create_index(
        "ix_runtime_assurance_response_incident",
        "runtime_assurance_response_recommendations",
        ["incident_id"],
    )
    op.create_index(
        "ix_runtime_assurance_response_agent_time",
        "runtime_assurance_response_recommendations",
        ["agent_id", "generated_at"],
    )
    op.create_index(
        "ix_runtime_assurance_response_digest",
        "runtime_assurance_response_recommendations",
        ["recommendation_digest"],
    )


def downgrade() -> None:
    """Remove Runtime Assurance response recommendation evidence."""
    op.drop_index(
        "ix_runtime_assurance_response_digest",
        table_name="runtime_assurance_response_recommendations",
    )
    op.drop_index(
        "ix_runtime_assurance_response_agent_time",
        table_name="runtime_assurance_response_recommendations",
    )
    op.drop_index(
        "ix_runtime_assurance_response_incident",
        table_name="runtime_assurance_response_recommendations",
    )
    op.drop_table("runtime_assurance_response_recommendations")
