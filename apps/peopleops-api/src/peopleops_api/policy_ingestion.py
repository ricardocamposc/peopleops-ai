"""PeopleOps-owned policy upload and indexing pipeline.

This module deliberately has no MCP dependency. Policy files are untrusted
content: they are parsed as data and their text is never executed or treated
as application instructions.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from llama_index.core import Document as LlamaDocument
from llama_index.core import Settings as LlamaSettings
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from pypdf import PdfReader
from pypdf.errors import PdfStreamError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from peopleops_api.config import Settings
from peopleops_api.models import IngestionJob, PolicyChunk, PolicyDocument, PolicyVersion

logger = logging.getLogger(__name__)
PDF_MIME = "application/pdf"
PDF_EXTENSION = ".pdf"
MAX_METADATA_KEYS = 32


class PolicyUploadError(ValueError):
    """A safe, user-facing policy upload validation error."""


class EmbeddingModel(Protocol):
    def get_text_embedding(self, text: str) -> list[float]: ...


def validate_upload(
    filename: str, content_type: str | None, content: bytes, max_bytes: int
) -> None:
    if not filename or Path(filename).suffix.lower() != PDF_EXTENSION:
        raise PolicyUploadError("only PDF policy documents are supported")
    if content_type and content_type.lower() != PDF_MIME:
        raise PolicyUploadError("the uploaded file must have content type application/pdf")
    if not content:
        raise PolicyUploadError("the uploaded file is empty")
    if len(content) > max_bytes:
        raise PolicyUploadError("the uploaded file exceeds the configured size limit")
    if not content.startswith(b"%PDF-"):
        raise PolicyUploadError("the uploaded file is not a valid PDF")


def safe_filename(filename: str) -> str:
    """Keep only a display name; never use user input as a storage path."""
    return re.sub(r"[^A-Za-z0-9._ -]", "_", Path(filename).name)[:500] or "policy.pdf"


def build_embedding_model(settings: Settings) -> EmbeddingModel:
    if settings.embedding_dimension != 1536:
        raise RuntimeError("the current pgvector schema requires 1536-dimensional embeddings")
    if settings.openai_api_key:
        return OpenAIEmbedding(model=settings.embedding_model, api_key=settings.openai_api_key)
    return MockEmbedding(embed_dim=settings.embedding_dimension)


def _pdf_documents(content: bytes, filename: str) -> list[LlamaDocument]:
    reader = PdfReader(BytesIO(content))
    pages: list[LlamaDocument] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except (KeyError, PdfStreamError):
            # Some PDFs omit optional font metadata. Keep ingestion bounded to
            # text drawing operators instead of treating document content as code.
            contents = page.get_contents()
            raw_contents = contents.get_data() if contents is not None else b""
            text = " ".join(
                match.decode("latin-1") for match in re.findall(rb"\(([^()]*)\)\s*Tj", raw_contents)
            )
        text = text.strip()
        if text:
            pages.append(
                LlamaDocument(text=text, metadata={"page": page_number, "source": filename})
            )
    if not pages:
        raise PolicyUploadError("the PDF contains no extractable text")
    return pages


def _chunks(
    content: bytes, filename: str, metadata: dict, embedding_model: EmbeddingModel
) -> list[dict]:
    documents = _pdf_documents(content, filename)
    parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    nodes = parser.get_nodes_from_documents(documents)
    result: list[dict] = []
    for index, node in enumerate(nodes):
        text = node.get_content().strip()
        if not text:
            continue
        node_metadata = {**metadata, **node.metadata, "untrusted_content": True}
        result.append(
            {
                "text": text,
                "page": node.metadata.get("page"),
                "section": node.metadata.get("section"),
                "chunk_index": index,
                "embedding": embedding_model.get_text_embedding(text),
                "metadata_": node_metadata,
            }
        )
    if not result:
        raise PolicyUploadError("the PDF did not produce any indexable chunks")
    return result


def get_embedding_model(settings: Settings) -> EmbeddingModel:
    """Configure LlamaIndex's process-local embedding model once per call site."""
    model = build_embedding_model(settings)
    LlamaSettings.embed_model = model
    return model


def _safe_metadata(metadata: dict | None) -> dict:
    if not metadata:
        return {}
    if len(metadata) > MAX_METADATA_KEYS:
        raise PolicyUploadError("policy metadata has too many keys")
    return {str(key): value for key, value in metadata.items()}


def _job_read(job: IngestionJob) -> dict:
    return {
        "id": job.id,
        "policy_version_id": job.policy_version_id,
        "status": job.status,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "chunk_count": job.chunk_count,
        "error_type": job.error_type,
        "error_detail": job.error_detail,
    }


class PolicyIngestionService:
    def __init__(
        self, session: Session, settings: Settings, embedding_model: EmbeddingModel | None = None
    ):
        self.session = session
        self.settings = settings
        self.embedding_model = embedding_model or get_embedding_model(settings)
        self.storage_root = Path(settings.policy_storage_path).resolve()

    def upload(
        self,
        *,
        document_key: str,
        title: str,
        document_type: str,
        version: str,
        effective_from: date,
        effective_to: date | None,
        department: str | None,
        confidentiality: str,
        filename: str,
        content_type: str | None,
        content: bytes,
        metadata: dict | None = None,
    ) -> tuple[PolicyVersion, IngestionJob, bool]:
        validate_upload(filename, content_type, content, self.settings.policy_max_upload_bytes)
        if effective_to and effective_to < effective_from:
            raise PolicyUploadError("effective_to must not be before effective_from")
        if not document_key.strip() or not title.strip() or not version.strip():
            raise PolicyUploadError("document_key, title and version are required")
        business_metadata = _safe_metadata(metadata)
        checksum = hashlib.sha256(content).hexdigest()

        document = self.session.scalar(
            select(PolicyDocument).where(PolicyDocument.document_key == document_key)
        )
        if document is None:
            document = PolicyDocument(
                document_key=document_key,
                title=title,
                document_type=document_type,
                department=department,
                confidentiality=confidentiality,
                status="active",
            )
            self.session.add(document)
            self.session.flush()
        existing = self.session.scalar(
            select(PolicyVersion).where(
                PolicyVersion.policy_document_id == document.id, PolicyVersion.checksum == checksum
            )
        )
        if existing is not None:
            job = self.session.scalar(
                select(IngestionJob)
                .where(IngestionJob.policy_version_id == existing.id)
                .order_by(IngestionJob.created_at.desc())
            )
            if job is None:
                raise RuntimeError("idempotent policy version has no ingestion job")
            self.session.commit()
            self.session.refresh(existing)
            self.session.refresh(job)
            return existing, job, True

        safe_name = safe_filename(filename)
        relative_uri = f"policies/{document.id}/{uuid4()}-{safe_name}"
        storage_path = self.storage_root / relative_uri
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(content)
        version_record = PolicyVersion(
            document=document,
            version=version,
            effective_from=effective_from,
            effective_to=effective_to,
            status="pending",
            original_filename=safe_name,
            storage_uri=f"file://{relative_uri}",
            checksum=checksum,
            metadata_={**business_metadata, "content_type": PDF_MIME, "untrusted_content": True},
        )
        self.session.add(version_record)
        self.session.flush()
        job = IngestionJob(policy_version_id=version_record.id, status="queued", chunk_count=0)
        self.session.add(job)
        self.session.commit()
        self.session.refresh(version_record)
        self.session.refresh(job)
        self._run(version_record.id, job.id, content, safe_name, business_metadata)
        self.session.refresh(version_record)
        self.session.refresh(job)
        return version_record, job, False

    def reindex(self, version_id: UUID) -> IngestionJob:
        version = self.session.get(PolicyVersion, version_id)
        if version is None:
            raise LookupError("policy version not found")
        path = self.storage_root / version.storage_uri.removeprefix("file://")
        if not path.is_file():
            raise PolicyUploadError("the original policy file is not available")
        job = IngestionJob(policy_version_id=version.id, status="queued", chunk_count=0)
        self.session.add(job)
        self.session.commit()
        self._run(
            version.id, job.id, path.read_bytes(), version.original_filename, version.metadata_
        )
        self.session.refresh(job)
        return job

    def _run(
        self, version_id: UUID, job_id: UUID, content: bytes, filename: str, metadata: dict
    ) -> None:
        job = self.session.get(IngestionJob, job_id)
        version = self.session.get(PolicyVersion, version_id)
        if job is None or version is None:
            raise RuntimeError("ingestion records disappeared")
        job.status = "running"
        job.started_at = datetime.now(UTC)
        version.status = "processing"
        self.session.commit()
        try:
            chunk_values = _chunks(content, filename, metadata, self.embedding_model)
            self.session.execute(
                delete(PolicyChunk).where(PolicyChunk.policy_version_id == version_id)
            )
            self.session.add_all(
                [
                    PolicyChunk(policy_version_id=version_id, **chunk_value)
                    for chunk_value in chunk_values
                ]
            )
            job.status = "completed"
            job.chunk_count = len(chunk_values)
            job.completed_at = datetime.now(UTC)
            version.status = "active"
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            job = self.session.get(IngestionJob, job_id)
            version = self.session.get(PolicyVersion, version_id)
            if job is None or version is None:
                raise
            job.status = "failed"
            job.error_type = type(exc).__name__
            job.error_detail = str(exc)[:1000]
            job.completed_at = datetime.now(UTC)
            version.status = "failed"
            self.session.commit()
            logger.warning(
                "policy ingestion failed for version %s: %s", version_id, type(exc).__name__
            )


def get_policy_version(session: Session, version_id: UUID) -> PolicyVersion | None:
    return session.scalar(
        select(PolicyVersion)
        .options(joinedload(PolicyVersion.document))
        .where(PolicyVersion.id == version_id)
    )


def get_ingestion_job(session: Session, job_id: UUID) -> IngestionJob | None:
    return session.get(IngestionJob, job_id)
