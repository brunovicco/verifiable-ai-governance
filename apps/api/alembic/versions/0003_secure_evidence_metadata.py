"""Add trusted upload metadata to evidence records.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable upload fields while preserving legacy URI-only evidence."""
    op.execute("ALTER TABLE evidence ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255)")
    op.execute("ALTER TABLE evidence ADD COLUMN IF NOT EXISTS content_type VARCHAR(100)")
    op.execute("ALTER TABLE evidence ADD COLUMN IF NOT EXISTS size_bytes INTEGER")
    op.execute(
        "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS scan_status VARCHAR(50) "
        "NOT NULL DEFAULT 'not_applicable'"
    )
    op.execute("ALTER TABLE evidence ADD COLUMN IF NOT EXISTS scanner VARCHAR(100)")
    op.execute(
        "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS scanned_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute("ALTER TABLE evidence ADD COLUMN IF NOT EXISTS storage_bucket VARCHAR(255)")
    op.execute("ALTER TABLE evidence ADD COLUMN IF NOT EXISTS storage_key VARCHAR(1024)")


def downgrade() -> None:
    """Remove uploaded evidence metadata without deleting legacy evidence rows."""
    op.execute("ALTER TABLE evidence DROP COLUMN IF EXISTS storage_key")
    op.execute("ALTER TABLE evidence DROP COLUMN IF EXISTS storage_bucket")
    op.execute("ALTER TABLE evidence DROP COLUMN IF EXISTS scanned_at")
    op.execute("ALTER TABLE evidence DROP COLUMN IF EXISTS scanner")
    op.execute("ALTER TABLE evidence DROP COLUMN IF EXISTS scan_status")
    op.execute("ALTER TABLE evidence DROP COLUMN IF EXISTS size_bytes")
    op.execute("ALTER TABLE evidence DROP COLUMN IF EXISTS content_type")
    op.execute("ALTER TABLE evidence DROP COLUMN IF EXISTS original_filename")
