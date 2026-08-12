"""Expand governance status columns for current lifecycle enum names.

Revision ID: 0020
Revises: 0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_STATUS_LENGTH = 12
STATUS_LENGTH = 32

STATUS_COLUMNS = (
    ("initiatives", "status"),
    ("ai_systems", "status"),
    ("model_assets", "status"),
    ("agents", "status"),
    ("assessments", "status"),
    ("approvals", "status"),
)


def _alter_status_columns(
    *,
    source_length: int,
    target_length: int,
) -> None:
    """Alter governance status columns while preserving nullability."""
    for table_name, column_name in STATUS_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.String(length=source_length),
            type_=sa.String(length=target_length),
            existing_nullable=False,
        )


def _assert_legacy_width_safe() -> None:
    """Refuse downgrade when current data cannot fit the legacy width."""
    connection = op.get_bind()

    for table_name, column_name in STATUS_COLUMNS:
        statement = sa.text(
            f"SELECT 1 FROM {table_name} WHERE length({column_name}) > :max_length LIMIT 1"
        )
        offending = connection.execute(
            statement,
            {"max_length": LEGACY_STATUS_LENGTH},
        ).first()

        if offending is not None:
            raise RuntimeError(
                "Downgrade refused: "
                f"{table_name}.{column_name} contains a status "
                f"longer than {LEGACY_STATUS_LENGTH} characters"
            )


def upgrade() -> None:
    """Expand lifecycle status storage for current enum member names."""
    _alter_status_columns(
        source_length=LEGACY_STATUS_LENGTH,
        target_length=STATUS_LENGTH,
    )


def downgrade() -> None:
    """Restore legacy widths only when existing values fit safely."""
    _assert_legacy_width_safe()
    _alter_status_columns(
        source_length=STATUS_LENGTH,
        target_length=LEGACY_STATUS_LENGTH,
    )
