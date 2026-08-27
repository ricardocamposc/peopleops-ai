"""Stable PeopleOps boundary for structured HR data."""

from __future__ import annotations

from typing import TypeVar
from urllib.parse import quote

from pydantic import RootModel

from peopleops_api.mcp_client import MCPClient
from peopleops_api.mcp_contracts import (
    DiscoveryCapability,
    DiscoveryCatalog,
    DiscoveryEntity,
    DiscoveryRelationship,
    DiscoveryRequestContext,
    SecurityContext,
)
from peopleops_api.query_contracts import ConceptualQuery, QueryResult, QueryValidation


class HRDataGateway:
    def __init__(self, client: MCPClient) -> None:
        self._client = client

    def discover_catalog(
        self, *, request_id: str, security: SecurityContext | None = None
    ) -> DiscoveryCatalog:
        return self._client.get_json(
            "/discovery/catalog",
            DiscoveryCatalog,
            DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext()),
        )

    def discover_capabilities(
        self, *, request_id: str, security: SecurityContext | None = None
    ) -> list[DiscoveryCapability]:
        return self._client.get_json(
            "/discovery/capabilities",
            _CapabilitiesResponse,
            DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext()),
        ).root

    def discover_entities(
        self, *, request_id: str, security: SecurityContext | None = None
    ) -> list[DiscoveryEntity]:
        return self._client.get_json(
            "/discovery/entities",
            _EntitiesResponse,
            DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext()),
        ).root

    def describe_entity(
        self, entity_id: str, *, request_id: str, security: SecurityContext | None = None
    ) -> DiscoveryEntity:
        return self._client.get_json(
            f"/discovery/entities/{quote(entity_id, safe='')}",
            DiscoveryEntity,
            DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext()),
        )

    def discover_relationships(
        self, *, request_id: str, security: SecurityContext | None = None
    ) -> list[DiscoveryRelationship]:
        return self._client.get_json(
            "/discovery/relationships",
            _RelationshipsResponse,
            DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext()),
        ).root

    def validate_query(
        self, query: ConceptualQuery, *, request_id: str, security: SecurityContext | None = None
    ) -> QueryValidation:
        return self._client.post_json(
            "/query/validate",
            query,
            QueryValidation,
            DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext()),
        )

    def execute_query(
        self, query: ConceptualQuery, *, request_id: str, security: SecurityContext | None = None
    ) -> QueryResult:
        return self._client.post_json(
            "/query/execute",
            query,
            QueryResult,
            DiscoveryRequestContext(request_id=request_id, security=security or SecurityContext()),
        )


T = TypeVar("T")


class _RootList(RootModel[list[T]]):
    pass


class _CapabilitiesResponse(_RootList[DiscoveryCapability]):
    pass


class _EntitiesResponse(_RootList[DiscoveryEntity]):
    pass


class _RelationshipsResponse(_RootList[DiscoveryRelationship]):
    pass
