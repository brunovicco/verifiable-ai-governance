"""Add governed scope reviews to model and agent registry assets.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

REVIEW_COLUMNS = (
    "approved_scope_digest",
    "reviewed_by",
    "reviewed_at",
    "next_review_at",
    "review_reference",
)


def upgrade() -> None:
    """Add semantic agent identity and review evidence to both asset tables."""
    _add_review_columns("model_assets")
    _add_review_columns("agents")

    agent_columns = _column_names("agents")
    if "agent_version" not in agent_columns:
        op.add_column(
            "agents",
            sa.Column(
                "agent_version",
                sa.String(length=100),
                nullable=False,
                server_default="unversioned",
            ),
        )
        op.alter_column("agents", "agent_version", server_default=None)
    if "deployment_region" not in agent_columns:
        op.add_column(
            "agents",
            sa.Column(
                "deployment_region",
                sa.String(length=100),
                nullable=False,
                server_default="unspecified",
            ),
        )
        op.alter_column("agents", "deployment_region", server_default=None)

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_model_assets_next_review_at "
        "ON model_assets (next_review_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agents_next_review_at "
        "ON agents (next_review_at)"
    )


def downgrade() -> None:
    """Remove review projections and semantic agent deployment fields."""
    op.execute("DROP INDEX IF EXISTS ix_model_assets_next_review_at")
    op.execute("DROP INDEX IF EXISTS ix_agents_next_review_at")
    for column in (*REVIEW_COLUMNS, "agent_version", "deployment_region"):
        if column in _column_names("agents"):
            op.drop_column("agents", column)
    for column in REVIEW_COLUMNS:
        if column in _column_names("model_assets"):
            op.drop_column("model_assets", column)


def _add_review_columns(table_name: str) -> None:
    """Add nullable current-review fields when a bootstrap did not create them."""
    columns = _column_names(table_name)
    definitions = {
        "approved_scope_digest": sa.Column(
            "approved_scope_digest",
            sa.String(length=64),
        ),
        "reviewed_by": sa.Column("reviewed_by", sa.String(length=200)),
        "reviewed_at": sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        "next_review_at": sa.Column("next_review_at", sa.DateTime(timezone=True)),
        "review_reference": sa.Column("review_reference", sa.String(length=100)),
    }
    for name, definition in definitions.items():
        if name not in columns:
            op.add_column(table_name, definition)


def _column_names(table_name: str) -> set[str]:
    """Return current column names for idempotent bootstrap compatibility."""
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }
