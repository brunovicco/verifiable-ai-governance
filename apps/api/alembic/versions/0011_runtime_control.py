"""Add durable monotonic runtime-control transitions.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create transition evidence used to project emergency runtime state."""
    if "runtime_control_transitions" in _table_names():
        return
    op.create_table(
        "runtime_control_transitions",
        sa.Column("id", sa.String(length=36), primary_key=True),
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
        sa.Column("control_epoch", sa.Integer(), nullable=False),
        sa.Column("previous_state", sa.String(length=20), nullable=False),
        sa.Column("target_state", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revoked_through_agent_version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(length=200), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column(
            "incident_id",
            sa.String(length=36),
            sa.ForeignKey("incidents.id"),
        ),
        sa.Column("evidence_reference", sa.String(length=500)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("control_epoch > 0", name="ck_runtime_control_epoch_positive"),
        sa.CheckConstraint(
            "revoked_through_agent_version > 0",
            name="ck_runtime_control_revoked_version_positive",
        ),
        sa.CheckConstraint(
            "previous_state IN ('active', 'inactive')",
            name="ck_runtime_control_previous_state",
        ),
        sa.CheckConstraint(
            "target_state IN ('active', 'inactive')",
            name="ck_runtime_control_target_state",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'applied')",
            name="ck_runtime_control_status",
        ),
        sa.UniqueConstraint(
            "agent_id",
            "control_epoch",
            name="uq_runtime_control_agent_epoch",
        ),
    )
    op.create_index(
        "ix_runtime_control_transitions_agent_id",
        "runtime_control_transitions",
        ["agent_id"],
    )
    op.create_index(
        "ix_runtime_control_transitions_ai_system_id",
        "runtime_control_transitions",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_runtime_control_transitions_status",
        "runtime_control_transitions",
        ["status"],
    )
    op.create_index(
        "ix_runtime_control_transitions_requested_at",
        "runtime_control_transitions",
        ["requested_at"],
    )


def downgrade() -> None:
    """Remove runtime-control transition evidence."""
    if "runtime_control_transitions" in _table_names():
        op.drop_table("runtime_control_transitions")


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())
