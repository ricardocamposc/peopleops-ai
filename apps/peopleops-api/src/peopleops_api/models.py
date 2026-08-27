from datetime import date, datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from peopleops_api.db import Base


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    interactions: Mapped[list["AnalysisInteraction"]] = relationship(back_populates="conversation")


class AnalysisInteraction(Base):
    __tablename__ = "analysis_interaction"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_analysis_interaction_request_id"),
        Index("ix_analysis_interaction_conversation_id", "conversation_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, default=uuid4)
    conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversation.id", ondelete="SET NULL")
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="received")
    current_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="received")
    stage_history: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    analysis_goal: Mapped[str | None] = mapped_column(String(255))
    semantic_request: Mapped[dict | None] = mapped_column(JSONB)
    query_plan: Mapped[dict | None] = mapped_column(JSONB)
    provider_type: Mapped[str | None] = mapped_column(String(64))
    provider_catalog_version: Mapped[str | None] = mapped_column(String(128))
    validation: Mapped[dict | None] = mapped_column(JSONB)
    structured_result: Mapped[dict | None] = mapped_column(JSONB)
    policy_sources: Mapped[list | None] = mapped_column(JSONB)
    policy_versions: Mapped[list | None] = mapped_column(JSONB)
    evidence: Mapped[list | None] = mapped_column(JSONB)
    human_review_status: Mapped[str | None] = mapped_column(String(64))
    human_review_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    response: Mapped[dict | None] = mapped_column(JSONB)
    warnings: Mapped[list | None] = mapped_column(JSONB)
    model_name: Mapped[str | None] = mapped_column(String(128))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_type: Mapped[str | None] = mapped_column(String(128))
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conversation: Mapped[Conversation | None] = relationship(back_populates="interactions")
    human_review: Mapped["HumanReviewRequest | None"] = relationship(
        back_populates="analysis", foreign_keys="HumanReviewRequest.analysis_id", uselist=False
    )


class HumanReviewRequest(Base):
    __tablename__ = "human_review_request"
    __table_args__ = (UniqueConstraint("analysis_id", name="uq_human_review_request_analysis"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("analysis_interaction.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evidence_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    decision: Mapped[str | None] = mapped_column(String(32))
    comments: Mapped[str | None] = mapped_column(Text)

    analysis: Mapped[AnalysisInteraction] = relationship(back_populates="human_review")
    decisions: Mapped[list["HumanReviewDecision"]] = relationship(
        back_populates="review_request",
        cascade="all, delete-orphan",
        order_by="HumanReviewDecision.decided_at",
    )


class HumanReviewDecision(Base):
    __tablename__ = "human_review_decision"
    __table_args__ = (
        UniqueConstraint("review_request_id", name="uq_human_review_decision_request"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    review_request_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("human_review_request.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    comments: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    review_request: Mapped[HumanReviewRequest] = relationship(back_populates="decisions")


class PolicyDocument(Base):
    __tablename__ = "policy_document"
    __table_args__ = (UniqueConstraint("document_key", name="uq_policy_document_document_key"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255))
    confidentiality: Mapped[str] = mapped_column(String(64), nullable=False, default="internal")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    versions: Mapped[list["PolicyVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class PolicyVersion(Base):
    __tablename__ = "policy_version"
    __table_args__ = (
        UniqueConstraint(
            "policy_document_id", "version", name="uq_policy_version_document_version"
        ),
        Index("ix_policy_version_effective_dates", "effective_from", "effective_to"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("policy_document.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[PolicyDocument] = relationship(back_populates="versions")
    chunks: Mapped[list["PolicyChunk"]] = relationship(
        back_populates="policy_version", cascade="all, delete-orphan"
    )
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(
        back_populates="policy_version", cascade="all, delete-orphan"
    )


class PolicyChunk(Base):
    __tablename__ = "policy_chunk"
    __table_args__ = (
        UniqueConstraint("policy_version_id", "chunk_index", name="uq_policy_chunk_version_index"),
        Index("ix_policy_chunk_policy_version_id", "policy_version_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("policy_version.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(500))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    policy_version: Mapped[PolicyVersion] = relationship(back_populates="chunks")


class IngestionJob(Base):
    __tablename__ = "ingestion_job"
    __table_args__ = (Index("ix_ingestion_job_policy_version_id", "policy_version_id"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("policy_version.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_type: Mapped[str | None] = mapped_column(String(128))
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    policy_version: Mapped[PolicyVersion] = relationship(back_populates="ingestion_jobs")
