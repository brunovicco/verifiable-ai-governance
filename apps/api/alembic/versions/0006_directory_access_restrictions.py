"""Add persistent emergency access restrictions for Entra identities.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the current-state table used for immediate platform blocking."""
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "directory_access_restrictions" not in tables:
        op.create_table(
            "directory_access_restrictions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("object_id", sa.String(length=36), nullable=False),
            sa.Column("blocked", sa.Boolean(), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "tenant_id",
                "object_id",
                name="uq_directory_access_restrictions_identity",
            ),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_directory_access_restrictions_changed_at "
        "ON directory_access_restrictions (changed_at)"
    )


def downgrade() -> None:
    """Drop current restriction state while preserving audit events."""
    op.drop_table("directory_access_restrictions")
