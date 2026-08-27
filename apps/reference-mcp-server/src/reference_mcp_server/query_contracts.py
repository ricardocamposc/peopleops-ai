"""Provider-neutral conceptual query wire contract owned by the MCP boundary."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Scalar = str | int | float | bool | date | Decimal


class QuerySelect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    alias: str | None = None


class QueryMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str | None = None
    function: Literal["count", "sum", "avg", "min", "max"] = "count"
    alias: str | None = None

    @model_validator(mode="after")
    def field_required_when_not_count(self) -> QueryMetric:
        if self.function != "count" and self.field is None:
            raise ValueError("field is required for metrics other than count")
        return self


class QueryFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    operator: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "is_null", "not_null"]
    value: Scalar | list[Scalar] | None = None

    @model_validator(mode="after")
    def value_shape(self) -> QueryFilter:
        if self.operator in {"is_null", "not_null"} and self.value is not None:
            raise ValueError("null checks do not accept a value")
        if self.operator in {"in", "not_in"} and not isinstance(self.value, list):
            raise ValueError("membership filters require a list value")
        if self.operator not in {"is_null", "not_null"} and self.value is None:
            raise ValueError("this filter requires a value")
        return self


class QueryPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["date_range", "payroll_period", "period_comparison"]
    field: str | None = None
    start: date | None = None
    end: date | None = None
    value: str | None = None
    current: QueryPeriod | None = None
    previous: QueryPeriod | None = None

    @model_validator(mode="after")
    def shape(self) -> QueryPeriod:
        if self.type == "date_range" and (not self.field or not self.start or not self.end):
            raise ValueError("date_range requires field, start and end")
        if self.type == "date_range" and self.start > self.end:
            raise ValueError("period start must not be after end")
        if self.type == "payroll_period" and not self.value:
            raise ValueError("payroll_period requires value")
        if self.type == "period_comparison" and (not self.current or not self.previous):
            raise ValueError("period_comparison requires current and previous periods")
        return self


class QueryComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: str
    operator: Literal["eq", "neq", "gt", "gte", "lt", "lte"]
    right: str


class QueryOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str
    direction: Literal["asc", "desc"] = "asc"


class ConceptualQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["1"] = "1"
    goal: str | None = Field(default=None, max_length=255)
    entities: list[str] = Field(min_length=1, max_length=8)
    select: list[QuerySelect] = Field(default_factory=list, max_length=32)
    metrics: list[QueryMetric] = Field(default_factory=list, max_length=16)
    filters: list[QueryFilter] = Field(default_factory=list, max_length=32)
    relationships: list[str] = Field(default_factory=list, max_length=8)
    time_scope: QueryPeriod | None = None
    comparisons: list[QueryComparison] = Field(default_factory=list, max_length=16)
    order_by: list[QueryOrder] = Field(default_factory=list, max_length=8)
    dimensions: list[str] = Field(default_factory=list, max_length=16)
    limit: int = Field(default=100, ge=1, le=1000)


class QueryValidation(BaseModel):
    request_id: str | None = None
    valid: bool
    query_hash: str
    catalog_version: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QueryEvidence(BaseModel):
    provider: str
    catalog_version: str
    query_hash: str
    entities: list[str]
    fields: list[str]
    metrics: list[str]
    time_scope: dict[str, Any] | None = None
    row_count: int
    result_reference: str
    request_id: str


class QueryResult(BaseModel):
    request_id: str
    validation: QueryValidation
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    evidence: QueryEvidence | None = None
