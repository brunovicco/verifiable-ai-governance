"""Add shared directory-authorization snapshots and invalidation markers.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the disposable, content-minimized authorization cache table."""
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "directory_authorization_cache" not in tables:
        op.create_table(
            "directory_authorization_cache",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("object_id", sa.String(length=36), nullable=False),
            sa.Column("catalog_id", sa.String(length=100)),
            sa.Column("catalog_version", sa.String(length=50)),
            sa.Column("catalog_digest", sa.String(length=64)),
            sa.Column("approval_areas", sa.JSON(), nullable=False),
            sa.Column("matched_mapping_ids", sa.JSON(), nullable=False),
            sa.Column("source_types", sa.JSON(), nullable=False),
            sa.Column("original_group_resolution_source", sa.String(length=50)),
            sa.Column("resolved_at", sa.DateTime(timezone=True)),
            sa.Column("expires_at", sa.DateTime(timezone=True)),
            sa.Column("invalidated_at", sa.DateTime(timezone=True)),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "tenant_id",
                "object_id",
                name="uq_directory_authorization_cache_identity",
            ),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_directory_authorization_cache_catalog_digest "
        "ON directory_authorization_cache (catalog_digest)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_directory_authorization_cache_expires_at "
        "ON directory_authorization_cache (expires_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_directory_authorization_cache_invalidated_at "
        "ON directory_authorization_cache (invalidated_at)"
    )


def downgrade() -> None:
    """Drop only disposable cache data and its invalidation markers."""
    op.drop_table("directory_authorization_cache")
