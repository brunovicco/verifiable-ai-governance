"""Add governed policy-model-router decisions.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add logical model groups and durable routing decision evidence."""
    model_columns = _column_names("model_assets")
    if "routing_group" not in model_columns:
        op.add_column(
            "model_assets",
            sa.Column(
                "routing_group",
                sa.String(length=100),
                nullable=False,
                server_default="unassigned",
            ),
        )
        op.alter_column("model_assets", "routing_group", server_default=None)
        _invalidate_existing_asset_reviews()

    if "model_routing_decisions" not in _table_names():
        op.create_table(
            "model_routing_decisions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "ai_system_id",
                sa.String(length=36),
                sa.ForeignKey("ai_systems.id"),
                nullable=False,
            ),
            sa.Column(
                "initiative_id",
                sa.String(length=36),
                sa.ForeignKey("initiatives.id"),
                nullable=False,
            ),
            sa.Column(
                "agent_id",
                sa.String(length=36),
                sa.ForeignKey("agents.id"),
                nullable=False,
            ),
            sa.Column("requested_by", sa.String(length=200), nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("scope_digest", sa.String(length=64), nullable=False),
            sa.Column("workflow_id", sa.String(length=200), nullable=False),
            sa.Column("task_id", sa.String(length=200), nullable=False),
            sa.Column("workload", sa.String(length=100), nullable=False),
            sa.Column("risk_level", sa.String(length=20), nullable=False),
            sa.Column("data_classification", sa.String(length=20), nullable=False),
            sa.Column("context_tokens_estimated", sa.Integer(), nullable=False),
            sa.Column("max_output_tokens_estimated", sa.Integer(), nullable=False),
            sa.Column("structured_output_required", sa.Boolean(), nullable=False),
            sa.Column("max_latency_ms", sa.Integer(), nullable=False),
            sa.Column("max_cost_usd", sa.Numeric(18, 8), nullable=False),
            sa.Column("outcome", sa.String(length=30), nullable=False),
            sa.Column("decision_source", sa.String(length=40)),
            sa.Column("router_decision_id", sa.String(length=200)),
            sa.Column("router_outcome", sa.String(length=20)),
            sa.Column("decided_at", sa.DateTime(timezone=True)),
            sa.Column("selected_model_group", sa.String(length=100)),
            sa.Column("rejected_model_group", sa.String(length=100)),
            sa.Column("reason", sa.Text()),
            sa.Column("reason_code", sa.String(length=100)),
            sa.Column("observed_value", sa.String(length=1000)),
            sa.Column("required_value", sa.String(length=1000)),
            sa.Column("rejected_candidates", sa.JSON(), nullable=False),
            sa.Column("policy_id", sa.String(length=200)),
            sa.Column("policy_version", sa.String(length=100)),
            sa.Column("policy_digest", sa.String(length=64)),
            sa.Column("service_version", sa.String(length=100)),
            sa.Column("environment", sa.String(length=100)),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "router_decision_id",
                name="uq_model_routing_decisions_router_decision_id",
            ),
        )
        for column in (
            "ai_system_id",
            "initiative_id",
            "agent_id",
            "requested_at",
            "workflow_id",
            "task_id",
            "outcome",
            "policy_digest",
        ):
            op.create_index(
                f"ix_model_routing_decisions_{column}",
                "model_routing_decisions",
                [column],
            )


def downgrade() -> None:
    """Remove routing evidence and the logical model group field."""
    if "model_routing_decisions" in _table_names():
        op.drop_table("model_routing_decisions")
    if "routing_group" in _column_names("model_assets"):
        op.drop_column("model_assets", "routing_group")


def _invalidate_existing_asset_reviews() -> None:
    """Fail closed because existing review digests did not bind routing groups."""
    for table_name in ("model_assets", "agents"):
        if "approved_scope_digest" not in _column_names(table_name):
            continue
        op.execute(
            sa.text(
                f"UPDATE {table_name} "
                "SET approved_scope_digest = NULL, reviewed_by = NULL, reviewed_at = NULL, "
                "next_review_at = NULL, review_reference = NULL, "
                "status = CASE WHEN lower(status) = 'retired' THEN status ELSE 'DRAFT' END"
            )
        )


def _table_names() -> set[str]:
    """Return current table names for bootstrap-compatible migrations."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    """Return current column names for bootstrap-compatible migrations."""
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}
