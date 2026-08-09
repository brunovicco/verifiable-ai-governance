"""Add governed Runtime Assurance actuation approval-request evidence.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create append-only actuation-request genesis evidence."""
    op.create_table(
        "runtime_assurance_actuation_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column(
            "recommendation_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_response_recommendations.id"),
            nullable=False,
        ),
        sa.Column("recommendation_digest", sa.String(length=64), nullable=False),
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
            "incident_id",
            sa.String(length=36),
            sa.ForeignKey("incidents.id"),
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
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.String(length=200), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "recommendation_id",
            "action",
            name="uq_runtime_assurance_actuation_request_recommendation_action",
        ),
        sa.CheckConstraint(
            "schema_version = '1.0'",
            name="ck_runtime_assurance_actuation_request_schema",
        ),
        sa.CheckConstraint(
            "action = 'engage_kill_switch'",
            name="ck_runtime_assurance_actuation_request_action",
        ),
        sa.CheckConstraint(
            "state = 'pending'",
            name="ck_runtime_assurance_actuation_request_state",
        ),
        sa.CheckConstraint(
            "version = 1",
            name="ck_runtime_assurance_actuation_request_version",
        ),
    )
    op.create_index(
        "ix_runtime_assurance_actuation_request_agent_time",
        "runtime_assurance_actuation_requests",
        ["agent_id", "requested_at"],
    )
    op.create_index(
        "ix_runtime_assurance_actuation_request_incident",
        "runtime_assurance_actuation_requests",
        ["incident_id"],
    )
    op.create_index(
        "ix_runtime_assurance_actuation_request_system",
        "runtime_assurance_actuation_requests",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_runtime_assurance_actuation_request_digest",
        "runtime_assurance_actuation_requests",
        ["request_digest"],
    )


def downgrade() -> None:
    """Remove governed actuation-request evidence."""
    op.drop_index(
        "ix_runtime_assurance_actuation_request_digest",
        table_name="runtime_assurance_actuation_requests",
    )
    op.drop_index(
        "ix_runtime_assurance_actuation_request_system",
        table_name="runtime_assurance_actuation_requests",
    )
    op.drop_index(
        "ix_runtime_assurance_actuation_request_incident",
        table_name="runtime_assurance_actuation_requests",
    )
    op.drop_index(
        "ix_runtime_assurance_actuation_request_agent_time",
        table_name="runtime_assurance_actuation_requests",
    )
    op.drop_table("runtime_assurance_actuation_requests")
