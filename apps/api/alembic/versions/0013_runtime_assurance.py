"""Add deterministic runtime assurance policy and evaluation evidence.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_assurance_policies",
        sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("agents.id"), primary_key=True),
        sa.Column(
            "ai_system_id", sa.String(length=36), sa.ForeignKey("ai_systems.id"), nullable=False
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("lookback_seconds", sa.Integer(), nullable=False),
        sa.Column("evaluation_sample_size", sa.Integer(), nullable=False),
        sa.Column("minimum_samples", sa.Integer(), nullable=False),
        sa.Column("max_failure_rate", sa.Float(), nullable=False),
        sa.Column("max_p95_duration_ms", sa.Float()),
        sa.Column("max_consecutive_failures", sa.Integer()),
        sa.Column("breach_severity", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lookback_seconds BETWEEN 60 AND 86400", name="ck_runtime_assurance_policy_lookback"
        ),
        sa.CheckConstraint(
            "evaluation_sample_size BETWEEN 1 AND 1000",
            name="ck_runtime_assurance_policy_sample_size",
        ),
        sa.CheckConstraint(
            "minimum_samples BETWEEN 1 AND evaluation_sample_size",
            name="ck_runtime_assurance_policy_minimum_samples",
        ),
        sa.CheckConstraint(
            "max_failure_rate >= 0 AND max_failure_rate <= 1",
            name="ck_runtime_assurance_policy_failure_rate",
        ),
        sa.CheckConstraint(
            "max_p95_duration_ms IS NULL OR max_p95_duration_ms > 0",
            name="ck_runtime_assurance_policy_p95",
        ),
        sa.CheckConstraint(
            "max_consecutive_failures IS NULL OR "
            "(max_consecutive_failures >= 1 AND "
            "max_consecutive_failures <= evaluation_sample_size)",
            name="ck_runtime_assurance_policy_consecutive",
        ),
        sa.CheckConstraint(
            "breach_severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_runtime_assurance_policy_severity",
        ),
        sa.CheckConstraint("version > 0", name="ck_runtime_assurance_policy_version"),
    )
    op.create_index(
        "ix_runtime_assurance_policy_system", "runtime_assurance_policies", ["ai_system_id"]
    )

    op.create_table(
        "runtime_assurance_evaluations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column(
            "ai_system_id", sa.String(length=36), sa.ForeignKey("ai_systems.id"), nullable=False
        ),
        sa.Column(
            "initiative_id", sa.String(length=36), sa.ForeignKey("initiatives.id"), nullable=False
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("duration_sample_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("failure_rate", sa.Float(), nullable=False),
        sa.Column("p95_duration_ms", sa.Float()),
        sa.Column("max_consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("breach_reasons", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(length=20)),
        sa.Column("source_event_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("policy_version > 0", name="ck_runtime_assurance_eval_policy_version"),
        sa.CheckConstraint("sample_count >= 0", name="ck_runtime_assurance_eval_sample_count"),
        sa.CheckConstraint(
            "duration_sample_count >= 0 AND duration_sample_count <= sample_count",
            name="ck_runtime_assurance_eval_duration_count",
        ),
        sa.CheckConstraint(
            "failure_count >= 0 AND failure_count <= sample_count",
            name="ck_runtime_assurance_eval_failure_count",
        ),
        sa.CheckConstraint(
            "failure_rate >= 0 AND failure_rate <= 1", name="ck_runtime_assurance_eval_failure_rate"
        ),
        sa.CheckConstraint(
            "p95_duration_ms IS NULL OR p95_duration_ms >= 0", name="ck_runtime_assurance_eval_p95"
        ),
        sa.CheckConstraint(
            "max_consecutive_failures >= 0 AND max_consecutive_failures <= sample_count",
            name="ck_runtime_assurance_eval_consecutive",
        ),
        sa.CheckConstraint(
            "outcome IN ('insufficient_data', 'healthy', 'breached')",
            name="ck_runtime_assurance_eval_outcome",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_runtime_assurance_eval_severity",
        ),
        sa.CheckConstraint("version = 1", name="ck_runtime_assurance_eval_version"),
    )
    op.create_index(
        "ix_runtime_assurance_eval_agent_time",
        "runtime_assurance_evaluations",
        ["agent_id", "evaluated_at"],
    )
    op.create_index(
        "ix_runtime_assurance_eval_system_outcome",
        "runtime_assurance_evaluations",
        ["ai_system_id", "outcome"],
    )
    op.create_index(
        "ix_runtime_assurance_eval_digest", "runtime_assurance_evaluations", ["evidence_digest"]
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_assurance_eval_digest", table_name="runtime_assurance_evaluations")
    op.drop_index(
        "ix_runtime_assurance_eval_system_outcome", table_name="runtime_assurance_evaluations"
    )
    op.drop_index(
        "ix_runtime_assurance_eval_agent_time", table_name="runtime_assurance_evaluations"
    )
    op.drop_table("runtime_assurance_evaluations")
    op.drop_index("ix_runtime_assurance_policy_system", table_name="runtime_assurance_policies")
    op.drop_table("runtime_assurance_policies")
