"""add PeopleOps-owned policy knowledge ingestion tables

Revision ID: 0002_policy_knowledge_ingestion
Revises: 0001_peopleops_persistence
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


revision = "0002_policy_knowledge_ingestion"
down_revision = "0001_peopleops_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "policy_document",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_key", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("department", sa.String(255)),
        sa.Column("confidentiality", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_key", name="uq_policy_document_document_key"),
    )
    op.create_table(
        "policy_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["policy_document_id"], ["policy_document.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("policy_document_id", "version", name="uq_policy_version_document_version"),
    )
    op.create_index(
        "ix_policy_version_effective_dates", "policy_version", ["effective_from", "effective_to"]
    )
    op.create_table(
        "policy_chunk",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer()),
        sa.Column("section", sa.String(500)),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_version.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("policy_version_id", "chunk_index", name="uq_policy_chunk_version_index"),
    )
    op.create_index("ix_policy_chunk_policy_version_id", "policy_chunk", ["policy_version_id"])
    op.create_table(
        "ingestion_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(128)),
        sa.Column("error_detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_version.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ingestion_job_policy_version_id", "ingestion_job", ["policy_version_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_job_policy_version_id", table_name="ingestion_job")
    op.drop_table("ingestion_job")
    op.drop_index("ix_policy_chunk_policy_version_id", table_name="policy_chunk")
    op.drop_table("policy_chunk")
    op.drop_index("ix_policy_version_effective_dates", table_name="policy_version")
    op.drop_table("policy_version")
    op.drop_table("policy_document")
