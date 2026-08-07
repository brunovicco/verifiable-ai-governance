"""Require one current assessment per definition and initiative.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the database invariant used by assessment upsert use cases."""
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_assessment_initiative_type "
        "ON assessments (initiative_id, assessment_type)"
    )


def downgrade() -> None:
    """Remove the assessment definition uniqueness invariant."""
    op.execute("ALTER TABLE assessments DROP CONSTRAINT IF EXISTS uq_assessment_initiative_type")
    op.execute("DROP INDEX IF EXISTS uq_assessment_initiative_type")
