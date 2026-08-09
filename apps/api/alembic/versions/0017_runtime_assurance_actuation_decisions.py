"""Add governed Runtime Assurance actuation decision evidence.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create append-only terminal human actuation decisions."""
    op.create_table(
        "runtime_assurance_actuation_decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_actuation_requests.id"),
            nullable=False,
        ),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("approval_area", sa.String(length=40), nullable=False),
        sa.Column("decided_by", sa.String(length=200), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "request_id",
            name="uq_runtime_assurance_actuation_decision_request",
        ),
        sa.CheckConstraint(
            "schema_version = '1.0'",
            name="ck_runtime_assurance_actuation_decision_schema",
        ),
        sa.CheckConstraint(
            "action = 'engage_kill_switch'",
            name="ck_runtime_assurance_actuation_decision_action",
        ),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_runtime_assurance_actuation_decision_outcome",
        ),
        sa.CheckConstraint(
            "approval_area = 'security'",
            name="ck_runtime_assurance_actuation_decision_area",
        ),
        sa.CheckConstraint(
            "version = 1",
            name="ck_runtime_assurance_actuation_decision_version",
        ),
    )
    op.create_index(
        "ix_runtime_assurance_actuation_decision_digest",
        "runtime_assurance_actuation_decisions",
        ["decision_digest"],
    )
    op.create_index(
        "ix_runtime_assurance_actuation_decision_actor_time",
        "runtime_assurance_actuation_decisions",
        ["decided_by", "decided_at"],
    )


def downgrade() -> None:
    """Remove governed Runtime Assurance actuation decision evidence."""
    op.drop_index(
        "ix_runtime_assurance_actuation_decision_actor_time",
        table_name="runtime_assurance_actuation_decisions",
    )
    op.drop_index(
        "ix_runtime_assurance_actuation_decision_digest",
        table_name="runtime_assurance_actuation_decisions",
    )
    op.drop_table("runtime_assurance_actuation_decisions")
