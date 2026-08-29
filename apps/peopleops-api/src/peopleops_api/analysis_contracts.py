"""Observable, provider-neutral contracts for the structured HR workflow."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from peopleops_api.query_contracts import ConceptualQuery


class PolicyMetadataFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=128)
    value: str = Field(max_length=1024)


class PolicyFilterContract(BaseModel):
    """Structured, provider-neutral policy filters compatible with strict schemas."""

    model_config = ConfigDict(extra="forbid")

    document_key: str | None = Field(default=None, max_length=255)
    document_type: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=255)
    confidentiality: str | None = Field(default=None, max_length=64)
    metadata: list[PolicyMetadataFilter] = Field(default_factory=list, max_length=16)


class SemanticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=255)
    required_capabilities: list[str] = Field(default_factory=list, max_length=8)
    entities: list[str] = Field(default_factory=list, max_length=8)
    sensitivity: Literal["standard", "restricted"] = "standard"
    requires_human_review: bool = False
    time_scope_description: str | None = Field(default=None, max_length=255)
    requires_structured_data: bool = True
    requires_policy: bool = False
    policy_query: str | None = Field(default=None, max_length=1000)
    policy_as_of: date | None = None
    policy_filters: PolicyFilterContract = Field(default_factory=PolicyFilterContract)


class PlannedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=1, max_length=255)
    query: ConceptualQuery
    # Internal, provider-neutral metadata used after period-comparison
    # expansion.  It is deliberately optional so ordinary plans remain
    # backward compatible and the provider never needs to interpret it.
    logical_role: Literal["current", "previous"] | None = None


class PolicyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    as_of: date
    filters: PolicyFilterContract = Field(default_factory=lambda: PolicyFilterContract())
    top_k: int = Field(default=6, ge=1, le=20)


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=255)
    queries: list[PlannedQuery] = Field(default_factory=list, max_length=8)
    policy: PolicyPlan | None = None


class StructuredAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)
    key_findings: list[str] = Field(default_factory=list, max_length=12)
    # These are replaced with deterministic evidence after model parsing. Any
    # keeps the persisted evidence contract flexible without an open object in
    # the provider-facing Structured Outputs schema.
    facts: list[Any] = Field(default_factory=list, max_length=24)
    policies: list[Any] = Field(default_factory=list, max_length=24)
    inference: list[str] = Field(default_factory=list, max_length=12)
    status: Literal[
        "completed",
        "insufficient_data",
        "policy_not_found",
        "policy_conflict",
    ] = "completed"
    warnings: list[str] = Field(default_factory=list, max_length=12)
