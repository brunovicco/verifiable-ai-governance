"""Add incident remediation, kill-switch actions, and temporary exceptions.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add remediation fields, kill-switch action columns, and policy exceptions."""
    incident_columns = _column_names("incidents")
    for column_name, column in (
        ("remediation_owner_id", sa.Column("remediation_owner_id", sa.String(length=200))),
        ("remediation_description", sa.Column("remediation_description", sa.Text())),
        ("remediation_due_at", sa.Column("remediation_due_at", sa.DateTime(timezone=True))),
        ("resolved_at", sa.Column("resolved_at", sa.DateTime(timezone=True))),
    ):
        if column_name not in incident_columns:
            op.add_column("incidents", column)

    agent_columns = _column_names("agents")
    if "kill_switch_engaged" not in agent_columns:
        op.add_column(
            "agents",
            sa.Column(
                "kill_switch_engaged",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        op.alter_column("agents", "kill_switch_engaged", server_default=None)
    if "kill_switch_engaged_at" not in agent_columns:
        op.add_column("agents", sa.Column("kill_switch_engaged_at", sa.DateTime(timezone=True)))
    if "kill_switch_engaged_by" not in agent_columns:
        op.add_column("agents", sa.Column("kill_switch_engaged_by", sa.String(length=200)))

    if "policy_exceptions" not in _table_names():
        op.create_table(
            "policy_exceptions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "incident_id",
                sa.String(length=36),
                sa.ForeignKey("incidents.id"),
                nullable=False,
            ),
            sa.Column(
                "ai_system_id",
                sa.String(length=36),
                sa.ForeignKey("ai_systems.id"),
                nullable=False,
            ),
            sa.Column("requested_by", sa.String(length=200), nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("purpose", sa.Text(), nullable=False),
            sa.Column("scope_description", sa.Text(), nullable=False),
            sa.Column("compensating_controls", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("decided_by", sa.String(length=200)),
            sa.Column("decided_at", sa.DateTime(timezone=True)),
            sa.Column("decision_reason", sa.Text()),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        for column in ("incident_id", "ai_system_id", "requested_at", "expires_at", "status"):
            op.create_index(
                f"ix_policy_exceptions_{column}",
                "policy_exceptions",
                [column],
            )


def downgrade() -> None:
    """Remove policy exceptions, kill-switch action columns, and remediation fields."""
    if "policy_exceptions" in _table_names():
        op.drop_table("policy_exceptions")

    agent_columns = _column_names("agents")
    for column_name in (
        "kill_switch_engaged_by",
        "kill_switch_engaged_at",
        "kill_switch_engaged",
    ):
        if column_name in agent_columns:
            op.drop_column("agents", column_name)

    incident_columns = _column_names("incidents")
    for column_name in (
        "resolved_at",
        "remediation_due_at",
        "remediation_description",
        "remediation_owner_id",
    ):
        if column_name in incident_columns:
            op.drop_column("incidents", column_name)


def _table_names() -> set[str]:
    """Return current table names for bootstrap-compatible migrations."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    """Return current column names for bootstrap-compatible migrations."""
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}
