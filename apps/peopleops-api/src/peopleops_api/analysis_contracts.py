"""Observable, provider-neutral contracts for the structured HR workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from peopleops_api.query_contracts import ConceptualQuery


class SemanticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=255)
    required_capabilities: list[str] = Field(min_length=1, max_length=8)
    entities: list[str] = Field(min_length=1, max_length=8)
    sensitivity: Literal["standard", "restricted"] = "standard"
    time_scope_description: str | None = Field(default=None, max_length=255)


class PlannedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=1, max_length=255)
    query: ConceptualQuery


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=255)
    queries: list[PlannedQuery] = Field(min_length=1, max_length=8)


class StructuredAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)
    key_findings: list[str] = Field(default_factory=list, max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=12)
