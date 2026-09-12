import json
import logging
from time import monotonic
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any
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
    AnalysisDetailTrace,
    AnalysisRead,
    AnalysisTraceStep,
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
if not settings.hr_payroll_read_authorization_enabled:
    logger.warning(
        "Payroll read authorization enforcement is disabled. Intended only for "
        "synthetic/demo or explicitly trusted environments."
    )
if not settings.hr_read_analysis_human_review_enabled:
    logger.warning(
        "Human Review enforcement for read-only HR analysis is disabled. Intended only for "
        "synthetic/demo or explicitly trusted environments."
    )
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


def _safe_trace_payload(value: Any, *, max_items: int = 8) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    blocked = {
        "input",
        "incremental_input",
        "rendered_messages",
        "rendered_system_prompt",
        "prompt_template",
        "request",
        "request_messages",
        "messages",
    }
    payload = {key: item for key, item in value.items() if key not in blocked}
    if not payload:
        return None
    return dict(list(payload.items())[:max_items])


def _display_name(value: str | None) -> str:
    if not value:
        return "Workflow"
    return value.replace("_", " ").strip().title()


def _parse_datetime(value: Any):
    if not value:
        return None
    if hasattr(value, "isoformat"):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _query_count(query_plan: Any) -> int:
    if not isinstance(query_plan, dict):
        return 0
    queries = query_plan.get("queries")
    return len(queries) if isinstance(queries, list) else 0


def _row_count(structured_result: Any) -> int | None:
    if isinstance(structured_result, list):
        return len(structured_result)
    if isinstance(structured_result, dict):
        rows = structured_result.get("rows")
        if isinstance(rows, list):
            return len(rows)
        facts = structured_result.get("facts")
        if isinstance(facts, list):
            return len(facts)
    return None


def _validation_records(interaction, trace: dict[str, Any]) -> list[dict[str, Any]]:
    records = trace.get("provider_validations", [])
    if isinstance(records, list) and records:
        return [record for record in records if isinstance(record, dict)]
    if not isinstance(interaction.validation, dict):
        return []
    derived = []
    for key, value in interaction.validation.items():
        if not isinstance(value, dict) or "valid" not in value:
            continue
        query_index = value.get("query_index")
        if query_index is None:
            query_index = int(key) if str(key).isdigit() else key
        derived.append(
            {
                "attempt_number": value.get("attempt_number") or 1,
                "query_index": query_index,
                "accepted": bool(value.get("valid")),
                "errors": value.get("errors") or [],
                "catalog_version": value.get("catalog_version"),
                "query_hash": value.get("query_hash"),
                "source": "analysis_interaction.validation",
            }
        )
    return derived


def _execution_records(interaction, trace: dict[str, Any]) -> list[dict[str, Any]]:
    records = trace.get("provider_executions", [])
    if isinstance(records, list) and records:
        return [record for record in records if isinstance(record, dict)]
    evidence = interaction.evidence or interaction.structured_result or []
    if not isinstance(evidence, list):
        return []
    derived = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict) or item.get("type") != "structured_data":
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        rows = result.get("rows") if isinstance(result, dict) else None
        verification = item.get("result_verification") if isinstance(item.get("result_verification"), dict) else {}
        derived.append(
            {
                "attempt_number": 1,
                "query_index": index,
                "success": True,
                "row_count": len(rows) if isinstance(rows, list) else None,
                "result_verification_status": verification.get("status"),
                "source": "analysis_interaction.evidence",
            }
        )
    return derived


def _analysis_detail_trace(interaction) -> AnalysisDetailTrace:
    trace = interaction.evaluation_trace or {}
    steps: list[AnalysisTraceStep] = []

    for index, event in enumerate(interaction.stage_history or [], start=1):
        stage = event.get("stage")
        status_value = event.get("status")
        details = []
        if event.get("error_type"):
            details.append(f"Error: {event['error_type']}")
        steps.append(
            AnalysisTraceStep(
                sequence=len(steps) + 1,
                kind="workflow",
                title=_display_name(stage),
                status=status_value,
                stage=stage,
                graph_node=event.get("graph_node") or stage,
                at=_parse_datetime(event.get("at")),
                summary=f"Estado {status_value}" if status_value else None,
                details=details,
                metrics={"stage_event": index},
            )
        )

    if interaction.semantic_request:
        semantic = interaction.semantic_request
        details = []
        if isinstance(semantic.get("required_capabilities"), list) and semantic[
            "required_capabilities"
        ]:
            details.append(
                "Capacidades requeridas: " + ", ".join(map(str, semantic["required_capabilities"]))
            )
        if isinstance(semantic.get("operational_conditions"), list):
            details.append(
                f"Condiciones operacionales: {len(semantic['operational_conditions'])}"
            )
        steps.append(
            AnalysisTraceStep(
                sequence=len(steps) + 1,
                kind="analysis",
                title="Interpretacion Semantica",
                status="completed",
                stage="understanding",
                graph_node="understand_request",
                summary=str(semantic.get("goal") or "Requerimiento interpretado"),
                details=details,
                payload=_safe_trace_payload(semantic),
            )
        )

    if interaction.query_plan:
        combination = interaction.query_plan.get("combination")
        details = [f"Queries conceptuales: {_query_count(interaction.query_plan)}"]
        if isinstance(combination, dict) and combination.get("strategy"):
            details.append(f"Estrategia: {combination['strategy']}")
        steps.append(
            AnalysisTraceStep(
                sequence=len(steps) + 1,
                kind="analysis",
                title="Plan Conceptual",
                status="completed",
                stage="planning",
                graph_node="plan_queries",
                summary=str(interaction.query_plan.get("goal") or "Plan de consulta preparado"),
                details=details,
                metrics={"query_count": _query_count(interaction.query_plan)},
                payload=_safe_trace_payload(interaction.query_plan),
            )
        )

    validation_records = _validation_records(interaction, trace if isinstance(trace, dict) else {})
    for record in validation_records:
        if not isinstance(record, dict):
            continue
        accepted = bool(record.get("accepted"))
        details = []
        if record.get("errors"):
            details.append("; ".join(map(str, record["errors"])))
        if record.get("query_hash"):
            details.append(f"Query hash: {record['query_hash']}")
        steps.append(
            AnalysisTraceStep(
                sequence=len(steps) + 1,
                kind="tool",
                title="MCP Validate Conceptual Query",
                status="completed" if accepted else "failed",
                stage="query_execution",
                graph_node="execute_queries",
                tool_name="validate_query",
                summary="Query aceptada por el provider" if accepted else "Query rechazada por el provider",
                details=details,
                metrics={
                    "attempt": record.get("attempt_number"),
                    "query_index": record.get("query_index"),
                },
                payload=_safe_trace_payload(record),
            )
        )

    execution_records = _execution_records(interaction, trace if isinstance(trace, dict) else {})
    for record in execution_records:
        if not isinstance(record, dict):
            continue
        success = bool(record.get("success"))
        details = []
        if record.get("error"):
            details.append(str(record["error"]))
        steps.append(
            AnalysisTraceStep(
                sequence=len(steps) + 1,
                kind="tool",
                title="MCP Execute Conceptual Query",
                status="completed" if success else "failed",
                stage="query_execution",
                graph_node="execute_queries",
                tool_name="execute_query",
                summary="Ejecucion completada" if success else "Ejecucion fallida",
                details=details,
                metrics={
                    "attempt": record.get("attempt_number"),
                    "query_index": record.get("query_index"),
                    "row_count": record.get("row_count"),
                    "result_verification_status": record.get("result_verification_status"),
                },
                payload=_safe_trace_payload(record),
            )
        )

    for review in trace.get("senior_reviews", []) if isinstance(trace, dict) else []:
        if not isinstance(review, dict):
            continue
        coverage = review.get("semantic_coverage") if isinstance(review.get("semantic_coverage"), dict) else {}
        steps.append(
            AnalysisTraceStep(
                sequence=len(steps) + 1,
                kind="review",
                title="Senior Semantic Review",
                status=str(review.get("status") or "").lower() or None,
                stage="senior_review",
                graph_node="senior_review_node",
                summary=str((review.get("review") or {}).get("summary") or review.get("status") or "Revision semantica"),
                details=[f"Cobertura semantica: {coverage.get('status')}"] if coverage.get("status") else [],
                metrics={"attempt": review.get("attempt_number")},
                payload=_safe_trace_payload(review),
            )
        )

    if interaction.validation:
        steps.append(
            AnalysisTraceStep(
                sequence=len(steps) + 1,
                kind="validation",
                title="Validacion Deterministica",
                status="completed",
                summary="Validaciones persistidas para auditoria",
                payload=_safe_trace_payload(interaction.validation),
            )
        )

    if interaction.response:
        warnings = interaction.warnings or []
        steps.append(
            AnalysisTraceStep(
                sequence=len(steps) + 1,
                kind="analysis",
                title="Sintesis",
                status=interaction.status,
                stage="synthesis",
                graph_node="hr_assistant",
                summary=str(interaction.response.get("answer") or "Respuesta preparada"),
                details=[f"Advertencias: {len(warnings)}"] if warnings else [],
            )
        )

    return AnalysisDetailTrace(
        request_id=interaction.request_id,
        status=interaction.status,
        current_stage=interaction.current_stage,
        steps=steps,
        summary={
            "workflow_events": len(interaction.stage_history or []),
            "tool_validations": len(validation_records),
            "tool_executions": len(execution_records),
            "query_count": _query_count(interaction.query_plan),
            "structured_result_count": _row_count(interaction.structured_result),
            "policy_evidence_count": len(interaction.policy_sources or []),
            "warnings": len(interaction.warnings or []),
        },
    )


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
        payroll_read_authorization_enabled=settings.hr_payroll_read_authorization_enabled,
        read_analysis_human_review_enabled=settings.hr_read_analysis_human_review_enabled,
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


@app.get("/api/v1/analysis/{request_id}/details", response_model=AnalysisDetailTrace)
def read_analysis_details(
    request_id: str, session: Annotated[Session, Depends(get_db)]
) -> AnalysisDetailTrace:
    try:
        parsed_request_id = UUID(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid request_id") from exc
    interaction = get_interaction(session, parsed_request_id)
    if interaction is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return _analysis_detail_trace(interaction)


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
                and (interaction.conversation.metadata_ or {}).get("evaluation_structured_hr")
                is True
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
    interaction = session.get(type(review.analysis), review.analysis_id)
    if interaction is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    should_resume = created or (
        payload.decision == "approve"
        and review.decision == "approve"
        and interaction.status != "completed"
    )
    if should_resume:
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
            read_analysis_human_review_enabled=settings.hr_read_analysis_human_review_enabled,
        )
        workflow.resume(interaction, force=not created)
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
