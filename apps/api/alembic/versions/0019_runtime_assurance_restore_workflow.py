"""Add governed Runtime Assurance kill-switch restore workflow.

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable restore request, decision, and execution evidence."""
    op.create_table(
        "runtime_assurance_restore_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column(
            "source_execution_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_actuation_executions.id"),
            nullable=False,
        ),
        sa.Column("source_execution_digest", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column(
            "ai_system_id", sa.String(length=36), sa.ForeignKey("ai_systems.id"), nullable=False
        ),
        sa.Column(
            "incident_id",
            sa.String(length=36),
            sa.ForeignKey("incidents.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("remediation_digest", sa.String(length=64), nullable=False),
        sa.Column("incident_status", sa.String(length=30), nullable=False),
        sa.Column("incident_version", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(length=200), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "source_execution_id",
            "remediation_digest",
            name="uq_ra_restore_req_execution_remediation",
        ),
        sa.CheckConstraint("schema_version = '1.0'", name="ck_ra_restore_req_schema"),
        sa.CheckConstraint("action = 'restore_kill_switch'", name="ck_ra_restore_req_action"),
        sa.CheckConstraint("state = 'pending'", name="ck_ra_restore_req_state"),
        sa.CheckConstraint(
            "incident_status IN ('remediating', 'closed')",
            name="ck_ra_restore_req_incident_status",
        ),
        sa.CheckConstraint("incident_version > 0", name="ck_ra_restore_req_incident_version"),
        sa.CheckConstraint("version = 1", name="ck_ra_restore_req_version"),
    )
    op.create_index(
        "ix_ra_restore_req_agent_time",
        "runtime_assurance_restore_requests",
        ["agent_id", "requested_at"],
    )
    op.create_index(
        "ix_ra_restore_req_digest",
        "runtime_assurance_restore_requests",
        ["request_digest"],
    )

    op.create_table(
        "runtime_assurance_restore_decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_restore_requests.id"),
            nullable=False,
        ),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "source_execution_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_actuation_executions.id"),
            nullable=False,
        ),
        sa.Column("source_execution_digest", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("approval_area", sa.String(length=40), nullable=False),
        sa.Column("decided_by", sa.String(length=200), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("request_id", name="uq_ra_restore_dec_request"),
        sa.CheckConstraint("schema_version = '1.0'", name="ck_ra_restore_dec_schema"),
        sa.CheckConstraint("action = 'restore_kill_switch'", name="ck_ra_restore_dec_action"),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_ra_restore_dec_outcome",
        ),
        sa.CheckConstraint("approval_area = 'security'", name="ck_ra_restore_dec_area"),
        sa.CheckConstraint("version = 1", name="ck_ra_restore_dec_version"),
    )
    op.create_index(
        "ix_ra_restore_dec_digest",
        "runtime_assurance_restore_decisions",
        ["decision_digest"],
    )

    op.create_table(
        "runtime_assurance_restore_executions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column(
            "decision_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_restore_decisions.id"),
            nullable=False,
        ),
        sa.Column("decision_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "request_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_restore_requests.id"),
            nullable=False,
        ),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "source_execution_id",
            sa.String(length=36),
            sa.ForeignKey("runtime_assurance_actuation_executions.id"),
            nullable=False,
        ),
        sa.Column("source_execution_digest", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column(
            "ai_system_id", sa.String(length=36), sa.ForeignKey("ai_systems.id"), nullable=False
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
        sa.UniqueConstraint("decision_id", name="uq_ra_restore_exec_decision"),
        sa.UniqueConstraint("runtime_transition_id", name="uq_ra_restore_exec_transition"),
        sa.CheckConstraint("schema_version = '1.0'", name="ck_ra_restore_exec_schema"),
        sa.CheckConstraint("action = 'restore_kill_switch'", name="ck_ra_restore_exec_action"),
        sa.CheckConstraint(
            "previous_state = 'active' AND target_state = 'inactive'",
            name="ck_ra_restore_exec_states",
        ),
        sa.CheckConstraint("control_epoch > 0", name="ck_ra_restore_exec_epoch"),
        sa.CheckConstraint(
            "revoked_through_agent_version > 0",
            name="ck_ra_restore_exec_revoked",
        ),
        sa.CheckConstraint(
            "resulting_agent_version = revoked_through_agent_version + 1",
            name="ck_ra_restore_exec_agent_version",
        ),
        sa.CheckConstraint("version = 1", name="ck_ra_restore_exec_version"),
    )
    op.create_index(
        "ix_ra_restore_exec_digest",
        "runtime_assurance_restore_executions",
        ["execution_digest"],
    )
    op.create_index(
        "ix_ra_restore_exec_agent_time",
        "runtime_assurance_restore_executions",
        ["agent_id", "executed_at"],
    )


def downgrade() -> None:
    """Remove governed Runtime Assurance restore evidence."""
    op.drop_index(
        "ix_ra_restore_exec_agent_time",
        table_name="runtime_assurance_restore_executions",
    )
    op.drop_index("ix_ra_restore_exec_digest", table_name="runtime_assurance_restore_executions")
    op.drop_table("runtime_assurance_restore_executions")
    op.drop_index("ix_ra_restore_dec_digest", table_name="runtime_assurance_restore_decisions")
    op.drop_table("runtime_assurance_restore_decisions")
    op.drop_index("ix_ra_restore_req_digest", table_name="runtime_assurance_restore_requests")
    op.drop_index("ix_ra_restore_req_agent_time", table_name="runtime_assurance_restore_requests")
    op.drop_table("runtime_assurance_restore_requests")
