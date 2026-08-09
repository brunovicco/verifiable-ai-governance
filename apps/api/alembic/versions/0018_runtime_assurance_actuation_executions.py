"""Add governed Runtime Assurance actuation execution receipts.

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable receipts for applied governed Runtime Control actions."""
    op.create_table(
        "runtime_assurance_actuation_executions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column(
            "decision_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_actuation_decisions.id"),
            nullable=False,
        ),
        sa.Column("decision_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_actuation_requests.id"),
            nullable=False,
        ),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
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
        sa.Column(
            "runtime_transition_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_control_transitions.id"),
            nullable=False,
        ),
        sa.Column("control_epoch", sa.Integer(), nullable=False),
        sa.Column("previous_state", sa.String(length=20), nullable=False),
        sa.Column("target_state", sa.String(length=20), nullable=False),
        sa.Column("revoked_through_agent_version", sa.Integer(), nullable=False),
        sa.Column("resulting_agent_version", sa.Integer(), nullable=False),
        sa.Column("executed_by", sa.String(length=200), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execution_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "decision_id",
            name="uq_runtime_assurance_actuation_execution_decision",
        ),
        sa.UniqueConstraint(
            "runtime_transition_id",
            name="uq_runtime_assurance_actuation_execution_transition",
        ),
        sa.CheckConstraint(
            "schema_version = '1.0'",
            name="ck_runtime_assurance_actuation_execution_schema",
        ),
        sa.CheckConstraint(
            "action = 'engage_kill_switch'",
            name="ck_runtime_assurance_actuation_execution_action",
        ),
        sa.CheckConstraint(
            "previous_state = 'inactive' AND target_state = 'active'",
            name="ck_runtime_assurance_actuation_execution_states",
        ),
        sa.CheckConstraint(
            "control_epoch > 0",
            name="ck_runtime_assurance_actuation_execution_epoch",
        ),
        sa.CheckConstraint(
            "revoked_through_agent_version > 0",
            name="ck_runtime_assurance_actuation_execution_revoked",
        ),
        sa.CheckConstraint(
            "resulting_agent_version = revoked_through_agent_version + 1",
            name="ck_runtime_assurance_actuation_execution_agent_version",
        ),
        sa.CheckConstraint(
            "version = 1",
            name="ck_runtime_assurance_actuation_execution_version",
        ),
    )
    op.create_index(
        "ix_runtime_assurance_actuation_execution_digest",
        "runtime_assurance_actuation_executions",
        ["execution_digest"],
    )
    op.create_index(
        "ix_runtime_assurance_actuation_execution_agent_time",
        "runtime_assurance_actuation_executions",
        ["agent_id", "executed_at"],
    )
    op.create_index(
        "ix_runtime_assurance_actuation_execution_system",
        "runtime_assurance_actuation_executions",
        ["ai_system_id"],
    )


def downgrade() -> None:
    """Remove governed Runtime Assurance execution receipts."""
    op.drop_index(
        "ix_runtime_assurance_actuation_execution_system",
        table_name="runtime_assurance_actuation_executions",
    )
    op.drop_index(
        "ix_runtime_assurance_actuation_execution_agent_time",
        table_name="runtime_assurance_actuation_executions",
    )
    op.drop_index(
        "ix_runtime_assurance_actuation_execution_digest",
        table_name="runtime_assurance_actuation_executions",
    )
    op.drop_table("runtime_assurance_actuation_executions")
