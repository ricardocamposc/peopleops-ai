"""add durable human review requests and decisions

Revision ID: 0003_human_review
Revises: 0002_policy_knowledge_ingestion
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_human_review"
down_revision = "0002_policy_knowledge_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "human_review_request",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("recommendation_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("evidence_snapshot", postgresql.JSONB, nullable=False),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.String(255)),
        sa.Column("decision", sa.String(32)),
        sa.Column("comments", sa.Text()),
        sa.ForeignKeyConstraint(["analysis_id"], ["analysis_interaction.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("analysis_id", name="uq_human_review_request_analysis"),
    )
    op.create_index("ix_human_review_request_status", "human_review_request", ["status"])
    op.create_table(
        "human_review_decision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("comments", sa.Text()),
        sa.Column("reviewed_by", sa.String(255), nullable=False),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["review_request_id"], ["human_review_request.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("review_request_id", name="uq_human_review_decision_request"),
    )


def downgrade() -> None:
    op.drop_table("human_review_decision")
    op.drop_index("ix_human_review_request_status", table_name="human_review_request")
    op.drop_table("human_review_request")
