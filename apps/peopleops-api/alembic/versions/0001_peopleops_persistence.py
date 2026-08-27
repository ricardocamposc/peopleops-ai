"""create Conversation and AnalysisInteraction

Revision ID: 0001_peopleops_persistence
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_peopleops_persistence"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=255)),
        sa.Column("metadata", postgresql.JSONB, nullable=False),
    )
    op.create_table(
        "analysis_interaction",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("current_stage", sa.String(length=64), nullable=False),
        sa.Column("stage_history", postgresql.JSONB, nullable=False),
        sa.Column("analysis_goal", sa.String(length=255)),
        sa.Column("semantic_request", postgresql.JSONB),
        sa.Column("query_plan", postgresql.JSONB),
        sa.Column("provider_type", sa.String(length=64)),
        sa.Column("provider_catalog_version", sa.String(length=128)),
        sa.Column("validation", postgresql.JSONB),
        sa.Column("structured_result", postgresql.JSONB),
        sa.Column("policy_sources", postgresql.JSONB),
        sa.Column("policy_versions", postgresql.JSONB),
        sa.Column("evidence", postgresql.JSONB),
        sa.Column("human_review_status", sa.String(length=64)),
        sa.Column("human_review_id", postgresql.UUID(as_uuid=True)),
        sa.Column("response", postgresql.JSONB),
        sa.Column("warnings", postgresql.JSONB),
        sa.Column("model_name", sa.String(length=128)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_type", sa.String(length=128)),
        sa.Column("error_detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("request_id", name="uq_analysis_interaction_request_id"),
    )
    op.create_index("ix_analysis_interaction_conversation_id", "analysis_interaction", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_analysis_interaction_conversation_id", table_name="analysis_interaction")
    op.drop_table("analysis_interaction")
    op.drop_table("conversation")
