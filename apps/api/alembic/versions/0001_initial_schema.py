"""Initial governance inventory schema.

Revision ID: 0001
Revises:
"""

from ai_governance_api.models import Base
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
