"""Add sanitized runtime telemetry evidence.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_telemetry_events",
        sa.Column("event_id", sa.String(length=36), primary_key=True),
        sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("agents.id"), nullable=False),
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
        sa.Column("source_schema_version", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_name", sa.String(length=200), nullable=False),
        sa.Column("event_outcome", sa.String(length=20), nullable=False),
        sa.Column("service", sa.String(length=256), nullable=False),
        sa.Column("environment", sa.String(length=256), nullable=False),
        sa.Column("service_version", sa.String(length=256), nullable=False),
        sa.Column("trace_id", sa.String(length=32)),
        sa.Column("span_id", sa.String(length=16)),
        sa.Column("component", sa.String(length=256)),
        sa.Column("operation", sa.String(length=256)),
        sa.Column("correlation_id", sa.String(length=256)),
        sa.Column("request_id", sa.String(length=256)),
        sa.Column("retry_count", sa.Integer()),
        sa.Column("duration_ms", sa.Float()),
        sa.Column("http_method", sa.String(length=16)),
        sa.Column("http_status_code", sa.Integer()),
        sa.Column("error_type", sa.String(length=256)),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("source_schema_version = 1", name="ck_runtime_telemetry_source_schema"),
        sa.CheckConstraint(
            "event_outcome IN ('started', 'success', 'failure', 'error')",
            name="ck_runtime_telemetry_outcome",
        ),
        sa.CheckConstraint("version > 0", name="ck_runtime_telemetry_version_positive"),
    )
    op.create_index(
        "ix_runtime_telemetry_agent_observed",
        "runtime_telemetry_events",
        ["agent_id", "observed_at"],
    )
    op.create_index(
        "ix_runtime_telemetry_trace_id",
        "runtime_telemetry_events",
        ["trace_id"],
    )
    op.create_index(
        "ix_runtime_telemetry_correlation_id",
        "runtime_telemetry_events",
        ["correlation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_telemetry_correlation_id", table_name="runtime_telemetry_events")
    op.drop_index("ix_runtime_telemetry_trace_id", table_name="runtime_telemetry_events")
    op.drop_index("ix_runtime_telemetry_agent_observed", table_name="runtime_telemetry_events")
    op.drop_table("runtime_telemetry_events")
