"""Phase 4.2 — independent agent-team query retrieval experiment."""
from __future__ import annotations

import ast
import json
import os
import time
import uuid
from datetime import date
from importlib.resources import files as resource_files
from typing import Any, Literal, Protocol, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (
    Date, ForeignKey, Integer, String, and_, asc, case, cast, desc, distinct,
    extract, func, literal, not_, or_, select, union, union_all,
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
    employees: Mapped[list["Employee"]] = relationship(back_populates="department")


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
    overtime: Mapped[list["Overtime"]] = relationship(back_populates="employee")
    attendance: Mapped[list["Attendance"]] = relationship(back_populates="employee")


class Overtime(Base):
    __tablename__ = "overtime_record"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"))
    work_date: Mapped[date] = mapped_column(Date)
    approved_minutes: Mapped[int] = mapped_column(
        Integer,
        info={"description": (
            "total approved minutes of overtime; convert to hours by dividing "
            "by 60.0 when hours are requested so decimals are preserved"
        )},
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


class PreviousIssueResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    previous_issue: str
    resolution_status: Literal[
        "RESOLVED", "PARTIALLY_RESOLVED", "UNRESOLVED", "NO_LONGER_APPLICABLE"
    ]
    evidence: str


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
    def validate_state(self) -> "QueryProgrammerResponse":
        if self.status == "QUERY" and not self.sqlalchemy:
            raise ValueError("QUERY requires sqlalchemy")
        if self.status != "QUERY" and self.sqlalchemy is not None:
            raise ValueError(f"{self.status} requires sqlalchemy=null")
        if self.status == "NEEDS_INFO" and not self.missing_information:
            raise ValueError("NEEDS_INFO requires missing_information")
        return self


class QueryTask(BaseModel):
    """Canonical downstream functional contract, without physical implementation decisions."""
    model_config = ConfigDict(extra="forbid")
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
    previous_issue_resolutions: list[PreviousIssueResolution] = Field(default_factory=list)


class ValidationDiagnostic(TypedDict, total=False):
    stage: str
    code: str
    exception_type: str | None
    message: str
    line: int | None
    offset: int | None
    text: str | None
    source: str | None


class ValidationResult(TypedDict):
    diagnostics: list[ValidationDiagnostic]
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
    technical_repair_attempts: int
    semantic_revision_attempts: int
    internal_tool_calls: int
    internal_validation_attempts: int
    internal_self_repair_attempts: int
    internal_self_repair_success: int
    internal_iterations: list[dict[str, Any]]
    internal_candidates_generated: int
    internal_candidates_changed: int
    internal_candidates_unchanged: int
    syntax_short_circuits: int
    build_short_circuits: int
    compile_attempts: int
    tool_calls_avoided_by_short_circuit: int
    candidate_valid_before_external_validator: bool
    external_validator_pass_after_internal_validation: bool
    repair_type: Literal["TECHNICAL", "SEMANTIC"] | None
    final_status: str
    audit_trail: list[dict[str, Any]]
    models: dict[str, str]
    request_id: str
    reference_context: dict[str, Any]
    current_stage: str
    stage_history: list[dict[str, Any]]
    _llm: StructuredModel


PHASE42_PROMPTS = resource_files("peopleops_api.resources.prompts.phase42")
SEMANTIC_CLARIFIER_PROMPT = PHASE42_PROMPTS.joinpath("functional-analyst.md").read_text(encoding="utf-8")
SQLALCHEMY_QUERY_DEVELOPER_PROMPT = PHASE42_PROMPTS.joinpath("sqlalchemy-query-programmer.md").read_text(encoding="utf-8")
SENIOR_QUERY_REVIEWER_PROMPT = PHASE42_PROMPTS.joinpath("senior-query-reviewer.md").read_text(encoding="utf-8")

MAX_TECHNICAL_REPAIR_ATTEMPTS = 2
MAX_SEMANTIC_REVISION_ATTEMPTS = 1
MAX_INTERNAL_SELF_REPAIR_ATTEMPTS = 2
REFERENCE_CONTEXT = {
    "reference_date": "2026-08-30",
    "reference_year": 2026,
    "reference_month": 8,
    "reference_day": 30,
    "current_period": "2026-08",
    "timezone": "UTC",
}
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
    return {
        "semantic_clarifier": ChatPromptTemplate.from_messages(
            [("system", SEMANTIC_CLARIFIER_PROMPT), ("human", "{{user_input}}")],
            template_format="jinja2",
        ),
        "sqlalchemy_query_developer": ChatPromptTemplate.from_messages(
            [("system", SQLALCHEMY_QUERY_DEVELOPER_PROMPT), ("human", "{{user_input}}")],
            template_format="jinja2",
        ),
        "senior_query_reviewer": ChatPromptTemplate.from_messages(
            [("system", SENIOR_QUERY_REVIEWER_PROMPT), ("human", "{{user_input}}")],
            template_format="jinja2",
        ),
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _human_payload(role: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Keep model/context only in the system prompt; human input carries typed artifacts."""
    if role == "semantic_clarifier":
        return {"user_request": payload["user_request"]}
    if role == "sqlalchemy_query_developer":
        return {
            "functional_requirement": payload["query_task"],
            "repair_type": payload.get("repair_type"),
            "repair_attempt": payload.get("repair_attempt", 0),
            "previous_query": payload.get("previous_query"),
            "deterministic_validation_result": payload.get("deterministic_validation_result"),
            "senior_review": payload.get("senior_review"),
            "internal_tool_results": payload.get("internal_tool_results", []),
        }
    return {
        "functional_requirement": payload["functional_requirement"],
        "query_programmer_output": payload["query_programmer_output"],
        "deterministic_validation_result": payload["deterministic_validation_result"],
        "previous_reviews": payload.get("previous_reviews", []),
        "repair_attempt": payload.get("repair_attempt", 0),
    }


class LangChainAgentRuntime:
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
        variables = _chain_variables(input_payload)
        human_payload = _human_payload(role, input_payload)
        variables["user_input"] = _json(human_payload)
        rendered = self.templates[role].format_messages(**variables)
        started = time.perf_counter()
        chain = self.templates[role] | self.models[role].with_structured_output(output_model)
        result = chain.invoke(variables)
        return result, {
            "agent_id": role,
            "prompt_id": spec["prompt_id"],
            "prompt_version": spec["prompt_version"],
            "model": self.model_config[role],
            "schema_version": output_model.__name__,
            "rendered_messages": [
                {"role": message.type, "content": message.content} for message in rendered
            ],
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "rendered_system_prompt": rendered[0].content,
        }

    def invoke_query_programmer(
        self, *, input_payload: dict[str, Any], output_model: type[BaseModel],
    ) -> tuple[BaseModel, dict[str, Any]]:
        """Run the programmer's bounded tool-assisted generation loop.

        The tools are deterministic application functions. Their diagnostics are
        fed back to the programmer as structured repair context; no Python or SQL
        is executed by the model.
        """
        payload = dict(input_payload)
        tool_events: list[dict[str, Any]] = []
        internal_iterations: list[dict[str, Any]] = []
        counters = {
            "syntax_short_circuits": 0, "build_short_circuits": 0,
            "compile_attempts": 0, "tool_calls_avoided_by_short_circuit": 0,
        }
        internal_repairs = 0
        previous_candidate: str | None = None
        while True:
            repair_input = _human_payload("sqlalchemy_query_developer", payload)
            result, metadata = self.invoke(
                role="sqlalchemy_query_developer",
                input_payload=payload,
                output_model=output_model,
            )
            tools_result, tool_stats = (
                _run_internal_tools(result.sqlalchemy) if result.status == "QUERY"
                else ([], {key: 0 for key in counters})
            )
            tool_events.extend(tools_result)
            counters = {key: counters[key] + tool_stats[key] for key in counters}
            candidate_valid = result.status == "QUERY" and all(
                item["valid"] for item in tools_result
            )
            candidate_changed = (
                None if previous_candidate is None else result.sqlalchemy != previous_candidate
            )
            iteration = {
                "iteration": len(internal_iterations) + 1,
                "candidate": result.sqlalchemy,
                "generation_type": (
                    "INITIAL" if not internal_iterations else "INTERNAL_TECHNICAL_REPAIR"
                ),
                "repair_input": repair_input,
                "tool_calls": [item["stage"] for item in tools_result],
                "tool_results": tools_result,
                "validation_status": (
                    "VALID" if candidate_valid else "INVALID"
                    if result.status == "QUERY" else "NOT_APPLICABLE"
                ),
                "errors": [item["message"] for item in tools_result if not item["valid"]],
                "candidate_changed": candidate_changed,
                "final_iteration": False,
            }
            internal_iterations.append(iteration)
            if result.status != "QUERY" or candidate_valid:
                iteration["final_iteration"] = True
                metadata = {
                    **metadata,
                    "tool_assisted": True,
                    "internal_tool_events": tool_events,
                    "internal_tool_calls": len(tool_events),
                    "internal_validation_attempts": (
                        1 + internal_repairs if result.status == "QUERY" else 0
                    ),
                    "internal_self_repair_attempts": internal_repairs,
                    "internal_self_repair_success": (
                        1 if internal_repairs and candidate_valid and candidate_changed else 0
                    ),
                    "candidate_valid_before_external_validator": candidate_valid,
                    "internal_iterations": internal_iterations,
                    "internal_candidates_generated": len(internal_iterations),
                    "internal_candidates_changed": sum(
                        item["candidate_changed"] is True for item in internal_iterations
                    ),
                    "internal_candidates_unchanged": sum(
                        item["candidate_changed"] is False for item in internal_iterations
                    ),
                    **counters,
                }
                return result, metadata
            if internal_repairs >= MAX_INTERNAL_SELF_REPAIR_ATTEMPTS:
                iteration["final_iteration"] = True
                metadata = {
                    **metadata,
                    "tool_assisted": True,
                    "internal_tool_events": tool_events,
                    "internal_tool_calls": len(tool_events),
                    "internal_validation_attempts": 1 + internal_repairs,
                    "internal_self_repair_attempts": internal_repairs,
                    "internal_self_repair_success": 0,
                    "candidate_valid_before_external_validator": False,
                    "internal_iterations": internal_iterations,
                    "internal_candidates_generated": len(internal_iterations),
                    "internal_candidates_changed": sum(
                        item["candidate_changed"] is True for item in internal_iterations
                    ),
                    "internal_candidates_unchanged": sum(
                        item["candidate_changed"] is False for item in internal_iterations
                    ),
                    **counters,
                }
                return result, metadata
            internal_repairs += 1
            payload["repair_type"] = "INTERNAL_SELF_REPAIR"
            payload["repair_attempt"] = internal_repairs
            payload["previous_query"] = result.model_dump(mode="json")
            payload["internal_tool_results"] = tools_result
            previous_candidate = result.sqlalchemy


def _chain_variables(payload: dict[str, Any]) -> dict[str, str]:
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
                f"relationship key: {model.__name__}.{local.key} {arrow} {target.__name__}.{remote.key}"
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


def _syntax_validation(source: str) -> tuple[list[str], list[ValidationDiagnostic]]:
    errors: list[str] = []
    diagnostics: list[ValidationDiagnostic] = []
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        code = f"PYTHON_SYNTAX:{exc.msg}"
        return [code], [{
            "stage": "PYTHON_SYNTAX",
            "code": "PYTHON_SYNTAX",
            "exception_type": type(exc).__name__,
            "message": exc.msg,
            "line": exc.lineno,
            "offset": exc.offset,
            "text": exc.text.strip() if exc.text else None,
            "source": source,
        }]
    forbidden = (
        ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
        ast.NamedExpr, ast.Await, ast.Yield, ast.YieldFrom,
    )
    for node in ast.walk(tree):
        code: str | None = None
        if isinstance(node, forbidden):
            code = f"FORBIDDEN_AST:{type(node).__name__}"
        elif isinstance(node, ast.Name):
            if node.id in BLOCKED_NAMES:
                code = f"BLOCKED_NAME:{node.id}"
            elif node.id not in SAFE_NAMESPACE:
                code = f"UNKNOWN_NAME:{node.id}"
        elif isinstance(node, ast.Attribute) and (
            node.attr.startswith("_") or node.attr in BLOCKED_ATTRIBUTES
        ):
            code = f"BLOCKED_ATTRIBUTE:{node.attr}"
        if code and code not in errors:
            errors.append(code)
            diagnostics.append({
                "stage": "AST_SAFETY",
                "code": code.split(":", 1)[0],
                "exception_type": None,
                "message": code,
                "line": getattr(node, "lineno", None),
                "offset": getattr(node, "col_offset", None),
                "text": None,
                "source": source,
            })
    return errors, diagnostics


def validate_python_expression(source: str) -> list[str]:
    return _syntax_validation(source)[0]


def build_statement(source: str) -> tuple[Select | CompoundSelect | None, list[str]]:
    errors, _ = _syntax_validation(source)
    if errors:
        return None, errors
    try:
        statement = eval(
            compile(ast.parse(source, mode="eval"), "<phase42-query>", "eval"),
            {"__builtins__": {}},
            SAFE_NAMESPACE,
        )
    except Exception as exc:  # noqa: BLE001
        return None, [f"BUILD_ERROR:{type(exc).__name__}:{exc}"]
    if not isinstance(statement, (Select, CompoundSelect)):
        return None, [f"NOT_READ_ONLY_SELECT:{type(statement).__name__}"]
    return statement, []


def compile_postgresql(statement: Select | CompoundSelect) -> tuple[str | None, list[str]]:
    try:
        sql = str(statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        ))
    except Exception as exc:  # noqa: BLE001
        return None, [f"COMPILE_ERROR:{type(exc).__name__}:{exc}"]
    if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
        return None, ["COMPILED_SQL_NOT_READ_ONLY"]
    return sql, []


def _validation(source: str | None) -> ValidationResult:
    empty: ValidationResult = {
        "diagnostics": [],
        "syntax_errors": [],
        "build_errors": [],
        "compile_errors": [],
        "all_errors": [],
        "statement_built": False,
        "compiled_sql": None,
        "technically_valid": False,
    }
    if not source:
        empty["diagnostics"] = [{
            "stage": "INPUT", "code": "MISSING_QUERY", "exception_type": None,
            "message": "No SQLAlchemy expression was provided.", "source": source,
        }]
        empty["all_errors"] = ["MISSING_QUERY"]
        return empty

    syntax_errors, diagnostics = _syntax_validation(source)
    if syntax_errors:
        return {**empty, "diagnostics": diagnostics, "syntax_errors": syntax_errors, "all_errors": syntax_errors}

    try:
        statement = eval(
            compile(ast.parse(source, mode="eval"), "<phase42-query>", "eval"),
            {"__builtins__": {}},
            SAFE_NAMESPACE,
        )
    except Exception as exc:  # noqa: BLE001
        error = f"BUILD_ERROR:{type(exc).__name__}:{exc}"
        diagnostic: ValidationDiagnostic = {
            "stage": "SQLALCHEMY_BUILD", "code": "BUILD_ERROR",
            "exception_type": type(exc).__name__, "message": str(exc), "source": source,
        }
        return {**empty, "diagnostics": [diagnostic], "build_errors": [error], "all_errors": [error]}

    if not isinstance(statement, (Select, CompoundSelect)):
        error = f"NOT_READ_ONLY_SELECT:{type(statement).__name__}"
        diagnostic = {
            "stage": "READ_ONLY", "code": "NOT_READ_ONLY_SELECT",
            "exception_type": None, "message": error, "source": source,
        }
        return {**empty, "diagnostics": [diagnostic], "build_errors": [error], "all_errors": [error]}

    try:
        sql = str(statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        ))
    except Exception as exc:  # noqa: BLE001
        error = f"COMPILE_ERROR:{type(exc).__name__}:{exc}"
        diagnostic = {
            "stage": "SQLALCHEMY_COMPILE", "code": "COMPILE_ERROR",
            "exception_type": type(exc).__name__, "message": str(exc), "source": source,
        }
        return {
            **empty, "diagnostics": [diagnostic], "compile_errors": [error],
            "all_errors": [error], "statement_built": True,
        }

    if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
        error = "COMPILED_SQL_NOT_READ_ONLY"
        diagnostic = {
            "stage": "READ_ONLY", "code": error, "exception_type": None,
            "message": error, "source": source,
        }
        return {
            **empty, "diagnostics": [diagnostic], "compile_errors": [error],
            "all_errors": [error], "statement_built": True, "compiled_sql": sql,
        }

    return {
        **empty, "statement_built": True, "compiled_sql": sql, "technically_valid": True
    }


def _tool_diagnostic(
    *, stage: str, valid: bool, source: str | None,
    message: str, exception_type: str | None = None,
    line: int | None = None, offset: int | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "valid": valid,
        "exception_type": exception_type,
        "message": message,
        "line": line,
        "offset": offset,
        "text": text,
        "source": source,
    }


def validate_python_syntax(source: str | None) -> dict[str, Any]:
    """Deterministically validate the candidate as one safe Python expression."""
    if not source:
        return _tool_diagnostic(
            stage="PYTHON_SYNTAX", valid=False, source=source,
            message="No SQLAlchemy expression was provided.",
        )
    errors, diagnostics = _syntax_validation(source)
    if errors:
        diagnostic = diagnostics[0]
        return _tool_diagnostic(
            stage="PYTHON_SYNTAX", valid=False, source=source,
            message=diagnostic.get("message", errors[0]),
            exception_type=diagnostic.get("exception_type"),
            line=diagnostic.get("line"), offset=diagnostic.get("offset"),
            text=diagnostic.get("text"),
        )
    return _tool_diagnostic(
        stage="PYTHON_SYNTAX", valid=True, source=source,
        message="Python expression syntax is valid.",
    )


def build_sqlalchemy_query(source: str | None) -> dict[str, Any]:
    """Build a candidate in the closed SQLAlchemy namespace without executing it."""
    syntax = validate_python_syntax(source)
    if not syntax["valid"]:
        return syntax
    return _build_sqlalchemy_query(source, syntax_checked=True)[0]


def _build_sqlalchemy_query(
    source: str | None, *, syntax_checked: bool = False,
) -> tuple[dict[str, Any], Select | CompoundSelect | None]:
    if not syntax_checked:
        syntax = validate_python_syntax(source)
        if not syntax["valid"]:
            return syntax, None
    statement, errors = build_statement(source or "")
    if errors:
        error = errors[0]
        return _tool_diagnostic(
            stage="SQLALCHEMY_BUILD", valid=False, source=source,
            message=error,
            exception_type=error.split(":", 2)[1] if error.startswith("BUILD_ERROR:") else None,
        ), None
    return _tool_diagnostic(
        stage="SQLALCHEMY_BUILD", valid=True, source=source,
        message=f"Built read-only {type(statement).__name__} expression.",
    ), statement


def compile_sqlalchemy_query(
    source: str | None, statement: Select | CompoundSelect | None = None,
) -> dict[str, Any]:
    """Compile a safely built candidate for PostgreSQL without database access."""
    if statement is None:
        built, statement = _build_sqlalchemy_query(source)
    else:
        built = _tool_diagnostic(
            stage="SQLALCHEMY_BUILD", valid=True, source=source,
            message=f"Built read-only {type(statement).__name__} expression.",
        )
    if not built["valid"] or statement is None:
        return {
            **built,
            "stage": "SQLALCHEMY_COMPILE",
            "message": f"Cannot compile candidate: {built['message']}",
        }
    compiled, errors = compile_postgresql(statement)
    if errors:
        return _tool_diagnostic(
            stage="SQLALCHEMY_COMPILE", valid=False, source=source,
            message=errors[0],
        )
    return {
        **_tool_diagnostic(
            stage="SQLALCHEMY_COMPILE", valid=True, source=source,
            message="Candidate compiles as read-only PostgreSQL SQLAlchemy.",
        ),
        "compiled_sql": compiled,
    }


def _run_internal_tools(
    source: str | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    events: list[dict[str, Any]] = []
    stats = {
        "syntax_short_circuits": 0,
        "build_short_circuits": 0,
        "compile_attempts": 0,
        "tool_calls_avoided_by_short_circuit": 0,
    }
    syntax = validate_python_syntax(source)
    events.append(syntax)
    if not syntax["valid"]:
        stats["syntax_short_circuits"] = 1
        stats["tool_calls_avoided_by_short_circuit"] = 2
        return events, stats
    built, statement = _build_sqlalchemy_query(source, syntax_checked=True)
    events.append(built)
    if not built["valid"]:
        stats["build_short_circuits"] = 1
        stats["tool_calls_avoided_by_short_circuit"] = 1
        return events, stats
    stats["compile_attempts"] = 1
    events.append(compile_sqlalchemy_query(source, statement=statement))
    return events, stats


def _transition(state: Phase42State, stage: str, status: str = "entered") -> None:
    state["current_stage"] = stage
    state.setdefault("stage_history", []).append({"stage": stage, "status": status})


def _record(
    state: Phase42State, *, role: str, prompt: str | None,
    input_payload: Any, output: Any, metadata: dict[str, Any] | None = None,
) -> None:
    event = {
        "role": role,
        "prompt": prompt,
        "input": input_payload,
        "output": output.model_dump(mode="json") if isinstance(output, BaseModel) else output,
        "model": state.get("models", {}).get(role),
    }
    if metadata:
        event.update(metadata)
    state.setdefault("audit_trail", []).append(event)


def _parse(
    state: Phase42State, *, role: str, prompt: str, input_payload: dict[str, Any],
    output_model: type[BaseModel],
) -> BaseModel:
    result, metadata = state["_llm"].invoke(
        role=role, input_payload=input_payload, output_model=output_model
    )
    _record(
        state, role=role, prompt=prompt, input_payload=_human_payload(role, input_payload),
        output=result, metadata=metadata,
    )
    return result


def _semantic_clarifier(state: Phase42State) -> dict[str, Any]:
    _transition(state, "functional_analysis")
    input_payload = {
        "user_request": state["question"],
        "reference_context": state["reference_context"],
        "data_model": _catalog(),
    }
    result = _parse(
        state, role="semantic_clarifier", prompt=SEMANTIC_CLARIFIER_PROMPT,
        input_payload=input_payload, output_model=FunctionalAnalystResponse,
    )
    task = QueryTask(
        original_user_request=result.original_user_request,
        clarified_request=result.clarified_request,
        business_intent=result.business_intent,
        domain=result.domain,
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
        required_sources=result.required_sources,
        assumptions=result.assumptions,
        ambiguities=result.ambiguities,
        unsupported_requirements=result.unsupported_requirements,
        sensitivity=result.sensitivity,
    )
    return {
        "functional_analysis": result.model_dump(mode="json"),
        "query_task": task.model_dump(mode="json"),
        "final_status": "NEEDS_CLARIFICATION" if result.needs_clarification else "",
    }


def _query_developer(state: Phase42State) -> dict[str, Any]:
    _transition(state, "query_generation")
    repair_type = state.get("repair_type")
    repair_attempt = (
        state.get("technical_repair_attempts", 0)
        if repair_type == "TECHNICAL"
        else state.get("semantic_revision_attempts", 0)
        if repair_type == "SEMANTIC"
        else 0
    )
    input_payload = {
        "query_task": state["query_task"],
        "data_model": _catalog(),
        "reference_context": state["reference_context"],
        "repair_type": repair_type,
        "repair_attempt": repair_attempt,
        "previous_query": state.get("current_query"),
        "deterministic_validation_result": (
            state.get("validation_result") if repair_type == "TECHNICAL" else None
        ),
        "senior_review": (
            (state.get("senior_reviews") or [None])[-1] if repair_type == "SEMANTIC" else None
        ),
    }
    runtime = state["_llm"]
    if hasattr(runtime, "invoke_query_programmer"):
        result, metadata = runtime.invoke_query_programmer(
            input_payload=input_payload, output_model=QueryProgrammerResponse,
        )
        _record(
            state, role="sqlalchemy_query_developer",
            prompt=SQLALCHEMY_QUERY_DEVELOPER_PROMPT,
            input_payload=_human_payload("sqlalchemy_query_developer", input_payload),
            output=result, metadata=metadata,
        )
        for iteration in metadata.get("internal_iterations", []):
            _record(
                state, role="query_programmer_internal_iteration", prompt=None,
                input_payload=iteration["repair_input"], output=iteration,
            )
    else:
        result = _parse(
            state, role="sqlalchemy_query_developer",
            prompt=SQLALCHEMY_QUERY_DEVELOPER_PROMPT,
            input_payload=input_payload, output_model=QueryProgrammerResponse,
        )
        metadata = {}
    attempts = list(state.get("query_developer_attempts", []))
    attempts.append({
        **result.model_dump(mode="json"),
        "_attempt_kind": repair_type or "INITIAL",
        "_attempt_number": repair_attempt,
    })
    final_status = ""
    if result.status == "NEEDS_INFO":
        final_status = "NEEDS_INFO"
    elif result.status == "CANNOT_IMPLEMENT":
        final_status = "CANNOT_IMPLEMENT"
    internal_valid = bool(metadata.get("candidate_valid_before_external_validator", False))
    return {
        "current_query": result.model_dump(mode="json"),
        "query_developer_attempts": attempts,
        "final_status": final_status,
        "internal_tool_calls": state.get("internal_tool_calls", 0) + metadata.get(
            "internal_tool_calls", 0
        ),
        "internal_validation_attempts": state.get("internal_validation_attempts", 0) + metadata.get(
            "internal_validation_attempts", 0
        ),
        "internal_self_repair_attempts": state.get("internal_self_repair_attempts", 0) + metadata.get(
            "internal_self_repair_attempts", 0
        ),
        "internal_self_repair_success": state.get("internal_self_repair_success", 0) + metadata.get(
            "internal_self_repair_success", 0
        ),
        "internal_iterations": state.get("internal_iterations", []) + metadata.get(
            "internal_iterations", []
        ),
        "internal_candidates_generated": state.get("internal_candidates_generated", 0) + metadata.get(
            "internal_candidates_generated", 0
        ),
        "internal_candidates_changed": state.get("internal_candidates_changed", 0) + metadata.get(
            "internal_candidates_changed", 0
        ),
        "internal_candidates_unchanged": state.get("internal_candidates_unchanged", 0) + metadata.get(
            "internal_candidates_unchanged", 0
        ),
        "syntax_short_circuits": state.get("syntax_short_circuits", 0) + metadata.get(
            "syntax_short_circuits", 0
        ),
        "build_short_circuits": state.get("build_short_circuits", 0) + metadata.get(
            "build_short_circuits", 0
        ),
        "compile_attempts": state.get("compile_attempts", 0) + metadata.get(
            "compile_attempts", 0
        ),
        "tool_calls_avoided_by_short_circuit": state.get(
            "tool_calls_avoided_by_short_circuit", 0
        ) + metadata.get("tool_calls_avoided_by_short_circuit", 0),
        "candidate_valid_before_external_validator": internal_valid,
    }


def _query_validation(state: Phase42State) -> dict[str, Any]:
    _transition(state, "technical_validation")
    result = _validation(state.get("current_query", {}).get("sqlalchemy"))
    _record(
        state, role="query_validation", prompt=None,
        input_payload=state.get("current_query"), output=result,
    )
    return {
        "validation_result": result,
        "external_validator_pass_after_internal_validation": bool(
            state.get("candidate_valid_before_external_validator") and result["technically_valid"]
        ),
    }


def _senior_query_reviewer(state: Phase42State) -> dict[str, Any]:
    if not state.get("validation_result", {}).get("technically_valid"):
        raise RuntimeError("Senior Query Reviewer must only receive technically valid queries")
    _transition(state, "senior_review")
    input_payload = {
        "functional_requirement": state["functional_analysis"],
        "query_programmer_output": state["current_query"],
        "deterministic_validation_result": state["validation_result"],
        "previous_reviews": state.get("senior_reviews", []),
        "repair_attempt": state.get("semantic_revision_attempts", 0),
        "data_model": _catalog(),
        "reference_context": state["reference_context"],
    }
    result = _parse(
        state, role="senior_query_reviewer", prompt=SENIOR_QUERY_REVIEWER_PROMPT,
        input_payload=input_payload, output_model=SeniorReview,
    )
    reviews = list(state.get("senior_reviews", []))
    reviews.append(result.model_dump(mode="json"))
    return {"senior_reviews": reviews, "final_status": result.status}


def _technical_repair(state: Phase42State) -> dict[str, Any]:
    _transition(state, "technical_repair")
    return {
        "technical_repair_attempts": state.get("technical_repair_attempts", 0) + 1,
        "repair_type": "TECHNICAL",
        "final_status": "",
    }


def _semantic_repair(state: Phase42State) -> dict[str, Any]:
    _transition(state, "semantic_repair")
    return {
        "semantic_revision_attempts": state.get("semantic_revision_attempts", 0) + 1,
        "repair_type": "SEMANTIC",
        "final_status": "",
    }


def _technical_failed(state: Phase42State) -> dict[str, Any]:
    _transition(state, "failed", "technical_validation_failed")
    return {"final_status": "TECHNICAL_VALIDATION_FAILED"}


def _semantic_failed(state: Phase42State) -> dict[str, Any]:
    _transition(state, "failed", "semantic_revision_limit_reached")
    return {"final_status": "MAX_SEMANTIC_REVISIONS_REACHED"}


def _after_clarifier(state: Phase42State) -> str:
    if state.get("final_status") == "NEEDS_CLARIFICATION":
        return "end"
    return "query_developer"


def _after_query_developer(state: Phase42State) -> str:
    status = state.get("current_query", {}).get("status")
    if status == "QUERY":
        return "validation"
    return "end"


def _after_validation(state: Phase42State) -> str:
    if state.get("mode") == "QUERY_DEVELOPER_ONLY":
        return "end"
    if state.get("validation_result", {}).get("technically_valid"):
        return "senior"
    if state.get("technical_repair_attempts", 0) < MAX_TECHNICAL_REPAIR_ATTEMPTS:
        return "technical_repair"
    return "technical_failed"


def _after_senior(state: Phase42State) -> str:
    status = state.get("senior_reviews", [])[-1]["status"]
    if status in {"APPROVED", "CANNOT_APPROVE"}:
        return "end"
    if state.get("semantic_revision_attempts", 0) < MAX_SEMANTIC_REVISION_ATTEMPTS:
        return "semantic_repair"
    return "semantic_failed"


def build_graph() -> Any:
    graph = StateGraph(Phase42State)
    graph.add_node("semantic_clarifier", _semantic_clarifier)
    graph.add_node("query_developer", _query_developer)
    graph.add_node("query_validation", _query_validation)
    graph.add_node("technical_repair", _technical_repair)
    graph.add_node("technical_failed", _technical_failed)
    graph.add_node("senior_query_reviewer", _senior_query_reviewer)
    graph.add_node("semantic_repair", _semantic_repair)
    graph.add_node("semantic_failed", _semantic_failed)

    graph.add_edge(START, "semantic_clarifier")
    graph.add_conditional_edges(
        "semantic_clarifier", _after_clarifier,
        {"query_developer": "query_developer", "end": END},
    )
    graph.add_conditional_edges(
        "query_developer", _after_query_developer,
        {"validation": "query_validation", "end": END},
    )
    graph.add_conditional_edges(
        "query_validation", _after_validation,
        {
            "senior": "senior_query_reviewer",
            "technical_repair": "technical_repair",
            "technical_failed": "technical_failed",
            "end": END,
        },
    )
    graph.add_edge("technical_repair", "query_developer")
    graph.add_edge("technical_failed", END)
    graph.add_conditional_edges(
        "senior_query_reviewer", _after_senior,
        {
            "end": END,
            "semantic_repair": "semantic_repair",
            "semantic_failed": "semantic_failed",
        },
    )
    graph.add_edge("semantic_repair", "query_developer")
    graph.add_edge("semantic_failed", END)
    return graph.compile()


def initial_state(
    *, mode: Literal["FUNCTIONAL_ANALYST_ONLY", "QUERY_DEVELOPER_ONLY", "AGENT_TEAM"],
    question: str, llm: StructuredModel, reference_context: dict[str, Any] | None = None,
) -> Phase42State:
    return {
        "mode": mode,
        "question": question,
        "query_developer_attempts": [],
        "senior_reviews": [],
        "technical_repair_attempts": 0,
        "semantic_revision_attempts": 0,
        "internal_tool_calls": 0,
        "internal_validation_attempts": 0,
        "internal_self_repair_attempts": 0,
        "internal_self_repair_success": 0,
        "internal_iterations": [],
        "internal_candidates_generated": 0,
        "internal_candidates_changed": 0,
        "internal_candidates_unchanged": 0,
        "syntax_short_circuits": 0,
        "build_short_circuits": 0,
        "compile_attempts": 0,
        "tool_calls_avoided_by_short_circuit": 0,
        "candidate_valid_before_external_validator": False,
        "external_validator_pass_after_internal_validation": False,
        "repair_type": None,
        "final_status": "",
        "audit_trail": [],
        "reference_context": dict(reference_context or REFERENCE_CONTEXT),
        "request_id": str(uuid.uuid4()),
        "current_stage": "created",
        "stage_history": [{"stage": "created", "status": "created"}],
        "models": {
            "semantic_clarifier": getattr(llm, "model_name", "unknown"),
            "sqlalchemy_query_developer": getattr(llm, "model_name", "unknown"),
            "senior_query_reviewer": getattr(llm, "model_name", "unknown"),
        },
        "_llm": llm,
    }


def assert_phase42_contract() -> None:
    for prompt in (
        SEMANTIC_CLARIFIER_PROMPT,
        SQLALCHEMY_QUERY_DEVELOPER_PROMPT,
        SENIOR_QUERY_REVIEWER_PROMPT,
    ):
        assert prompt.count("{{data_model}}") == 1
        for key in (
            "reference_date", "reference_year", "reference_month",
            "reference_day", "current_period", "timezone",
        ):
            assert prompt.count("{{" + key + "}}") == 1

    template = _prompt_templates()["sqlalchemy_query_developer"]
    rendered = template.format_messages(
        data_model="class Employee", **REFERENCE_CONTEXT, user_input="{}"
    )
    assert rendered[0].content.count("class Employee") == 1
    assert _after_validation({
        "mode": "AGENT_TEAM",
        "validation_result": {"technically_valid": False},
        "technical_repair_attempts": 0,
    }) == "technical_repair"
    assert _after_validation({
        "mode": "AGENT_TEAM",
        "validation_result": {"technically_valid": True},
    }) == "senior"
    assert _after_query_developer({"current_query": {"status": "CANNOT_IMPLEMENT"}}) == "end"

    invalid = _validation("select(")
    assert not invalid["technically_valid"]
    assert invalid["diagnostics"][0]["stage"] == "PYTHON_SYNTAX"
    assert invalid["diagnostics"][0].get("line") == 1

    valid = _validation("select(Overtime.approved_minutes)")
    assert valid["technically_valid"]
    assert valid["compiled_sql"]

    task = QueryTask(
        original_user_request="test", clarified_request="test", business_intent="test",
        domain=["overtime"], required_information=["test"], measures=[], dimensions=[],
        filters=[], temporal_requirements=[], grouping_requirements=[],
        ordering_requirements=[], comparison_requirements=[],
        data_retrieval_request="Retrieve the data.", downstream_analysis=[],
        required_sources=["HRIS_STRUCTURED_DATA"], assumptions=[], ambiguities=[],
        unsupported_requirements=[], sensitivity=[],
    )
    assert "unsupported_requirements" in task.model_dump()


if __name__ == "__main__":
    assert_phase42_contract()
    print("DIRECT_SQLALCHEMY_PHASE42_SELF_TEST_OK")
