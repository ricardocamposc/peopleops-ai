"""Phase 4.2 — independent agent-team query retrieval experiment."""
from __future__ import annotations

import ast
import json
import os
import time
from datetime import date
from importlib.resources import files as resource_files
from typing import Any, Literal, Protocol, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    String,
    and_,
    asc,
    case,
    cast,
    desc,
    distinct,
    extract,
    func,
    literal,
    not_,
    or_,
    select,
    union,
    union_all,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql.selectable import CompoundSelect, Select


class StructuredModel(Protocol):
    model_name: str

    def invoke(
        self, *, role: str, input_payload: dict[str, Any], output_model: type[BaseModel]
    ) -> tuple[BaseModel, dict[str, Any]]: ...


class Base(DeclarativeBase):
    pass


class Department(Base):
    __tablename__ = "department"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    cost_center: Mapped[str] = mapped_column(String(32))
    employees: Mapped[list[Employee]] = relationship(back_populates="department")


class Employee(Base):
    __tablename__ = "employee"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(32))
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32))
    hire_date: Mapped[date] = mapped_column(Date)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"))
    department: Mapped[Department] = relationship(back_populates="employees")
    overtime: Mapped[list[Overtime]] = relationship(back_populates="employee")
    attendance: Mapped[list[Attendance]] = relationship(back_populates="employee")


class Overtime(Base):
    __tablename__ = "overtime_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"))
    work_date: Mapped[date] = mapped_column(Date)
    approved_minutes: Mapped[int] = mapped_column(
        Integer,
        info={
            "description": (
                "total approved minutes of overtime; convert to hours by "
                "dividing by 60.0 when the request asks for hours so "
                "decimals are preserved: hours = approved_minutes / 60.0"
            )
        },
    )
    status: Mapped[str] = mapped_column(String(32))
    employee: Mapped[Employee] = relationship(back_populates="overtime")


class Attendance(Base):
    __tablename__ = "attendance_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"))
    work_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32))
    scheduled_minutes: Mapped[int] = mapped_column(Integer)
    worked_minutes: Mapped[int] = mapped_column(Integer)
    late_minutes: Mapped[int] = mapped_column(Integer)
    absence_minutes: Mapped[int] = mapped_column(Integer)
    employee: Mapped[Employee] = relationship(back_populates="attendance")


MODELS = (Employee, Department, Overtime, Attendance)


class FunctionalAnalystResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    needs_clarification: bool
    questions_or_missing_information: list[str]
    original_user_request: str
    clarified_request: str
    business_intent: str
    domain: list[str]
    required_information: list[str]
    measures: list[str]
    dimensions: list[str]
    filters: list[str]
    temporal_requirements: list[str]
    grouping_requirements: list[str]
    ordering_requirements: list[str]
    comparison_requirements: list[str]
    data_retrieval_request: str
    downstream_analysis: list[str]
    required_sources: list[str]
    assumptions: list[str]
    ambiguities: list[str]
    unsupported_requirements: list[str]
    sensitivity: list[str]


class RequirementCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str
    status: Literal["SATISFIED", "PARTIALLY_SATISFIED", "NOT_SATISFIED"]
    implementation: str


class MaterialIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    severity: str
    requirement: str
    issue: str
    why_it_matters: str
    required_correction: str


class RequirementReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str
    status: Literal["SATISFIED", "PARTIALLY_SATISFIED", "NOT_SATISFIED", "NOT_APPLICABLE"]
    evidence: str
    notes: str


class QuerySemanticsReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temporal_correctness: str
    measure_correctness: str
    dimension_correctness: str
    filter_correctness: str
    aggregation_correctness: str
    grouping_correctness: str
    ordering_correctness: str
    relationship_correctness: str
    duplicate_risk: str
    data_sufficiency: str
    comparison_preservation: str


class QueryProgrammerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["QUERY", "NEEDS_INFO", "CANNOT_IMPLEMENT"]
    sqlalchemy: str | None = None
    interpretation: str
    assumptions: list[str]
    missing_information: list[str]
    models_used: list[str]
    relationships_used: list[str]
    retrieved_measures: list[str]
    retrieved_dimensions: list[str]
    applied_filters: list[str]
    applied_temporal_constraints: list[str]
    grouping_implemented: list[str]
    requirement_coverage: list[RequirementCoverage]

    @model_validator(mode="after")
    def validate_state(self) -> QueryProgrammerResponse:
        if self.status == "QUERY" and not self.sqlalchemy:
            raise ValueError("QUERY requires sqlalchemy")
        if self.status == "NEEDS_INFO" and not self.missing_information:
            raise ValueError("NEEDS_INFO requires missing_information")
        return self


class QueryTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_user_request: str
    clarified_request: str
    business_intent: str
    required_information: list[str]
    measures: list[str]
    dimensions: list[str]
    filters: list[str]
    temporal_requirements: list[str]
    grouping_requirements: list[str]
    ordering_requirements: list[str]
    comparison_requirements: list[str]
    data_retrieval_request: str
    downstream_analysis: list[str]
    assumptions: list[str]


class SeniorReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["APPROVED", "REVISE", "CANNOT_APPROVE"]
    summary: str
    material_issues: list[MaterialIssue]
    requirement_review: list[RequirementReview]
    query_semantics_review: QuerySemanticsReview
    repair_instructions: list[str]
    assumptions: list[str]
    missing_information: list[str]
    confidence: float = Field(ge=0, le=1)


class ValidationResult(TypedDict):
    syntax_errors: list[str]
    build_errors: list[str]
    compile_errors: list[str]
    all_errors: list[str]
    statement_built: bool
    compiled_sql: str | None
    technically_valid: bool


class Phase42State(TypedDict, total=False):
    mode: Literal["FUNCTIONAL_ANALYST_ONLY", "QUERY_DEVELOPER_ONLY", "AGENT_TEAM"]
    question: str
    functional_analysis: dict[str, Any]
    query_task: dict[str, Any]
    query_developer_attempts: list[dict[str, Any]]
    current_query: dict[str, Any]
    validation_result: ValidationResult
    senior_reviews: list[dict[str, Any]]
    revision_count: int
    final_status: str
    audit_trail: list[dict[str, Any]]
    models: dict[str, str]
    request_id: str
    reference_context: dict[str, Any]
    current_stage: str
    stage_history: list[str]
    _llm: StructuredModel


PHASE42_PROMPTS = resource_files("peopleops_api.resources.prompts.phase42")
SEMANTIC_CLARIFIER_PROMPT = PHASE42_PROMPTS.joinpath(
    "functional-analyst.md"
).read_text(encoding="utf-8")
SQLALCHEMY_QUERY_DEVELOPER_PROMPT = PHASE42_PROMPTS.joinpath(
    "sqlalchemy-query-programmer.md"
).read_text(encoding="utf-8")
MAX_REPAIR_ATTEMPTS = 1
REFERENCE_CONTEXT = {
    "reference_date": "2026-08-30",
    "reference_year": 2026,
    "reference_month": 8,
    "reference_day": 30,
    "current_period": "2026-08",
    "timezone": "UTC",
}


SENIOR_QUERY_REVIEWER_PROMPT = PHASE42_PROMPTS.joinpath(
    "senior-query-reviewer.md"
).read_text(encoding="utf-8")


AGENT_SPECS = {
    "semantic_clarifier": {
        "prompt_id": "peopleops.semantic_clarifier",
        "prompt_version": "v3-functional-analyst",
        "model_env": "SEMANTIC_CLARIFIER_MODEL",
    },
    "sqlalchemy_query_developer": {
        "prompt_id": "peopleops.sqlalchemy_query_developer",
        "prompt_version": "v2-query-programmer",
        "model_env": "SQLALCHEMY_QUERY_DEVELOPER_MODEL",
    },
    "senior_query_reviewer": {
        "prompt_id": "peopleops.senior_query_reviewer",
        "prompt_version": "v2-senior-reviewer",
        "model_env": "SENIOR_QUERY_REVIEWER_MODEL",
    },
}


def _prompt_templates() -> dict[str, ChatPromptTemplate]:
    """Build LangChain templates that render the prompt-file variables."""
    return {
        "semantic_clarifier": ChatPromptTemplate.from_messages([
            ("system", SEMANTIC_CLARIFIER_PROMPT),
            ("human", "{{user_input}}"),
        ], template_format="jinja2"),
        "sqlalchemy_query_developer": ChatPromptTemplate.from_messages([
            ("system", SQLALCHEMY_QUERY_DEVELOPER_PROMPT),
            ("human", "{{user_input}}"),
        ], template_format="jinja2"),
        "senior_query_reviewer": ChatPromptTemplate.from_messages([
            ("system", SENIOR_QUERY_REVIEWER_PROMPT),
            ("human", "{{user_input}}"),
        ], template_format="jinja2"),
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class LangChainAgentRuntime:
    """Central model registry and structured-output invocation boundary."""

    model_name = "langchain-configured"

    def __init__(self, model_config: dict[str, str] | None = None) -> None:
        configured = model_config or {
            role: os.getenv(spec["model_env"], "gpt-4o-mini")
            for role, spec in AGENT_SPECS.items()
        }
        self.models = {
            role: ChatOpenAI(
                model=model,
                api_key=os.environ.get("OPENAI_API_KEY"),
                temperature=0,
                max_retries=0,
            )
            for role, model in configured.items()
        }
        self.model_config = configured
        self.templates = _prompt_templates()

    def invoke(
        self, *, role: str, input_payload: dict[str, Any], output_model: type[BaseModel]
    ) -> tuple[BaseModel, dict[str, Any]]:
        spec = AGENT_SPECS[role]
        variables = _chain_variables(role, input_payload)
        prompt_template = {
            "semantic_clarifier": SEMANTIC_CLARIFIER_PROMPT,
            "sqlalchemy_query_developer": SQLALCHEMY_QUERY_DEVELOPER_PROMPT,
            "senior_query_reviewer": SENIOR_QUERY_REVIEWER_PROMPT,
        }[role]
        variables["user_input"] = _json(input_payload)
        rendered = self.templates[role].format_messages(**variables)
        started = time.perf_counter()
        chain = self.templates[role] | self.models[role].with_structured_output(output_model)
        result = chain.invoke(variables)
        metadata = {
            "agent_id": role,
            "prompt_id": spec["prompt_id"],
            "prompt_version": spec["prompt_version"],
            "model": self.model_config[role],
            "schema_version": output_model.__name__,
            "rendered_messages": [
                {"role": message.type, "content": message.content}
                for message in rendered
            ],
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        metadata["prompt_template"] = prompt_template
        metadata["rendered_system_prompt"] = rendered[0].content
        return result, metadata


def _chain_variables(role: str, payload: dict[str, Any]) -> dict[str, str]:
    if role == "semantic_clarifier":
        context = payload["reference_context"]
        return {
            "data_model": str(payload["data_model"]),
            "reference_date": str(context["reference_date"]),
            "reference_year": str(context["reference_year"]),
            "reference_month": str(context["reference_month"]),
            "reference_day": str(context["reference_day"]),
            "current_period": str(context["current_period"]),
            "timezone": str(context["timezone"]),
        }
    if role == "sqlalchemy_query_developer":
        context = payload["reference_context"]
        return {
            "reference_date": str(context["reference_date"]),
            "reference_year": str(context["reference_year"]),
            "reference_month": str(context["reference_month"]),
            "reference_day": str(context["reference_day"]),
            "current_period": str(context["current_period"]),
            "timezone": str(context["timezone"]),
            "data_model": str(payload["data_model"]),
            "query_task": _json(payload["query_task"]),
            "previous_query": _json(payload.get("previous_query")),
            "validation_feedback": _json(payload.get("validation_feedback")),
            "senior_review": _json(payload.get("senior_review")),
        }
    return {
        "data_model": str(payload["data_model"]),
        "reference_date": str(payload["reference_context"]["reference_date"]),
        "reference_year": str(payload["reference_context"]["reference_year"]),
        "reference_month": str(payload["reference_context"]["reference_month"]),
        "reference_day": str(payload["reference_context"]["reference_day"]),
        "current_period": str(payload["reference_context"]["current_period"]),
        "timezone": str(payload["reference_context"]["timezone"]),
    }


def _catalog() -> str:
    blocks: list[str] = []
    for model in MODELS:
        mapper = model.__mapper__
        lines = [f"class {model.__name__}", "attributes:"]
        for property_ in mapper.column_attrs:
            column = property_.columns[0]
            lines.append(f"  - {property_.key}: {column.type}")
            description = column.info.get("description")
            if description:
                lines.append(f"    description: {description}")
        lines.append("relationships:")
        for relation in mapper.relationships:
            target = relation.mapper.class_
            cardinality = "one-to-many" if relation.uselist else "many-to-one"
            local, remote = relation.local_remote_pairs[0]
            arrow = "<-" if relation.uselist else "->"
            lines.append(
                f"  - {relation.key}: {cardinality} -> {target.__name__}; "
                f"relationship key: {model.__name__}.{local.key} {arrow} "
                f"{target.__name__}.{remote.key}"
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


SAFE_NAMESPACE = {
    "Employee": Employee, "Department": Department, "Overtime": Overtime,
    "Attendance": Attendance, "select": select, "func": func, "and_": and_,
    "or_": or_, "not_": not_, "case": case, "cast": cast, "literal": literal,
    "distinct": distinct, "extract": extract, "union": union,
    "union_all": union_all, "asc": asc, "desc": desc, "date": date,
    "Integer": Integer, "String": String, "Date": Date,
}
BLOCKED_NAMES = {
    "__import__", "eval", "exec", "open", "compile", "globals", "locals",
    "getattr", "setattr", "delattr", "text", "literal_column", "table",
    "column", "insert", "update", "delete",
}
BLOCKED_ATTRIBUTES = {"metadata", "registry", "__table__", "__mapper__", "with_for_update"}


def validate_python_expression(source: str) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        return [f"PYTHON_SYNTAX:{exc.msg}"]
    forbidden = (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp,
                 ast.GeneratorExp, ast.NamedExpr, ast.Await, ast.Yield,
                 ast.YieldFrom)
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            errors.append(f"FORBIDDEN_AST:{type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id in BLOCKED_NAMES:
                errors.append(f"BLOCKED_NAME:{node.id}")
            elif node.id not in SAFE_NAMESPACE:
                errors.append(f"UNKNOWN_NAME:{node.id}")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in BLOCKED_ATTRIBUTES):
            errors.append(f"BLOCKED_ATTRIBUTE:{node.attr}")
    return sorted(set(errors))


def build_statement(source: str) -> tuple[Select | CompoundSelect | None, list[str]]:
    errors = validate_python_expression(source)
    if errors:
        return None, errors
    try:
        statement = eval(compile(ast.parse(source, mode="eval"), "<phase42-query>", "eval"),
                         {"__builtins__": {}}, SAFE_NAMESPACE)
    except Exception as exc:  # noqa: BLE001
        return None, [f"BUILD_ERROR:{type(exc).__name__}:{exc}"]
    if not isinstance(statement, (Select, CompoundSelect)):
        return None, [f"NOT_READ_ONLY_SELECT:{type(statement).__name__}"]
    return statement, []


def compile_postgresql(statement: Select | CompoundSelect) -> tuple[str | None, list[str]]:
    try:
        sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    except Exception as exc:  # noqa: BLE001
        return None, [f"COMPILE_ERROR:{type(exc).__name__}:{exc}"]
    if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
        return None, ["COMPILED_SQL_NOT_READ_ONLY"]
    return sql, []


def _validation(source: str | None) -> ValidationResult:
    if not source:
        return {
            "syntax_errors": [],
            "build_errors": [],
            "compile_errors": [],
            "all_errors": [],
            "statement_built": False,
            "compiled_sql": None,
            "technically_valid": False,
        }
    syntax_errors = validate_python_expression(source)
    if syntax_errors:
        return {
            "syntax_errors": syntax_errors,
            "build_errors": [],
            "compile_errors": [],
            "all_errors": syntax_errors,
            "statement_built": False,
            "compiled_sql": None,
            "technically_valid": False,
        }
    statement, build_errors = build_statement(source)
    if statement is None or build_errors:
        return {
            "syntax_errors": [],
            "build_errors": build_errors,
            "compile_errors": [],
            "all_errors": build_errors,
            "statement_built": False,
            "compiled_sql": None,
            "technically_valid": False,
        }
    compiled_sql, compile_errors = compile_postgresql(statement)
    return {
        "syntax_errors": [],
        "build_errors": [],
        "compile_errors": compile_errors,
        "all_errors": compile_errors,
        "statement_built": True,
        "compiled_sql": compiled_sql,
        "technically_valid": not compile_errors and compiled_sql is not None,
    }


def _record(
    state: Phase42State,
    *,
    role: str,
    prompt: str,
    input_payload: Any,
    output: Any,
    latency_ms: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    event = {
        "role": role,
        "prompt": prompt,
        "input": input_payload,
        "output": output.model_dump(mode="json")
        if isinstance(output, BaseModel)
        else output,
        "model": state.get("models", {}).get(role),
        "latency_ms": latency_ms,
    }
    if metadata:
        event.update(metadata)
    state.setdefault("audit_trail", []).append(event)


def _parse(
    state: Phase42State,
    *,
    role: str,
    prompt: str,
    input_payload: Any,
    output_model: type[BaseModel],
) -> BaseModel:
    result, metadata = state["_llm"].invoke(
        role=role, input_payload=input_payload, output_model=output_model
    )
    _record(
        state,
        role=role,
        prompt=prompt,
        input_payload=input_payload,
        output=result,
        metadata=metadata,
    )
    return result


def _semantic_clarifier(state: Phase42State) -> dict[str, Any]:
    """Build the functional requirement from the current user request."""
    input_payload = {
        "user_request": state["question"],
        "reference_context": state["reference_context"],
        "data_model": _catalog(),
    }
    result = _parse(
        state,
        role="semantic_clarifier",
        prompt=SEMANTIC_CLARIFIER_PROMPT,
        input_payload=input_payload,
        output_model=FunctionalAnalystResponse,
    )
    task = QueryTask(
        original_user_request=result.original_user_request,
        clarified_request=result.clarified_request,
        business_intent=result.business_intent,
        required_information=result.required_information,
        measures=result.measures,
        dimensions=result.dimensions,
        filters=result.filters,
        temporal_requirements=result.temporal_requirements,
        grouping_requirements=result.grouping_requirements,
        ordering_requirements=result.ordering_requirements,
        comparison_requirements=result.comparison_requirements,
        data_retrieval_request=result.data_retrieval_request,
        downstream_analysis=result.downstream_analysis,
        assumptions=result.assumptions,
    )
    return {
        "functional_analysis": result.model_dump(mode="json"),
        "query_task": task.model_dump(mode="json"),
        "final_status": "NEEDS_CLARIFICATION" if result.needs_clarification else "",
    }


def _query_developer(state: Phase42State) -> dict[str, Any]:
    task = state["query_task"]
    repair_context = {}
    if state.get("current_query"):
        last_review = (state.get("senior_reviews") or [{}])[-1]
        repair_context = {
            "previous_query": state["current_query"],
            "validation_feedback": state.get("validation_result", {}),
            "senior_review": last_review,
        }
    input_payload = {
        "query_task": task,
        "data_model": _catalog(),
        "reference_context": REFERENCE_CONTEXT,
        **repair_context,
    }
    result = _parse(
        state,
        role="sqlalchemy_query_developer",
        prompt=SQLALCHEMY_QUERY_DEVELOPER_PROMPT,
        input_payload=input_payload,
        output_model=QueryProgrammerResponse,
    )
    attempts = state.setdefault("query_developer_attempts", [])
    attempts.append(result.model_dump(mode="json"))
    return {
        "current_query": result.model_dump(mode="json"),
        "query_developer_attempts": attempts,
    }


def _query_validation(state: Phase42State) -> dict[str, Any]:
    result = _validation(state.get("current_query", {}).get("sqlalchemy"))
    state.setdefault("audit_trail", []).append(
        {
            "role": "query_validation",
            "input": state.get("current_query"),
            "output": result,
            "model": None,
        }
    )
    return {"validation_result": result}


def _senior_query_reviewer(state: Phase42State) -> dict[str, Any]:
    input_payload = {
        "original_user_request": state["question"],
        "functional_requirement": state["functional_analysis"],
        "query_programmer_output": state.get("current_query"),
        "deterministic_validation_result": state.get("validation_result"),
        "data_model": _catalog(),
        "reference_context": REFERENCE_CONTEXT,
        "revision_count": state.get("revision_count", 0),
    }
    result = _parse(
        state,
        role="senior_query_reviewer",
        prompt=SENIOR_QUERY_REVIEWER_PROMPT,
        input_payload=input_payload,
        output_model=SeniorReview,
    )
    reviews = state.setdefault("senior_reviews", [])
    reviews.append(result.model_dump(mode="json"))
    return {"senior_reviews": reviews, "final_status": result.status}


def _after_clarifier(state: Phase42State) -> str:
    return "end" if state.get("final_status") == "NEEDS_CLARIFICATION" else "query_developer"


def _after_validation(state: Phase42State) -> str:
    if state.get("mode") == "QUERY_DEVELOPER_ONLY":
        return "end"
    return "senior"


def _after_senior(state: Phase42State) -> str:
    status = state.get("senior_reviews", [])[-1].get("status")
    if status == "APPROVED" and state.get("validation_result", {}).get("technically_valid"):
        return "end"
    if status == "CANNOT_APPROVE":
        return "end"
    if state.get("revision_count", 0) < MAX_REPAIR_ATTEMPTS:
        return "repair"
    return "max_revisions"


def _repair(state: Phase42State) -> dict[str, Any]:
    return {"revision_count": state.get("revision_count", 0) + 1}


def _max_revisions(state: Phase42State) -> dict[str, Any]:
    return {"final_status": "MAX_REVISIONS_REACHED"}


def build_graph() -> Any:
    graph = StateGraph(Phase42State)
    graph.add_node("semantic_clarifier", _semantic_clarifier)
    graph.add_node("query_developer", _query_developer)
    graph.add_node("query_validation", _query_validation)
    graph.add_node("senior_query_reviewer", _senior_query_reviewer)
    graph.add_node("repair", _repair)
    graph.add_node("max_revisions", _max_revisions)
    graph.add_edge(START, "semantic_clarifier")
    graph.add_conditional_edges(
        "semantic_clarifier",
        _after_clarifier,
        {"query_developer": "query_developer", "end": END},
    )
    graph.add_edge("query_developer", "query_validation")
    graph.add_conditional_edges(
        "query_validation",
        _after_validation,
        {"senior": "senior_query_reviewer", "repair": "repair", "end": END, "max_revisions": "max_revisions"},
    )
    graph.add_conditional_edges(
        "senior_query_reviewer",
        _after_senior,
        {"end": END, "repair": "repair", "max_revisions": "max_revisions"},
    )
    graph.add_edge("repair", "query_developer")
    graph.add_edge("max_revisions", END)
    return graph.compile()


def initial_state(
    *, mode: Literal["FUNCTIONAL_ANALYST_ONLY", "QUERY_DEVELOPER_ONLY", "AGENT_TEAM"], question: str, llm: StructuredModel
) -> Phase42State:
    return {
        "mode": mode,
        "question": question,
        "query_developer_attempts": [],
        "senior_reviews": [],
        "revision_count": 0,
        "final_status": "",
        "audit_trail": [],
        "reference_context": dict(REFERENCE_CONTEXT),
        "current_stage": "created",
        "stage_history": [],
        "models": {
            "semantic_clarifier": getattr(llm, "model_name", "unknown"),
            "sqlalchemy_query_developer": getattr(llm, "model_name", "unknown"),
            "senior_query_reviewer": getattr(llm, "model_name", "unknown"),
        },
        "_llm": llm,
    }


def assert_phase42_contract() -> None:
    assert "{{data_model}}" in SEMANTIC_CLARIFIER_PROMPT
    assert "{{data_model}}" in SQLALCHEMY_QUERY_DEVELOPER_PROMPT
    assert "{{data_model}}" in SENIOR_QUERY_REVIEWER_PROMPT
    developer_template = _prompt_templates()["sqlalchemy_query_developer"]
    assert developer_template.messages[0].prompt.template_format == "jinja2"
    rendered = developer_template.format_messages(
        data_model="class Employee", **REFERENCE_CONTEXT, user_input="{}"
    )
    assert "class Employee" in rendered[0].content
    assert "Reference date: 2026-08-30" in rendered[0].content
    assert REFERENCE_CONTEXT["current_period"] == "2026-08"
    assert "{{data_model}}" in SENIOR_QUERY_REVIEWER_PROMPT
    assert MAX_REPAIR_ATTEMPTS == 1
    assert _after_clarifier({"final_status": "NEEDS_CLARIFICATION"}) == "end"
    assert _after_clarifier({"final_status": ""}) == "query_developer"
    assert _after_validation({"mode": "QUERY_DEVELOPER_ONLY", "validation_result": {}}) == "end"
    assert _after_validation({"mode": "AGENT_TEAM", "validation_result": {"technically_valid": False}}) == "senior"
    assert _after_senior({"senior_reviews": [{"status": "REVISE"}], "revision_count": 0, "validation_result": {"technically_valid": True}}) == "repair"
    assert _after_senior({"senior_reviews": [{"status": "REVISE"}], "revision_count": 1, "validation_result": {"technically_valid": True}}) == "max_revisions"
    task = QueryTask(
        original_user_request="test", clarified_request="test",
        business_intent="test", required_information=["test"], measures=[],
        dimensions=[], filters=[], temporal_requirements=[],
        grouping_requirements=[], ordering_requirements=[],
        comparison_requirements=[], data_retrieval_request="test",
        downstream_analysis=[], assumptions=[],
    )
    assert "data_retrieval_request" in task.model_dump()

    class FakeModel:
        model_name = "fake"

        def __init__(self, outputs: list[BaseModel]) -> None:
            self.outputs = outputs

        def invoke(
            self, *, role: str, input_payload: dict[str, Any],
            output_model: type[BaseModel]
        ) -> tuple[BaseModel, dict[str, Any]]:
            result = self.outputs.pop(0)
            assert isinstance(result, output_model)
            return result, {
                "agent_id": role,
                "prompt_id": f"test.{role}",
                "prompt_version": "test",
                "model": self.model_name,
                "schema_version": output_model.__name__,
                "rendered_messages": [],
                "latency_ms": 0,
            }

    analysis = FunctionalAnalystResponse(
        needs_clarification=False, questions_or_missing_information=[],
        original_user_request="test", clarified_request="test",
        business_intent="test", domain=[], required_information=["test"],
        measures=[], dimensions=[], filters=[], temporal_requirements=[],
        grouping_requirements=[], ordering_requirements=[],
        comparison_requirements=[], data_retrieval_request="Retrieve the data.",
        downstream_analysis=[], required_sources=[], assumptions=[],
        ambiguities=[], unsupported_requirements=[], sensitivity=[],
    )
    query = QueryProgrammerResponse(
        status="QUERY", sqlalchemy="select(Overtime.approved_minutes)",
        interpretation="retrieve", assumptions=[], missing_information=[],
        models_used=["Overtime"], relationships_used=[], retrieved_measures=[],
        retrieved_dimensions=[], applied_filters=[],
        applied_temporal_constraints=[], grouping_implemented=[],
        requirement_coverage=[],
    )
    approve = SeniorReview(
        status="APPROVED", summary="valid", material_issues=[],
        requirement_review=[], query_semantics_review=QuerySemanticsReview(
            temporal_correctness="ok", measure_correctness="ok",
            dimension_correctness="ok", filter_correctness="ok",
            aggregation_correctness="ok", grouping_correctness="ok",
            ordering_correctness="ok", relationship_correctness="ok",
            duplicate_risk="none", data_sufficiency="ok",
            comparison_preservation="ok",
        ), repair_instructions=[],
        assumptions=[], missing_information=[], confidence=1,
    )
    graph = build_graph()
    approved = graph.invoke(initial_state(
        mode="AGENT_TEAM", question="test", llm=FakeModel([analysis, query, approve])
    ))
    assert approved["final_status"] == "APPROVED"
    assert len(approved["senior_reviews"]) == 1

    clarified = FunctionalAnalystResponse(
        needs_clarification=True, questions_or_missing_information=["metric"],
        original_user_request="test", clarified_request="test",
        business_intent="test", domain=[], required_information=[], measures=[],
        dimensions=[], filters=[], temporal_requirements=[], grouping_requirements=[],
        ordering_requirements=[], comparison_requirements=[], data_retrieval_request="",
        downstream_analysis=[], required_sources=[], assumptions=[], ambiguities=[],
        unsupported_requirements=[], sensitivity=[],
    )
    stopped = graph.invoke(initial_state(
        mode="AGENT_TEAM", question="test", llm=FakeModel([clarified])
    ))
    assert stopped["final_status"] == "NEEDS_CLARIFICATION"
    assert stopped.get("query_developer_attempts") == []

    revise = SeniorReview(
        status="REVISE", summary="revise", material_issues=[MaterialIssue(
            type="semantic", severity="ERROR", requirement="test", issue="issue",
            why_it_matters="material", required_correction="fix",
        )], requirement_review=[], query_semantics_review=QuerySemanticsReview(
            temporal_correctness="ok", measure_correctness="ok",
            dimension_correctness="ok", filter_correctness="ok",
            aggregation_correctness="ok", grouping_correctness="ok",
            ordering_correctness="ok", relationship_correctness="ok",
            duplicate_risk="none", data_sufficiency="ok",
            comparison_preservation="ok",
        ), repair_instructions=["fix"],
        assumptions=[], missing_information=[], confidence=0.9,
    )
    repaired = graph.invoke(initial_state(
        mode="AGENT_TEAM", question="test",
        llm=FakeModel([analysis, query, revise, query, approve]),
    ))
    assert repaired["final_status"] == "APPROVED"
    assert repaired["revision_count"] == 1
    assert len(repaired["senior_reviews"]) == 2

    invalid = QueryProgrammerResponse(
        status="QUERY", sqlalchemy="select(", interpretation="invalid",
        assumptions=[], missing_information=[], models_used=[], relationships_used=[],
        retrieved_measures=[], retrieved_dimensions=[], applied_filters=[],
        applied_temporal_constraints=[], grouping_implemented=[],
        requirement_coverage=[],
    )
    maxed = graph.invoke(initial_state(
        mode="AGENT_TEAM", question="test",
        llm=FakeModel([analysis, invalid, revise, invalid, revise]),
    ))
    assert maxed["final_status"] == "MAX_REVISIONS_REACHED"
    assert maxed["revision_count"] == 1


if __name__ == "__main__":
    assert_phase42_contract()
    print("DIRECT_SQLALCHEMY_PHASE42_SELF_TEST_OK")
