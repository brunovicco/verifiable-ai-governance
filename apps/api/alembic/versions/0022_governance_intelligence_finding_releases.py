"""Add durable minimized Governance Intelligence finding releases.

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create append-only content-minimized advisory finding releases."""
    op.create_table(
        "governance_intelligence_finding_releases",
        sa.Column("release_id", sa.String(length=36), primary_key=True),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column("finding_schema_version", sa.String(length=10), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=False),
        sa.Column("finding_type", sa.String(length=40), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_digest", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=200), nullable=False),
        sa.Column("correlation_id", sa.String(length=200), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("release_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "finding_id",
            name="uq_governance_intelligence_finding_release_finding",
        ),
        sa.CheckConstraint(
            "schema_version = '1.0'",
            name="ck_governance_intelligence_finding_release_schema",
        ),
        sa.CheckConstraint(
            "finding_schema_version = '1.0'",
            name="ck_governance_intelligence_finding_release_finding_schema",
        ),
        sa.CheckConstraint(
            "finding_type IN ('policy_interpretation', 'risk_candidate', "
            "'control_candidate', 'evidence_gap', 'evidence_interpretation', "
            "'intake_suggestion')",
            name="ck_governance_intelligence_finding_release_type",
        ),
        sa.CheckConstraint(
            "length(candidate_digest) = 64",
            name="ck_governance_intelligence_finding_release_candidate_digest",
        ),
        sa.CheckConstraint(
            "length(release_digest) = 64",
            name="ck_governance_intelligence_finding_release_digest",
        ),
        sa.CheckConstraint(
            "version = 1",
            name="ck_governance_intelligence_finding_release_version",
        ),
    )
    op.create_index(
        "ix_governance_intelligence_finding_release_subject_time",
        "governance_intelligence_finding_releases",
        ["subject_id", "released_at"],
    )
    op.create_index(
        "ix_governance_intelligence_finding_release_correlation",
        "governance_intelligence_finding_releases",
        ["correlation_id"],
    )
    op.create_index(
        "ix_governance_intelligence_finding_release_candidate_digest",
        "governance_intelligence_finding_releases",
        ["candidate_digest"],
    )


def downgrade() -> None:
    """Remove durable minimized advisory finding releases."""
    op.drop_index(
        "ix_governance_intelligence_finding_release_candidate_digest",
        table_name="governance_intelligence_finding_releases",
    )
    op.drop_index(
        "ix_governance_intelligence_finding_release_correlation",
        table_name="governance_intelligence_finding_releases",
    )
    op.drop_index(
        "ix_governance_intelligence_finding_release_subject_time",
        table_name="governance_intelligence_finding_releases",
    )
    op.drop_table("governance_intelligence_finding_releases")
