"""Add immutable review submissions and versioned approval rounds.

Revision ID: 0004
Revises: 0003
"""

import json
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create review-round history and migrate any legacy approval round."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "review_submissions" not in tables:
        op.create_table(
            "review_submissions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "initiative_id",
                sa.String(length=36),
                sa.ForeignKey("initiatives.id"),
                nullable=False,
            ),
            sa.Column("review_round", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("submitted_by", sa.String(length=200), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True)),
            sa.Column("revision_summary", sa.Text(), nullable=False),
            sa.Column("policy_id", sa.String(length=100), nullable=False),
            sa.Column("policy_version", sa.String(length=50), nullable=False),
            sa.Column("risk_score", sa.Integer(), nullable=False),
            sa.Column("risk_tier", sa.String(length=50), nullable=False),
            sa.Column("initiative_snapshot", sa.JSON(), nullable=False),
            sa.Column("assessment_snapshots", sa.JSON(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "initiative_id",
                "review_round",
                name="uq_review_submission_initiative_round",
            ),
        )
        op.create_index(
            "ix_review_submissions_initiative_id",
            "review_submissions",
            ["initiative_id"],
        )

    _add_review_columns(inspector)
    _backfill_legacy_rounds(bind)

    op.execute("ALTER TABLE approvals DROP CONSTRAINT IF EXISTS uq_approval_initiative_area")
    op.execute("DROP INDEX IF EXISTS uq_approval_initiative_area")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_initiative_round_area "
        "ON approvals (initiative_id, review_round, area)"
    )


def downgrade() -> None:
    """Remove review rounds only when doing so cannot discard resubmission history."""
    bind = op.get_bind()
    has_later_round = bind.execute(
        sa.text("SELECT 1 FROM review_submissions WHERE review_round > 1 LIMIT 1")
    ).first()
    if has_later_round is not None:
        raise RuntimeError("Downgrade refused: review rounds greater than one would be destroyed")

    op.execute("ALTER TABLE approvals DROP CONSTRAINT IF EXISTS uq_approval_initiative_round_area")
    op.execute("DROP INDEX IF EXISTS uq_approval_initiative_round_area")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_initiative_area "
        "ON approvals (initiative_id, area)"
    )
    op.execute("ALTER TABLE approvals DROP COLUMN IF EXISTS superseded_at")
    op.execute("ALTER TABLE approvals DROP COLUMN IF EXISTS review_submission_id")
    op.execute("ALTER TABLE approvals DROP COLUMN IF EXISTS review_round")
    op.execute("ALTER TABLE initiatives DROP COLUMN IF EXISTS current_review_round")
    op.drop_table("review_submissions")


def _add_review_columns(inspector: sa.Inspector) -> None:
    """Add review projection columns when upgrading an existing database."""
    initiative_columns = {item["name"] for item in inspector.get_columns("initiatives")}
    if "current_review_round" not in initiative_columns:
        op.add_column(
            "initiatives",
            sa.Column(
                "current_review_round",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    approval_columns = {item["name"] for item in inspector.get_columns("approvals")}
    if "review_submission_id" not in approval_columns:
        op.add_column(
            "approvals",
            sa.Column(
                "review_submission_id",
                sa.String(length=36),
                sa.ForeignKey("review_submissions.id"),
            ),
        )
        op.create_index(
            "ix_approvals_review_submission_id",
            "approvals",
            ["review_submission_id"],
        )
    if "review_round" not in approval_columns:
        op.add_column(
            "approvals",
            sa.Column(
                "review_round",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )
    if "superseded_at" not in approval_columns:
        op.add_column(
            "approvals",
            sa.Column("superseded_at", sa.DateTime(timezone=True)),
        )


def _backfill_legacy_rounds(bind: sa.Connection) -> None:
    """Convert pre-workflow approvals into an immutable first review round."""
    initiatives = bind.execute(
        sa.text(
            """
            SELECT initiative.*
            FROM initiatives AS initiative
            WHERE EXISTS (
                SELECT 1 FROM approvals
                WHERE approvals.initiative_id = initiative.id
            )
            AND NOT EXISTS (
                SELECT 1 FROM review_submissions
                WHERE review_submissions.initiative_id = initiative.id
            )
            """
        )
    ).mappings()
    for initiative in initiatives:
        submission_id = str(uuid4())
        submitted_at = initiative["submitted_at"] or initiative["created_at"]
        assessment_snapshots = _assessment_snapshots(bind, initiative["id"])
        bind.execute(
            sa.text(
                """
                INSERT INTO review_submissions (
                    id, initiative_id, review_round, status, submitted_by,
                    submitted_at, resolved_at, revision_summary, policy_id,
                    policy_version, risk_score, risk_tier, initiative_snapshot,
                    assessment_snapshots, version, created_at, updated_at
                ) VALUES (
                    :id, :initiative_id, 1, :status, :submitted_by,
                    :submitted_at, :resolved_at, :revision_summary, :policy_id,
                    :policy_version, :risk_score, :risk_tier,
                    CAST(:initiative_snapshot AS JSON),
                    CAST(:assessment_snapshots AS JSON), 1, :created_at, :updated_at
                )
                """
            ),
            {
                "id": submission_id,
                "initiative_id": initiative["id"],
                "status": initiative["status"],
                "submitted_by": initiative["business_owner_id"],
                "submitted_at": submitted_at,
                "resolved_at": _resolved_at(initiative),
                "revision_summary": "Migrated legacy review round",
                "policy_id": initiative["policy_id"],
                "policy_version": initiative["policy_version"],
                "risk_score": initiative["risk_score"],
                "risk_tier": initiative["risk_tier"],
                "initiative_snapshot": json.dumps(_initiative_snapshot(initiative)),
                "assessment_snapshots": json.dumps(assessment_snapshots),
                "created_at": submitted_at,
                "updated_at": initiative["updated_at"],
            },
        )
        bind.execute(
            sa.text(
                "UPDATE approvals SET review_submission_id = :submission_id, "
                "review_round = 1 WHERE initiative_id = :initiative_id"
            ),
            {"submission_id": submission_id, "initiative_id": initiative["id"]},
        )
        bind.execute(
            sa.text("UPDATE initiatives SET current_review_round = 1 WHERE id = :initiative_id"),
            {"initiative_id": initiative["id"]},
        )


def _initiative_snapshot(initiative: Mapping[str, Any]) -> dict[str, Any]:
    """Build the same content snapshot used by new review submissions."""
    fields = (
        "name",
        "description",
        "business_owner_id",
        "business_area",
        "intended_users",
        "decision_impact",
        "data_classification",
        "autonomy_level",
        "hosting_model",
        "affects_rights",
        "executes_actions",
        "personal_data",
        "sensitive_data",
        "children_data",
        "external_facing",
        "regulated_context",
        "international_processing",
        "inference_countries",
        "uses_rag",
        "uses_agents",
        "uses_mcp",
        "uses_custom_model",
    )
    return {field: initiative[field] for field in fields}


def _assessment_snapshots(
    bind: sa.Connection,
    initiative_id: str,
) -> list[dict[str, Any]]:
    """Return serializable legacy assessment state for one initiative."""
    rows = bind.execute(
        sa.text(
            """
            SELECT id, assessment_type, schema_version, status, answers,
                   risk_score, risk_tier, assessed_by, version
            FROM assessments
            WHERE initiative_id = :initiative_id
            ORDER BY assessment_type
            """
        ),
        {"initiative_id": initiative_id},
    ).mappings()
    return [dict(row) for row in rows]


def _resolved_at(initiative: Mapping[str, Any]) -> Any | None:
    """Infer a legacy round resolution timestamp from its terminal state."""
    if str(initiative["status"]).lower() in {
        "approved",
        "rejected",
        "entitystatus.approved",
        "entitystatus.rejected",
    }:
        return initiative["updated_at"]
    return None
