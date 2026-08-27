from datetime import date
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)
from sqlalchemy import inspect, text

from peopleops_api.config import Settings
from peopleops_api.models import IngestionJob, PolicyChunk, PolicyDocument, PolicyVersion
from peopleops_api.policy_ingestion import (
    PolicyIngestionService,
    PolicyUploadError,
    validate_upload,
)


def pdf_bytes(text_value: str = "Vacation requests require manager approval.") -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): DictionaryObject({NameObject("/Type"): NameObject("/Font")})}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text_value}) Tj ET".encode())
    page[NameObject("/Contents")] = stream
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def ingestion_settings(tmp_path) -> Settings:
    return Settings(
        POLICY_STORAGE_PATH=str(tmp_path),
        OPENAI_API_KEY=None,
        EMBEDDING_DIMENSION=1536,
    )


def test_slice_07_migration_is_postgresql_with_pgvector(db_session) -> None:
    inspector = inspect(db_session.bind)
    assert {"policy_document", "policy_version", "policy_chunk", "ingestion_job"}.issubset(
        inspector.get_table_names()
    )
    assert (
        db_session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one()
        == "vector"
    )
    assert "embedding" in {column["name"] for column in inspector.get_columns("policy_chunk")}
    assert str(inspector.get_columns("policy_chunk")[6]["type"]).startswith("VECTOR")


def test_upload_validation_rejects_non_pdf_empty_and_oversized() -> None:
    with pytest.raises(PolicyUploadError, match="only PDF"):
        validate_upload("policy.txt", "text/plain", b"text", 100)
    with pytest.raises(PolicyUploadError, match="empty"):
        validate_upload("policy.pdf", "application/pdf", b"", 100)
    with pytest.raises(PolicyUploadError, match="exceeds"):
        validate_upload("policy.pdf", "application/pdf", b"%PDF-" + b"x" * 100, 10)
    with pytest.raises(PolicyUploadError, match="valid PDF"):
        validate_upload("policy.pdf", "application/pdf", b"not a pdf", 100)


def test_pdf_ingestion_persists_original_chunks_metadata_and_embedding(
    db_session, tmp_path
) -> None:
    content = pdf_bytes()
    document_key = f"vacation-{uuid4()}"
    version, job, idempotent = PolicyIngestionService(
        db_session, ingestion_settings(tmp_path)
    ).upload(
        document_key=document_key,
        title="Vacation policy",
        document_type="policy",
        version="2026.1",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        department="People",
        confidentiality="internal",
        filename="../vacation policy.pdf",
        content_type="application/pdf",
        content=content,
        metadata={"locale": "en-US"},
    )

    assert idempotent is False
    assert job.status == "completed"
    assert job.chunk_count >= 1
    assert version.status == "active"
    assert version.effective_from == date(2026, 1, 1)
    assert version.metadata_["locale"] == "en-US"
    assert version.metadata_["untrusted_content"] is True
    stored_path = tmp_path / version.storage_uri.removeprefix("file://")
    assert stored_path.is_file()
    assert stored_path.read_bytes() == content

    chunk = db_session.query(PolicyChunk).filter_by(policy_version_id=version.id).one()
    assert "manager approval" in chunk.text
    assert chunk.page == 1
    assert chunk.metadata_["untrusted_content"] is True
    assert len(chunk.embedding) == 1536


def test_same_checksum_is_idempotent_and_new_version_is_preserved(db_session, tmp_path) -> None:
    settings = ingestion_settings(tmp_path)
    content = pdf_bytes("The current policy applies to all employees.")
    key = f"remote-work-{uuid4()}"
    service = PolicyIngestionService(db_session, settings)
    first, first_job, _ = service.upload(
        document_key=key,
        title="Remote work",
        document_type="procedure",
        version="1",
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 12, 31),
        department=None,
        confidentiality="internal",
        filename="remote.pdf",
        content_type="application/pdf",
        content=content,
    )
    repeat, repeat_job, idempotent = service.upload(
        document_key=key,
        title="Remote work",
        document_type="procedure",
        version="1",
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 12, 31),
        department=None,
        confidentiality="internal",
        filename="remote.pdf",
        content_type="application/pdf",
        content=content,
    )
    second, second_job, _ = service.upload(
        document_key=key,
        title="Remote work",
        document_type="procedure",
        version="2",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        department=None,
        confidentiality="internal",
        filename="remote-v2.pdf",
        content_type="application/pdf",
        content=pdf_bytes("The updated policy requires written approval."),
    )

    assert idempotent is True
    assert repeat.id == first.id
    assert repeat_job.id == first_job.id
    assert second.id != first.id
    assert second_job.status == "completed"
    assert (
        db_session.query(PolicyVersion)
        .filter_by(policy_document_id=first.policy_document_id)
        .count()
        == 2
    )


def test_parse_failure_is_audited_and_does_not_raise(db_session, tmp_path) -> None:
    service = PolicyIngestionService(db_session, ingestion_settings(tmp_path))
    version, job, _ = service.upload(
        document_key=f"broken-{uuid4()}",
        title="Broken policy",
        document_type="policy",
        version="1",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        department=None,
        confidentiality="internal",
        filename="broken.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.7\nnot a complete pdf",
    )

    assert version.status == "failed"
    assert job.status == "failed"
    assert job.error_type
    assert job.error_detail
    assert db_session.query(IngestionJob).filter_by(policy_version_id=version.id).count() == 1
    assert db_session.query(PolicyDocument).filter_by(id=version.policy_document_id).one()
