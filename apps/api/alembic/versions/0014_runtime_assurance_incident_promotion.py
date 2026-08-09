"""Add governed Runtime Assurance breach-to-incident promotion evidence.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_assurance_incident_promotions",
        sa.Column("id", sa.String(length=36), primary_key=True),
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
        sa.Column("disposition", sa.String(length=30), nullable=False),
        sa.Column("promoted_by", sa.String(length=200), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "evaluation_id",
            name="uq_runtime_assurance_incident_promotion_evaluation",
        ),
        sa.CheckConstraint(
            "disposition IN ('created', 'deduplicated', 'severity_escalated')",
            name="ck_runtime_assurance_incident_promotion_disposition",
        ),
        sa.CheckConstraint(
            "version = 1",
            name="ck_runtime_assurance_incident_promotion_version",
        ),
    )
    op.create_index(
        "ix_runtime_assurance_incident_promotion_agent_fingerprint",
        "runtime_assurance_incident_promotions",
        ["agent_id", "breach_fingerprint"],
    )
    op.create_index(
        "ix_runtime_assurance_incident_promotion_system",
        "runtime_assurance_incident_promotions",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_runtime_assurance_incident_promotion_incident",
        "runtime_assurance_incident_promotions",
        ["incident_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runtime_assurance_incident_promotion_incident",
        table_name="runtime_assurance_incident_promotions",
    )
    op.drop_index(
        "ix_runtime_assurance_incident_promotion_system",
        table_name="runtime_assurance_incident_promotions",
    )
    op.drop_index(
        "ix_runtime_assurance_incident_promotion_agent_fingerprint",
        table_name="runtime_assurance_incident_promotions",
    )
    op.drop_table("runtime_assurance_incident_promotions")
