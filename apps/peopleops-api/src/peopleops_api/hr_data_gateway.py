"""Stable PeopleOps boundary for structured HR data."""

from __future__ import annotations

from typing import TypeVar

from pydantic import RootModel

from peopleops_api.mcp_client import MCPClient
from peopleops_api.mcp_contracts import (
    DiscoveryCapability,
    DiscoveryCatalog,
    DiscoveryEntity,
    DiscoveryRelationship,
    DiscoveryRequestContext,
    SecurityContext,
    TemporalContext,
)
from peopleops_api.query_contracts import ConceptualQuery, QueryResult, QueryValidation


class HRDataGateway:
    def __init__(self, client: MCPClient) -> None:
        self._client = client

    def discover_catalog(
        self, *, request_id: str, security: SecurityContext | None = None
    ) -> DiscoveryCatalog:
        context = DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext())
        return self._client.call_tool(
            "discover_catalog", _context_arguments(context), DiscoveryCatalog, context
        )

    def discover_capabilities(
        self, *, request_id: str, security: SecurityContext | None = None
    ) -> list[DiscoveryCapability]:
        context = DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext())
        return self._client.call_tool(
            "discover_capabilities", _context_arguments(context), _CapabilitiesResponse, context
        ).root

    def discover_entities(
        self, *, request_id: str, security: SecurityContext | None = None
    ) -> list[DiscoveryEntity]:
        context = DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext())
        return self._client.call_tool(
            "discover_entities", _context_arguments(context), _EntitiesResponse, context
        ).root

    def describe_entity(
        self, entity_id: str, *, request_id: str, security: SecurityContext | None = None
    ) -> DiscoveryEntity:
        context = DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext())
        return self._client.call_tool(
            "describe_entity", {**_context_arguments(context), "entity_id": entity_id}, DiscoveryEntity, context
        )

    def discover_relationships(
        self, *, request_id: str, security: SecurityContext | None = None
    ) -> list[DiscoveryRelationship]:
        context = DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext())
        return self._client.call_tool(
            "discover_relationships", _context_arguments(context), _RelationshipsResponse, context
        ).root

    def validate_query(
        self, query: ConceptualQuery, *, request_id: str, security: SecurityContext | None = None
    ) -> QueryValidation:
        context = DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext())
        return self._client.call_tool(
            "validate_conceptual_query",
            {**_context_arguments(context), "query": query.model_dump(mode="json")},
            QueryValidation,
            context,
        )

    def get_temporal_context(
        self, *, request_id: str, security: SecurityContext | None = None
    ) -> TemporalContext:
        context = DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext())
        return self._client.call_tool(
            "temporal_context", _context_arguments(context), TemporalContext, context
        )

    def execute_query(
        self, query: ConceptualQuery, *, request_id: str, security: SecurityContext | None = None
    ) -> QueryResult:
        context = DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext())
        return self._client.call_tool(
            "execute_conceptual_query",
            {**_context_arguments(context), "query": query.model_dump(mode="json")},
            QueryResult,
            context,
        )


def _context_arguments(context: DiscoveryRequestContext) -> dict[str, object]:
    return {
        "request_id": context.request_id,
        "security": context.security.model_dump(mode="json"),
    }


T = TypeVar("T")


class _RootList(RootModel[list[T]]):
    pass


class _CapabilitiesResponse(_RootList[DiscoveryCapability]):
    pass


class _EntitiesResponse(_RootList[DiscoveryEntity]):
    pass


class _RelationshipsResponse(_RootList[DiscoveryRelationship]):
    pass
