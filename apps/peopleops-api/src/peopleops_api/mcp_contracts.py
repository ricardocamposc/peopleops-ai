"""Provider-neutral contracts consumed from the Reference MCP Server."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    temporal_kind: str = "none"
    period_granularity: str | None = None


class DiscoveryEntity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entity_id: str
    business_name: str
    description: str
    fields: list[DiscoveryField]
    relationships: list[str] = Field(default_factory=list)
    temporal_fields: list[str] = Field(default_factory=list)
    primary_temporal_field: str | None = None
    supports_period_filter: bool = False
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


class TemporalContext(BaseModel):
    source_current_date: date
    source_current_timestamp: datetime
    source_timezone: str | None = None
    current_year: int
    current_month: int


class SecurityContext(BaseModel):
    """Minimal opaque authorization context forwarded to the provider."""

    actor_id: str | None = Field(default=None, max_length=255)
    scopes: list[str] = Field(default_factory=list, max_length=16)
    role: str | None = Field(default=None, max_length=64)

    @field_validator("scopes")
    @classmethod
    def normalize_scopes(cls, value: list[str]) -> list[str]:
        normalized = [scope.strip() for scope in value if scope.strip()]
        if any(len(scope) > 100 for scope in normalized):
            raise ValueError("security scope is too long")
        return list(dict.fromkeys(normalized))

    def allows_payroll(self) -> bool:
        return "hr:payroll" in self.scopes


class DiscoveryRequestContext(BaseModel):
    request_id: str
    security: SecurityContext = Field(default_factory=SecurityContext)


class ProviderError(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
