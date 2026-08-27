"""Provider-neutral contracts consumed from the Reference MCP Server."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DiscoveryField(BaseModel):
    model_config = ConfigDict(extra="ignore")

    field_id: str
    business_name: str
    description: str
    data_type: str
    unit: str | None = None
    nullable: bool
    semantic_role: str
    sensitivity: str
    is_primary_key: bool = False
    is_foreign_key: bool = False


class DiscoveryEntity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entity_id: str
    business_name: str
    description: str
    fields: list[DiscoveryField]
    relationships: list[str] = Field(default_factory=list)
    temporal_fields: list[str] = Field(default_factory=list)
    sensitivity: str
    supported_operations: list[str]


class DiscoveryCapability(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str
    entities: list[str]
    supported_operations: list[str]
    sensitivity: str


class DiscoveryRelationship(BaseModel):
    model_config = ConfigDict(extra="ignore")

    relationship_id: str
    from_entity: str
    to_entity: str
    relationship_type: str
    join_semantics: str


class DiscoveryCatalog(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_type: str
    catalog_version: str
    fingerprint: str
    capabilities: list[DiscoveryCapability]
    entities: list[DiscoveryEntity]
    relationships: list[DiscoveryRelationship]


class SecurityContext(BaseModel):
    """Minimal opaque authorization context forwarded to the provider."""

    actor_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    role: str | None = None


class DiscoveryRequestContext(BaseModel):
    request_id: str
    security: SecurityContext = Field(default_factory=SecurityContext)


class ProviderError(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
