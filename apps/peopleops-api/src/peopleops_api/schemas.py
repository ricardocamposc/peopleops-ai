from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AnalysisCreate(BaseModel):
    question: str = Field(min_length=1)
    conversation_id: UUID | None = None
    created_by: str | None = Field(default=None, max_length=255)
    metadata: dict = Field(default_factory=dict)


class StageEvent(BaseModel):
    stage: str
    status: str
    at: datetime
    error_type: str | None = None


class AnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: UUID
    conversation_id: UUID | None
    question: str
    status: str
    current_stage: str
    stage_history: list[StageEvent]
    analysis_goal: str | None
    semantic_request: dict | None
    query_plan: dict | None
    provider_type: str | None
    provider_catalog_version: str | None
    validation: dict | None
    structured_result: dict | None
    policy_sources: list | None
    policy_versions: list | None
    evidence: list | None
    human_review_status: str | None
    human_review_id: UUID | None
    response: dict | None
    warnings: list | None
    model_name: str | None
    latency_ms: int | None
    error_type: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class AnalysisCreated(BaseModel):
    request_id: UUID
    conversation_id: UUID | None
    status: str
    current_stage: str


class PolicyJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_version_id: UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    chunk_count: int
    error_type: str | None
    error_detail: str | None


class PolicyVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_document_id: UUID
    version: str
    effective_from: date
    effective_to: date | None
    status: str
    original_filename: str
    storage_uri: str
    checksum: str
    metadata: dict = Field(validation_alias="metadata_")
    created_at: datetime


class PolicyChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_version_id: UUID
    text: str
    page: int | None
    section: str | None
    chunk_index: int
    metadata: dict = Field(validation_alias="metadata_")
    created_at: datetime


class PolicyDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_key: str
    title: str
    document_type: str
    department: str | None
    confidentiality: str
    status: str
    created_at: datetime
    versions: list[PolicyVersionRead]


class PolicyUploadResponse(BaseModel):
    document: PolicyDocumentRead
    version: PolicyVersionRead
    ingestion: PolicyJobRead
    idempotent: bool
