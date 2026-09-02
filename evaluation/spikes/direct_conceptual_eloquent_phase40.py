"""Phase 4.0 — Direct Conceptual Eloquent Translation PoC.

This experiment deliberately bypasses the SemanticUnderstanding -> canonicalizer
-> compiler pipeline. The LLM receives an Eloquent-like conceptual model catalog
and returns either a conceptual Eloquent query or an explicit NEEDS_INFO result.

Physical table/column mappings are owned by the provider side of the experiment
and are never exposed to the first LLM call. A second, optional translation call
can receive the full provider mapping and translate the conceptual query to
provider SQL for validation/execution.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    cast: str
    description: str
    physical_column: str
    nullable: bool = False


class ModelRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    relation_type: Literal["belongsTo", "hasMany"]
    related_model: str
    foreign_key: str
    owner_key: str


class EloquentModelDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    physical_table: str
    primary_key: str
    primary_key_cast: str
    attributes: list[ModelAttribute]
    relationships: list[ModelRelationship] = Field(default_factory=list)


MODELS: tuple[EloquentModelDefinition, ...] = (
    EloquentModelDefinition(
        name="Employee",
        description="Person employed by the organization.",
        physical_table="employee",
        primary_key="id",
        primary_key_cast="integer",
        attributes=[
            ModelAttribute(name="id", cast="integer", description="Employee record identifier.", physical_column="id"),
            ModelAttribute(name="employee_code", cast="string", description="Business employee code.", physical_column="employee_code"),
            ModelAttribute(name="first_name", cast="string", description="Employee given name.", physical_column="first_name"),
            ModelAttribute(name="last_name", cast="string", description="Employee family name.", physical_column="last_name"),
            ModelAttribute(name="status", cast="string", description="Employment status.", physical_column="status"),
            ModelAttribute(name="hire_date", cast="date", description="Date employment began.", physical_column="hire_date"),
            ModelAttribute(name="department_id", cast="integer", description="Department reference.", physical_column="department_id"),
        ],
        relationships=[
            ModelRelationship(
                name="department",
                relation_type="belongsTo",
                related_model="Department",
                foreign_key="department_id",
                owner_key="id",
            ),
            ModelRelationship(
                name="overtime",
                relation_type="hasMany",
                related_model="Overtime",
                foreign_key="employee_id",
                owner_key="id",
            ),
        ],
    ),
    EloquentModelDefinition(
        name="Department",
        description="Organizational department and cost center.",
        physical_table="department",
        primary_key="id",
        primary_key_cast="integer",
        attributes=[
            ModelAttribute(name="id", cast="integer", description="Department identifier.", physical_column="id"),
            ModelAttribute(name="code", cast="string", description="Department business code.", physical_column="code"),
            ModelAttribute(name="name", cast="string", description="Department display name.", physical_column="name"),
            ModelAttribute(name="cost_center", cast="string", description="Assigned cost center.", physical_column="cost_center"),
        ],
        relationships=[
            ModelRelationship(
                name="employees",
                relation_type="hasMany",
                related_model="Employee",
                foreign_key="department_id",
                owner_key="id",
            )
        ],
    ),
    EloquentModelDefinition(
        name="Overtime",
        description="Approved overtime worked by an employee.",
        physical_table="overtime_record",
        primary_key="id",
        primary_key_cast="integer",
        attributes=[
            ModelAttribute(name="id", cast="integer", description="Overtime record identifier.", physical_column="id"),
            ModelAttribute(name="employee_id", cast="integer", description="Employee reference.", physical_column="employee_id"),
            ModelAttribute(name="work_date", cast="date", description="Date overtime was worked.", physical_column="work_date"),
            ModelAttribute(name="approved_minutes", cast="integer", description="Approved overtime duration in minutes.", physical_column="approved_minutes"),
            ModelAttribute(name="status", cast="string", description="Overtime approval/processing status.", physical_column="status"),
        ],
        relationships=[
            ModelRelationship(
                name="employee",
                relation_type="belongsTo",
                related_model="Employee",
                foreign_key="employee_id",
                owner_key="id",
            )
        ],
    ),
    EloquentModelDefinition(
        name="Attendance",
        description="Daily scheduled and worked attendance record.",
        physical_table="attendance_record",
        primary_key="id",
        primary_key_cast="integer",
        attributes=[
            ModelAttribute(name="id", cast="integer", description="Attendance identifier.", physical_column="id"),
            ModelAttribute(name="employee_id", cast="integer", description="Employee reference.", physical_column="employee_id"),
            ModelAttribute(name="work_date", cast="date", description="Attendance work date.", physical_column="work_date"),
            ModelAttribute(name="status", cast="string", description="Attendance status.", physical_column="status"),
            ModelAttribute(name="scheduled_minutes", cast="integer", description="Scheduled minutes.", physical_column="scheduled_minutes"),
            ModelAttribute(name="worked_minutes", cast="integer", description="Worked minutes.", physical_column="worked_minutes"),
            ModelAttribute(name="late_minutes", cast="integer", description="Late minutes.", physical_column="late_minutes"),
            ModelAttribute(name="absence_minutes", cast="integer", description="Absence minutes.", physical_column="absence_minutes"),
        ],
        relationships=[
            ModelRelationship(
                name="employee",
                relation_type="belongsTo",
                related_model="Employee",
                foreign_key="employee_id",
                owner_key="id",
            )
        ],
    ),
)


ALLOWED_METHODS: tuple[str, ...] = (
    "query",
    "select",
    "where",
    "whereBetween",
    "whereIn",
    "whereYear",
    "whereMonth",
    "whereDay",
    "whereWeekday",
    "whereLastDayOfMonth",
    "whereFirstDayOfMonth",
    "groupBy",
    "groupByMonth",
    "orderBy",
    "limit",
    "sum",
    "count",
    "avg",
    "min",
    "max",
    "get",
)

FORBIDDEN_METHODS: tuple[str, ...] = (
    "whereRaw",
    "selectRaw",
    "orderByRaw",
    "groupByRaw",
    "DB::raw",
    "joinRaw",
    "insert",
    "update",
    "delete",
    "upsert",
    "create",
    "save",
    "statement",
)


class ConceptualEloquentResponse(BaseModel):
    """Thin envelope around direct Eloquent text; not a query AST."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["QUERY", "NEEDS_INFO"]
    eloquent_query: str | None = None
    missing_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state(self) -> "ConceptualEloquentResponse":
        if self.status == "QUERY" and not self.eloquent_query:
            raise ValueError("QUERY requires eloquent_query")
        if self.status == "NEEDS_INFO" and not self.missing_information:
            raise ValueError("NEEDS_INFO requires missing_information")
        return self


class SQLTranslationResponse(BaseModel):
    """Provider translation result for the optional second LLM call."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["SQL", "NEEDS_INFO"]
    sql: str | None = None
    missing_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state(self) -> "SQLTranslationResponse":
        if self.status == "SQL" and not self.sql:
            raise ValueError("SQL requires sql")
        if self.status == "NEEDS_INFO" and not self.missing_information:
            raise ValueError("NEEDS_INFO requires missing_information")
        return self


def conceptual_catalog_text() -> str:
    """Render only the logical Eloquent surface exposed to query generation."""
    blocks: list[str] = []
    for model in MODELS:
        lines = [
            f"class {model.name}",
            f"description: {model.description}",
            f"primary_key: {model.primary_key} ({model.primary_key_cast})",
            "attributes:",
        ]
        for attribute in model.attributes:
            nullable = ", nullable" if attribute.nullable else ""
            lines.append(
                f"  - {attribute.name}: {attribute.cast}{nullable} — {attribute.description}"
            )
        lines.append("relationships:")
        if model.relationships:
            for relation in model.relationships:
                lines.append(
                    f"  - {relation.name}: {relation.relation_type}({relation.related_model})"
                )
        else:
            lines.append("  - none")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def physical_catalog_text() -> str:
    """Render provider-owned physical mapping for Eloquent -> SQL translation."""
    blocks: list[str] = []
    for model in MODELS:
        lines = [
            f"model {model.name}",
            f"table: {model.physical_table}",
            f"primary_key: {model.primary_key}",
            "columns:",
        ]
        for attribute in model.attributes:
            lines.append(
                f"  - {attribute.name} -> {model.physical_table}.{attribute.physical_column} [{attribute.cast}]"
            )
        lines.append("relationships:")
        if model.relationships:
            for relation in model.relationships:
                related = next(item for item in MODELS if item.name == relation.related_model)
                if relation.relation_type == "belongsTo":
                    join = (
                        f"{model.physical_table}.{relation.foreign_key} = "
                        f"{related.physical_table}.{relation.owner_key}"
                    )
                else:
                    join = (
                        f"{model.physical_table}.{relation.owner_key} = "
                        f"{related.physical_table}.{relation.foreign_key}"
                    )
                lines.append(f"  - {relation.name} -> {relation.related_model}: {join}")
        else:
            lines.append("  - none")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


ELOQUENT_GENERATION_PROMPT = f"""
You translate a user's HR data request directly into a conceptual Eloquent query.

Current reference date: 2026-08-30.
Timezone: UTC.

Use ONLY the conceptual models, attributes, relationships and methods below.
Do not use physical table names or physical column names.
Do not output SQL.
Do not use raw expressions or arbitrary methods.
Do not invent model attributes or relationships.

If the request cannot be translated safely because an essential business or
semantic fact is missing, return NEEDS_INFO and state exactly what is missing.
Do not guess the meaning of an ambiguous period.

The Eloquent text may contain more than one conceptual query when that is the
simplest faithful solution. Do not force comparisons into a binary structure;
choose the query shape that naturally answers the request.

Allowed methods:
{', '.join(ALLOWED_METHODS)}

Forbidden methods/constructs:
{', '.join(FORBIDDEN_METHODS)}

Conceptual models:
{conceptual_catalog_text()}
""".strip()


SQL_TRANSLATION_PROMPT = f"""
You are the physical query translator inside a provider/MCP boundary.
Translate the supplied conceptual Eloquent query to PostgreSQL SELECT SQL.

Use ONLY the physical mappings below. Do not invent tables, columns or joins.
The SQL must be read-only. Never emit INSERT, UPDATE, DELETE, DDL, COPY,
SELECT ... FOR UPDATE, raw procedural calls, or multiple statements.
Preserve half-open date intervals when the conceptual query uses them.
If the conceptual query cannot be translated with the mapping provided, return
NEEDS_INFO and state what mapping is missing.

Provider model mappings:
{physical_catalog_text()}
""".strip()


def assert_phase40_contract() -> None:
    conceptual = conceptual_catalog_text()
    physical = physical_catalog_text()
    assert "overtime_record" not in conceptual
    assert "attendance_record" not in conceptual
    assert "overtime_record" in physical
    assert "Employee" in conceptual
    assert "employee.department" not in physical  # joins, not conceptual paths
    for forbidden in FORBIDDEN_METHODS:
        assert forbidden in ELOQUENT_GENERATION_PROMPT


if __name__ == "__main__":
    assert_phase40_contract()
    print("DIRECT_CONCEPTUAL_ELOQUENT_PHASE40_SELF_TEST_OK")
