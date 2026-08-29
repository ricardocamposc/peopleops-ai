import json
import logging
from time import monotonic
from datetime import date
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from peopleops_api.analysis_workflow import AnalysisWorkflow, OpenAIStructuredModel
from peopleops_api.config import get_settings
from peopleops_api.db import get_db
from peopleops_api.evidence_verifier import PolicyEvidenceVerifier
from peopleops_api.hr_data_gateway import HRDataGateway
from peopleops_api.mcp_client import MCPClient
from peopleops_api.mcp_contracts import DiscoveryCatalog, SecurityContext
from peopleops_api.models import HumanReviewRequest, PolicyDocument
from peopleops_api.observability import (
    configure_logging,
    log_event,
    request_id_context,
    request_id_from_header,
)
from peopleops_api.policy_ingestion import (
    PolicyIngestionService,
    PolicyUploadError,
    get_ingestion_job,
    get_policy_version,
    get_embedding_model,
)
from peopleops_api.policy_retrieval import PolicyKnowledgeProvider
from peopleops_api.repositories import (
    create_interaction,
    get_human_review,
    get_interaction,
    list_interactions,
    list_human_reviews,
    record_human_review_decision,
)
from peopleops_api.schemas import (
    AnalysisCreate,
    AnalysisRead,
    HumanReviewDecisionCreate,
    HumanReviewRead,
    PolicyChunkRead,
    PolicyDocumentRead,
    PolicyJobRead,
    PolicyUploadResponse,
    PolicyVersionRead,
)

configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()
app = FastAPI(title="PeopleOps AI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(settings.frontend_url).rstrip("/")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _analysis_response(interaction, *, include_evaluation_trace: bool = False) -> AnalysisRead:
    result = AnalysisRead.model_validate(interaction)
    if not include_evaluation_trace:
        result.evaluation_trace = None
    return result


def _security_context(request: Request) -> SecurityContext:
    """Build the provider context from the authenticated edge context.

    The default is read-only and deliberately excludes payroll. Browsers are
    not an authorization authority; deployments must set these headers at the
    authenticated gateway.
    """
    try:
        return SecurityContext(
            actor_id=request.headers.get("X-Actor-ID"),
            role=request.headers.get("X-Role"),
            scopes=request.headers.get("X-Security-Scopes", "hr:read").split(","),
        )
    except ValueError:
        # Malformed edge context must fail closed without exposing validation details.
        return SecurityContext()


@app.middleware("http")
async def observe_request(request: Request, call_next):
    request_id = request_id_from_header(request.headers.get("X-Request-ID"))
    token = request_id_context.set(request_id)
    started = monotonic()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = request_id
        log_event(
            logger,
            "request completed",
            event="http_request",
            status=response.status_code,
            latency_ms=round((monotonic() - started) * 1000),
        )
        return response
    finally:
        request_id_context.reset(token)


@app.get("/api/v1/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/api/v1/hr-data/catalog", response_model=DiscoveryCatalog, tags=["hr-data"])
def read_hr_data_catalog(request: Request) -> DiscoveryCatalog:
    gateway = HRDataGateway(
        MCPClient(
            server_url=str(settings.reference_mcp_server_url),
            timeout_seconds=settings.mcp_timeout_seconds,
            max_retries=settings.mcp_max_retries,
            max_response_bytes=settings.mcp_max_response_bytes,
        )
    )
    return gateway.discover_catalog(request_id=str(uuid4()), security=_security_context(request))


@app.post("/api/v1/analysis", response_model=AnalysisRead, status_code=status.HTTP_201_CREATED)
def register_analysis(
    payload: AnalysisCreate, request: Request, session: Annotated[Session, Depends(get_db)]
) -> AnalysisRead:
    if len(payload.question) > settings.max_question_length:
        raise HTTPException(status_code=422, detail="question exceeds the configured size limit")
    try:
        interaction = create_interaction(
            session,
            question=payload.question,
            conversation_id=payload.conversation_id,
            created_by=payload.created_by,
            metadata=payload.metadata,
            request_id=UUID(request_id_context.get()),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    gateway = HRDataGateway(
        MCPClient(
            server_url=str(settings.reference_mcp_server_url),
            timeout_seconds=settings.mcp_timeout_seconds,
            max_retries=settings.mcp_max_retries,
            max_response_bytes=settings.mcp_max_response_bytes,
        )
    )
    workflow = AnalysisWorkflow(
        session=session,
        gateway=gateway,
        model=OpenAIStructuredModel(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
            max_output_tokens=settings.openai_max_output_tokens,
        ),
        security=_security_context(request),
        policy_provider=PolicyKnowledgeProvider(session, get_embedding_model(settings)),
        evidence_verifier=(
            PolicyEvidenceVerifier(
                OpenAIStructuredModel(
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                    timeout_seconds=settings.openai_timeout_seconds,
                    max_retries=settings.openai_max_retries,
                    max_output_tokens=settings.openai_max_output_tokens,
                )
            )
            if settings.openai_api_key
            else None
        ),
    )
    interaction = workflow.run(interaction)
    return _analysis_response(
        interaction,
        include_evaluation_trace=payload.metadata.get("evaluation_structured_hr") is True,
    )


@app.get("/api/v1/analysis/{request_id}", response_model=AnalysisRead)
def read_analysis(request_id: str, session: Annotated[Session, Depends(get_db)]) -> AnalysisRead:
    try:
        parsed_request_id = UUID(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid request_id") from exc
    interaction = get_interaction(session, parsed_request_id)
    if interaction is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    include_trace = bool(
        interaction.conversation
        and (interaction.conversation.metadata_ or {}).get("evaluation_structured_hr") is True
    )
    return _analysis_response(interaction, include_evaluation_trace=include_trace)


@app.get("/api/v1/analysis", response_model=list[AnalysisRead])
def list_analysis(
    session: Annotated[Session, Depends(get_db)], limit: int = 50
) -> list[AnalysisRead]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    return [
        _analysis_response(
            interaction,
            include_evaluation_trace=bool(
                interaction.conversation
                and (interaction.conversation.metadata_ or {}).get("evaluation_structured_hr") is True
            ),
        )
        for interaction in list_interactions(session, limit=limit)
    ]


def _human_review_response(review: HumanReviewRequest) -> HumanReviewRead:
    analysis = review.analysis
    return HumanReviewRead(
        id=review.id,
        analysis_id=review.analysis_id,
        request_id=analysis.request_id,
        question=analysis.question,
        analysis_status=analysis.status,
        status=review.status,
        reason=review.reason,
        recommendation_snapshot=review.recommendation_snapshot,
        evidence_snapshot=review.evidence_snapshot,
        requested_at=review.requested_at,
        reviewed_at=review.reviewed_at,
        reviewed_by=review.reviewed_by,
        decision=review.decision,
        comments=review.comments,
        decisions=review.decisions,
    )


@app.get("/api/v1/human-review", response_model=list[HumanReviewRead], tags=["human-review"])
@app.get("/api/v1/human-review/inbox", response_model=list[HumanReviewRead], tags=["human-review"])
def human_review_inbox(
    status_filter: str | None = "pending",
    session: Annotated[Session, Depends(get_db)] = None,
) -> list[HumanReviewRead]:
    if status_filter not in {None, "pending", "approve", "reject", "needs_information"}:
        raise HTTPException(status_code=422, detail="invalid human review status")
    return [
        _human_review_response(item) for item in list_human_reviews(session, status=status_filter)
    ]


@app.get("/api/v1/human-review/{review_id}", response_model=HumanReviewRead, tags=["human-review"])
def human_review_detail(
    review_id: UUID, session: Annotated[Session, Depends(get_db)]
) -> HumanReviewRead:
    review = get_human_review(session, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="human review not found")
    return _human_review_response(review)


@app.post(
    "/api/v1/human-review/{review_id}/decision",
    response_model=HumanReviewRead,
    tags=["human-review"],
)
def human_review_decision(
    review_id: UUID,
    payload: HumanReviewDecisionCreate,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> HumanReviewRead:
    try:
        review, _, created = record_human_review_decision(
            session,
            review_id,
            decision=payload.decision,
            reviewed_by=payload.reviewed_by,
            comments=payload.comments,
        )
        session.commit()
    except LookupError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if created:
        interaction = session.get(type(review.analysis), review.analysis_id)
        if interaction is None:
            raise HTTPException(status_code=404, detail="analysis not found")
        workflow = AnalysisWorkflow(
            session=session,
            gateway=HRDataGateway(
                MCPClient(
                    server_url=str(settings.reference_mcp_server_url),
                    timeout_seconds=settings.mcp_timeout_seconds,
                    max_retries=settings.mcp_max_retries,
                    max_response_bytes=settings.mcp_max_response_bytes,
                )
            ),
            model=OpenAIStructuredModel(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                timeout_seconds=settings.openai_timeout_seconds,
                max_retries=settings.openai_max_retries,
                max_output_tokens=settings.openai_max_output_tokens,
            ),
            security=_security_context(request),
            policy_provider=PolicyKnowledgeProvider(session, get_embedding_model(settings)),
        )
        workflow.resume(interaction)
        session.refresh(review)
    return _human_review_response(review)


def _policy_response(version, job, idempotent: bool) -> PolicyUploadResponse:
    document = version.document
    return PolicyUploadResponse(
        document=PolicyDocumentRead.model_validate(document),
        version=PolicyVersionRead.model_validate(version),
        ingestion=PolicyJobRead.model_validate(job),
        idempotent=idempotent,
    )


@app.post(
    "/api/v1/policies/upload",
    response_model=PolicyUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_policy(
    file: Annotated[UploadFile, File(...)],
    document_key: Annotated[str, Form(...)],
    title: Annotated[str, Form(...)],
    version: Annotated[str, Form(...)],
    effective_from: Annotated[date, Form(...)],
    document_type: Annotated[str, Form()] = "policy",
    effective_to: Annotated[date | None, Form()] = None,
    department: Annotated[str | None, Form()] = None,
    confidentiality: Annotated[str, Form()] = "internal",
    metadata: Annotated[str, Form()] = "{}",
    session: Annotated[Session, Depends(get_db)] = None,
) -> PolicyUploadResponse:
    try:
        business_metadata = json.loads(metadata)
        if not isinstance(business_metadata, dict):
            raise TypeError("policy metadata must be a JSON object")
        content = file.file.read(settings.policy_max_upload_bytes + 1)
        service = PolicyIngestionService(session, settings)
        policy_version, job, idempotent = service.upload(
            document_key=document_key,
            title=title,
            document_type=document_type,
            version=version,
            effective_from=effective_from,
            effective_to=effective_to,
            department=department,
            confidentiality=confidentiality,
            filename=file.filename or "",
            content_type=file.content_type,
            content=content,
            metadata=business_metadata,
        )
        return _policy_response(policy_version, job, idempotent)
    except (PolicyUploadError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc) or "invalid policy metadata") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="policy ingestion configuration error") from exc


@app.get("/api/v1/policies", response_model=list[PolicyDocumentRead])
def list_policies(session: Annotated[Session, Depends(get_db)]) -> list[PolicyDocumentRead]:
    documents = (
        session.scalars(select(PolicyDocument).order_by(PolicyDocument.created_at)).unique().all()
    )
    return [PolicyDocumentRead.model_validate(document) for document in documents]


@app.get("/api/v1/policies/versions/{version_id}", response_model=PolicyVersionRead)
def read_policy_version(
    version_id: UUID, session: Annotated[Session, Depends(get_db)]
) -> PolicyVersionRead:
    version = get_policy_version(session, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="policy version not found")
    return PolicyVersionRead.model_validate(version)


@app.get("/api/v1/policies/ingestion/{job_id}", response_model=PolicyJobRead)
def read_policy_ingestion(
    job_id: UUID, session: Annotated[Session, Depends(get_db)]
) -> PolicyJobRead:
    job = get_ingestion_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ingestion job not found")
    return PolicyJobRead.model_validate(job)


def _policy_storage_path(version):
    storage_root = Path(settings.policy_storage_path).resolve()
    path = (storage_root / version.storage_uri.removeprefix("file://")).resolve()
    root = storage_root.resolve()
    if root not in path.parents:
        raise HTTPException(status_code=500, detail="invalid policy storage path")
    return path


@app.get("/api/v1/policies/versions/{version_id}/original", tags=["policies"])
def read_policy_original(
    version_id: UUID, session: Annotated[Session, Depends(get_db)]
) -> FileResponse:
    version = get_policy_version(session, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="policy version not found")
    path = _policy_storage_path(version)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="original policy file not found")
    return FileResponse(path, filename=version.original_filename, media_type="application/pdf")


@app.get(
    "/api/v1/policies/versions/{version_id}/chunks",
    response_model=list[PolicyChunkRead],
    tags=["policies"],
)
def read_policy_chunks(
    version_id: UUID, session: Annotated[Session, Depends(get_db)]
) -> list[PolicyChunkRead]:
    version = get_policy_version(session, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="policy version not found")
    chunks = sorted(version.chunks, key=lambda item: item.chunk_index)
    return [PolicyChunkRead.model_validate(chunk) for chunk in chunks]


@app.post("/api/v1/policies/versions/{version_id}/reindex", response_model=PolicyJobRead)
def reindex_policy(version_id: UUID, session: Annotated[Session, Depends(get_db)]) -> PolicyJobRead:
    try:
        job = PolicyIngestionService(session, settings).reindex(version_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyUploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PolicyJobRead.model_validate(job)
