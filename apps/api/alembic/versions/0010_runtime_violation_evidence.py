"""Add structured runtime violation evidence to routing decisions.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable P1.4 evidence fields without rewriting historical decisions."""
    columns = _column_names("model_routing_decisions")
    additions = (
        ("violation_event_id", sa.String(length=36)),
        ("violation_category", sa.String(length=40)),
        ("violation_code", sa.String(length=100)),
        ("violation_digest", sa.String(length=64)),
        ("violation_payload", sa.JSON()),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column(
                "model_routing_decisions",
                sa.Column(name, column_type, nullable=True),
            )

    indexes = _index_names("model_routing_decisions")
    desired = (
        ("ix_model_routing_decisions_violation_event_id", "violation_event_id", True),
        ("ix_model_routing_decisions_violation_category", "violation_category", False),
        ("ix_model_routing_decisions_violation_code", "violation_code", False),
    )
    for name, column, unique in desired:
        if name not in indexes:
            op.create_index(
                name,
                "model_routing_decisions",
                [column],
                unique=unique,
            )


def downgrade() -> None:
    """Remove P1.4 violation evidence columns and indexes."""
    if "model_routing_decisions" not in _table_names():
        return
    indexes = _index_names("model_routing_decisions")
    for name in (
        "ix_model_routing_decisions_violation_code",
        "ix_model_routing_decisions_violation_category",
        "ix_model_routing_decisions_violation_event_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name="model_routing_decisions")
    columns = _column_names("model_routing_decisions")
    for name in (
        "violation_payload",
        "violation_digest",
        "violation_code",
        "violation_category",
        "violation_event_id",
    ):
        if name in columns:
            op.drop_column("model_routing_decisions", name)


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }
