from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from reference_mcp_server.config import get_settings
from reference_mcp_server.discovery import (
    CapabilityMetadata,
    CatalogMetadata,
    DiscoveryError,
    EntityMetadata,
    RelationshipMetadata,
    build_catalog,
)
from reference_mcp_server.execution import QueryExecutionError, execute_query, validate_query
from reference_mcp_server.query_contracts import ConceptualQuery, QueryResult, QueryValidation

settings = get_settings()
app = FastAPI(title="Reference MCP Server", version="0.1.0")
catalog = build_catalog()


@app.middleware("http")
async def propagate_request_correlation(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "")
    response = await call_next(request)
    if request_id:
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = request_id
    return response


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/discovery/catalog", response_model=CatalogMetadata, tags=["discovery"])
def discover_catalog() -> CatalogMetadata:
    return catalog


@app.get("/discovery/capabilities", response_model=list[CapabilityMetadata], tags=["discovery"])
def discover_capabilities() -> list[CapabilityMetadata]:
    return catalog.capabilities


@app.get("/discovery/entities", response_model=list[EntityMetadata], tags=["discovery"])
def discover_entities() -> list[EntityMetadata]:
    return catalog.entities


@app.get("/discovery/entities/{entity_id}", response_model=EntityMetadata, tags=["discovery"])
def describe_entity(entity_id: str) -> EntityMetadata | JSONResponse:
    entity = next((item for item in catalog.entities if item.entity_id == entity_id), None)
    if entity is None:
        error = DiscoveryError(
            code="ENTITY_NOT_FOUND", message=f"Entity '{entity_id}' was not found"
        )
        return JSONResponse(status_code=404, content=error.model_dump())
    return entity


@app.get(
    "/discovery/relationships",
    response_model=list[RelationshipMetadata],
    tags=["discovery"],
)
def discover_relationships() -> list[RelationshipMetadata]:
    return catalog.relationships


def _scopes(request: Request) -> list[str]:
    return [scope for scope in request.headers.get("X-Security-Scopes", "").split(",") if scope]


@app.post("/query/validate", response_model=QueryValidation, tags=["query"])
async def validate_conceptual_query(query: ConceptualQuery, request: Request) -> QueryValidation:
    return validate_query(
        query,
        catalog,
        _scopes(request),
        request_id=request.headers.get("X-Request-ID"),
        max_result_rows=settings.max_result_rows,
    )


@app.post("/query/execute", response_model=QueryResult, tags=["query"])
async def execute_conceptual_query(
    query: ConceptualQuery, request: Request
) -> QueryResult | JSONResponse:
    request_id = request.headers.get("X-Request-ID", "missing-request-id")
    try:
        return execute_query(
            query,
            catalog=catalog,
            settings=settings,
            request_id=request_id,
            scopes=_scopes(request),
        )
    except QueryExecutionError as exc:
        return JSONResponse(
            status_code=504 if exc.code == "QUERY_TIMEOUT" else 422,
            content={
                "code": exc.code,
                "message": str(exc),
                "request_id": request_id,
                "retryable": exc.retryable,
            },
        )
