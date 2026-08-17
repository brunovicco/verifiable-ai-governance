"""Add durable minimized Governance Intelligence review receipts.

Revision ID: 0021
Revises: 0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create append-only content-minimized advisory review receipts."""
    op.create_table(
        "governance_finding_review_receipts",
        sa.Column("review_id", sa.String(length=36), primary_key=True),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=10), nullable=False),
        sa.Column("finding_schema_version", sa.String(length=10), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=False),
        sa.Column("finding_type", sa.String(length=40), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_digest", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=200), nullable=False),
        sa.Column("correlation_id", sa.String(length=200), nullable=False),
        sa.Column("disposition", sa.String(length=40), nullable=False),
        sa.Column("reviewed_by", sa.String(length=200), nullable=False),
        sa.Column("administrator_access", sa.Boolean(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt_digest", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "request_id",
            name="uq_governance_finding_review_receipt_request",
        ),
        sa.CheckConstraint(
            "schema_version = '1.0'",
            name="ck_governance_finding_review_receipt_schema",
        ),
        sa.CheckConstraint(
            "finding_schema_version = '1.0'",
            name="ck_governance_finding_review_receipt_finding_schema",
        ),
        sa.CheckConstraint(
            "finding_type IN ('policy_interpretation', 'risk_candidate', "
            "'control_candidate', 'evidence_gap', 'evidence_interpretation', "
            "'intake_suggestion')",
            name="ck_governance_finding_review_receipt_type",
        ),
        sa.CheckConstraint(
            "disposition IN ('accepted_for_consideration', 'rejected', 'deferred')",
            name="ck_governance_finding_review_receipt_disposition",
        ),
        sa.CheckConstraint(
            "length(candidate_digest) = 64",
            name="ck_governance_finding_review_receipt_candidate_digest",
        ),
        sa.CheckConstraint(
            "length(receipt_digest) = 64",
            name="ck_governance_finding_review_receipt_digest",
        ),
        sa.CheckConstraint(
            "version = 1",
            name="ck_governance_finding_review_receipt_version",
        ),
    )
    op.create_index(
        "ix_governance_finding_review_receipt_subject_time",
        "governance_finding_review_receipts",
        ["subject_id", "reviewed_at"],
    )
    op.create_index(
        "ix_governance_finding_review_receipt_finding",
        "governance_finding_review_receipts",
        ["finding_id"],
    )
    op.create_index(
        "ix_governance_finding_review_receipt_candidate_digest",
        "governance_finding_review_receipts",
        ["candidate_digest"],
    )


def downgrade() -> None:
    """Remove durable minimized advisory review receipts."""
    op.drop_index(
        "ix_governance_finding_review_receipt_candidate_digest",
        table_name="governance_finding_review_receipts",
    )
    op.drop_index(
        "ix_governance_finding_review_receipt_finding",
        table_name="governance_finding_review_receipts",
    )
    op.drop_index(
        "ix_governance_finding_review_receipt_subject_time",
        table_name="governance_finding_review_receipts",
    )
    op.drop_table("governance_finding_review_receipts")
