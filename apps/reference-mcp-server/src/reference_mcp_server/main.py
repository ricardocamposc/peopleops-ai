"""Reference provider exposed through the official MCP Streamable HTTP transport."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from reference_mcp_server.alternate_schema import build_alternate_catalog
from reference_mcp_server.audit import monotonic_started, record_interaction
from reference_mcp_server.config import get_settings
from reference_mcp_server.discovery import CatalogMetadata, build_catalog, build_catalog_from_database
from reference_mcp_server.execution import QueryExecutionError, execute_query, validate_query
from reference_mcp_server.query_contracts import ConceptualQuery
from reference_mcp_server.temporal import get_temporal_context

settings = get_settings()


def create_mcp_server(schema: str | None = None, *, live_discovery: bool = False) -> MCPServer:
    selected_schema = schema or os.environ.get("MCP_SCHEMA", "A")
    configured_catalog = build_alternate_catalog() if selected_schema == "B" else build_catalog()

    def current_catalog() -> CatalogMetadata:
        if not live_discovery:
            return configured_catalog
        url = _database_url()
        return build_catalog_from_database(url, configured_catalog)

    def catalog_error() -> ToolError:
        return ToolError("SOURCE_UNAVAILABLE")
    mcp = MCPServer(
        "reference-mcp-server",
        title="Reference MCP Server",
        version="0.1.0",
        instructions="Provider-neutral HR data discovery and read-only conceptual query execution.",
    )

    @mcp.tool(title="Discover catalog")
    def discover_catalog(request_id: str, security: dict[str, Any] | None = None) -> dict[str, Any]:
        """Discover provider capabilities, semantic entities and relationships."""
        try:
            return current_catalog().model_dump(mode="json")
        except Exception as exc:
            raise catalog_error() from exc

    @mcp.tool(title="Discover capabilities")
    def discover_capabilities(request_id: str, security: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """List generic capabilities exposed by the provider."""
        try:
            return [item.model_dump(mode="json") for item in current_catalog().capabilities]
        except Exception as exc:
            raise catalog_error() from exc

    @mcp.tool(title="Discover entities")
    def discover_entities(request_id: str, security: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """List semantic entities and their provider-neutral fields."""
        try:
            return [item.model_dump(mode="json") for item in current_catalog().entities]
        except Exception as exc:
            raise catalog_error() from exc

    @mcp.tool(title="Describe entity")
    def describe_entity(entity_id: str, request_id: str, security: dict[str, Any] | None = None) -> dict[str, Any]:
        """Describe one semantic entity."""
        try:
            entity = next((item for item in current_catalog().entities if item.entity_id == entity_id), None)
        except Exception as exc:
            raise catalog_error() from exc
        if entity is None:
            raise ToolError("UNSUPPORTED_ENTITY")
        return entity.model_dump(mode="json")

    @mcp.tool(title="Discover relationships")
    def discover_relationships(request_id: str, security: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """List relationships available to conceptual queries."""
        try:
            return [item.model_dump(mode="json") for item in current_catalog().relationships]
        except Exception as exc:
            raise catalog_error() from exc

    @mcp.tool(title="Get temporal context")
    def temporal_context(request_id: str, security: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return provider-source calendar context without exposing SQL or physical schema."""
        try:
            return get_temporal_context(settings, request_id=request_id).model_dump(mode="json")
        except Exception as exc:
            raise catalog_error() from exc

    @mcp.tool(title="Validate conceptual query")
    def validate_conceptual_query(
        query: dict[str, Any], request_id: str, security: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Validate a provider-neutral query without executing it."""
        started_at, _ = monotonic_started()
        try:
            typed_query = ConceptualQuery.model_validate(query)
        except Exception as exc:
            if settings.mcp_audit_enabled:
                record_interaction(settings, tool_name="validate_conceptual_query", request_id=request_id,
                                   started_at=started_at, status="invalid_contract",
                                   conceptual_query=query, error_code="INVALID_CONCEPTUAL_QUERY",
                                   error_message_safe="conceptual query contract invalid")
            raise ToolError("INVALID_CONCEPTUAL_QUERY") from exc
        try:
            catalog = current_catalog()
        except Exception as exc:
            raise catalog_error() from exc
        try:
            result = validate_query(
                typed_query,
                catalog,
                _scopes(security),
                request_id=request_id,
                max_result_rows=settings.max_result_rows,
            )
            if settings.mcp_audit_enabled:
                record_interaction(settings, tool_name="validate_conceptual_query", request_id=request_id,
                                   started_at=started_at,
                                   status="accepted" if result.valid else "rejected",
                                   catalog_version=result.catalog_version, provider_type=catalog.provider_type,
                                   conceptual_query=typed_query.model_dump(mode="json"),
                                   query_hash=result.query_hash,
                                   validation_result=result.model_dump(mode="json"),
                                   validation_errors=result.errors,
                                   error_code=None if result.valid else "QUERY_VALIDATION_ERROR",
                                   error_message_safe=None if result.valid else "query validation failed")
            return result.model_dump(mode="json")
        except Exception as exc:
            if settings.mcp_audit_enabled:
                record_interaction(settings, tool_name="validate_conceptual_query", request_id=request_id,
                                   started_at=started_at, status="failed",
                                   conceptual_query=query, error_code="INVALID_CONCEPTUAL_QUERY",
                                   error_message_safe="conceptual validation failed")
            raise ToolError("INVALID_CONCEPTUAL_QUERY") from exc

    @mcp.tool(title="Execute conceptual query")
    def execute_conceptual_query(
        query: dict[str, Any], request_id: str, security: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Validate and execute a bounded read-only conceptual query."""
        try:
            typed_query = ConceptualQuery.model_validate(query)
        except Exception as exc:
            raise ToolError("INVALID_CONCEPTUAL_QUERY") from exc
        try:
            catalog = current_catalog()
        except Exception as exc:
            raise catalog_error() from exc
        try:
            result = execute_query(
                typed_query,
                catalog=catalog,
                settings=settings,
                request_id=request_id,
                scopes=_scopes(security),
            )
        except QueryExecutionError as exc:
            raise ToolError(exc.code) from exc
        except Exception as exc:
            raise ToolError("EXECUTION_FAILED") from exc
        return result.model_dump(mode="json")

    return mcp


def create_app(schema: str | None = None, *, live_discovery: bool = True) -> FastAPI:
    # The deployed application always discovers the live physical source.
    mcp = create_mcp_server(schema, live_discovery=live_discovery)
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Reference MCP Server", version="0.1.0", lifespan=lifespan)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    # The official SDK owns the /mcp route and protocol lifecycle.
    app.mount("/", mcp_app)
    return app


def _scopes(security: dict[str, Any] | None) -> list[str]:
    if not security:
        return []
    values = security.get("scopes", [])
    if not isinstance(values, list) or len(values) > 16:
        return []
    return [str(value) for value in values if isinstance(value, str) and len(value) <= 100]


def _database_url() -> str:
    return (
        f"postgresql+psycopg://{settings.synthetic_hris_database_user}:"
        f"{settings.synthetic_hris_database_password}@{settings.synthetic_hris_database_host}:"
        f"{settings.synthetic_hris_database_port}/{settings.synthetic_hris_database_name}"
    )


app = create_app(live_discovery=os.environ.get("MCP_LIVE_DISCOVERY", "true").lower() == "true")
