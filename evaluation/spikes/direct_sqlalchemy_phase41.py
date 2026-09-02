"""Phase 4.1 — Direct SQLAlchemy 2.x query-generation PoC.

This experiment replaces the Eloquent-like surface with native SQLAlchemy 2.x.
The first LLM receives only logical ORM class names, attributes, relationships,
and the reference date. It returns either a SQLAlchemy SELECT expression or
NEEDS_INFO. The generated expression is parsed, evaluated in a restricted
namespace, compiled by SQLAlchemy itself to PostgreSQL SQL, and can optionally be
executed read-only against the synthetic HRIS.

Physical table names are deliberately hidden from the prompt. They remain inside
the SQLAlchemy mappings, mirroring the future provider/MCP ownership boundary.
"""
from __future__ import annotations

import ast
from datetime import date
from typing import Literal

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
    approved_minutes: Mapped[int] = mapped_column(Integer)
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


class SQLAlchemyGenerationResponse(BaseModel):
    """Thin envelope around SQLAlchemy source text, not a query AST."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["QUERY", "NEEDS_INFO"]
    sqlalchemy: str | None = None
    interpretation: str
    assumptions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state(self) -> SQLAlchemyGenerationResponse:
        if self.status == "QUERY" and not self.sqlalchemy:
            raise ValueError("QUERY requires sqlalchemy")
        if self.status == "NEEDS_INFO" and not self.missing_information:
            raise ValueError("NEEDS_INFO requires missing_information")
        return self


def conceptual_catalog_text() -> str:
    """Render ORM-facing logical metadata without physical table names."""
    blocks: list[str] = []
    for model in MODELS:
        mapper = model.__mapper__
        lines = [f"class {model.__name__}", "attributes:"]
        for column_property in mapper.column_attrs:
            column = column_property.columns[0]
            lines.append(f"  - {column_property.key}: {column.type}")
        lines.append("relationships:")
        for relation in mapper.relationships:
            direction = "many" if relation.uselist else "one"
            lines.append(f"  - {relation.key}: {direction} -> {relation.mapper.class_.__name__}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


GENERATION_PROMPT = f"""
You translate an HR analytics request directly into SQLAlchemy 2.x ORM query
code over the logical models below.

Reference date: 2026-08-30.
Timezone: UTC.

Return one of two outcomes:

QUERY
- Provide one Python expression that evaluates to a SQLAlchemy Select or
  CompoundSelect.
- Use SQLAlchemy 2.x select() style, not legacy Session.query().
- The expression may use joins, aliases expressed through subqueries/CTEs,
  UNION/UNION ALL, CASE, aggregate functions, date extraction, window
  functions, subqueries, and any other normal READ-ONLY SQLAlchemy query
  composition available through the provided namespace.
- Do not artificially avoid UNION or other legitimate query constructs.
- Do not emit SQL text and do not use raw textual SQL helpers.
- Never generate INSERT, UPDATE, DELETE, MERGE, DDL, locking queries, imports,
  or arbitrary Python side effects.
- Explain exactly what the query returns in interpretation.
- If you choose one reasonable interpretation of ambiguous wording, state that
  explicitly in assumptions. A QUERY with a declared assumption is acceptable
  when it is a defensible interpretation.

NEEDS_INFO
- Use this only when no responsible read-only query can be produced without
  inventing essential business meaning.
- State precisely what information is missing.

Planning guidance:
- Do not add employee, department, status, or other filters unless requested.
- Ordinary calendar expressions should be resolved from the reference date.
- If the user asks for overtime quantitatively (total, accumulated amount,
  comparison, trend), Overtime.approved_minutes is the available quantitative
  measure. For record/projection requests, select fields instead of forcing an
  aggregate.
- Comparisons may use one grouped query, several branches combined with UNION,
  conditional aggregates, subqueries, or another natural SQLAlchemy strategy.
  Do not force comparison into a binary schema.
- Three or more periods are valid query-planning problems, not automatic
  NEEDS_INFO cases.
- For percentage change, it is acceptable to retrieve the source aggregates
  needed for the calculation and explain that interpretation if computing the
  percentage in-query would make the expression less clear.

Available names in the execution namespace include:
select, func, and_, or_, not_, case, cast, literal, distinct, extract,
union, union_all, asc, desc, date, Integer, String, Date,
and the ORM models below.

Logical ORM models:
{conceptual_catalog_text()}
""".strip()


SAFE_NAMESPACE = {
    "Employee": Employee,
    "Department": Department,
    "Overtime": Overtime,
    "Attendance": Attendance,
    "select": select,
    "func": func,
    "and_": and_,
    "or_": or_,
    "not_": not_,
    "case": case,
    "cast": cast,
    "literal": literal,
    "distinct": distinct,
    "extract": extract,
    "union": union,
    "union_all": union_all,
    "asc": asc,
    "desc": desc,
    "date": date,
    "Integer": Integer,
    "String": String,
    "Date": Date,
}

BLOCKED_NAMES = {
    "__import__",
    "eval",
    "exec",
    "open",
    "compile",
    "globals",
    "locals",
    "getattr",
    "setattr",
    "delattr",
    "text",
    "literal_column",
    "table",
    "column",
    "insert",
    "update",
    "delete",
}

BLOCKED_ATTRIBUTES = {
    "metadata",
    "registry",
    "__table__",
    "__mapper__",
    "with_for_update",
}


def validate_python_expression(source: str) -> list[str]:
    """Validate Python/SQLAlchemy safety without interpreting query semantics."""
    errors: list[str] = []
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        return [f"PYTHON_SYNTAX:{exc.msg}"]

    forbidden_nodes = (
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
        ast.NamedExpr,
        ast.Await,
        ast.Yield,
        ast.YieldFrom,
    )
    for node in ast.walk(tree):
        if isinstance(node, forbidden_nodes):
            errors.append(f"FORBIDDEN_AST:{type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id in BLOCKED_NAMES:
                errors.append(f"BLOCKED_NAME:{node.id}")
            elif node.id not in SAFE_NAMESPACE:
                errors.append(f"UNKNOWN_NAME:{node.id}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr in BLOCKED_ATTRIBUTES:
                errors.append(f"BLOCKED_ATTRIBUTE:{node.attr}")
    return sorted(set(errors))


def build_statement(source: str) -> tuple[Select | CompoundSelect | None, list[str]]:
    """Evaluate a validated expression in a no-builtins SQLAlchemy namespace."""
    errors = validate_python_expression(source)
    if errors:
        return None, errors
    try:
        tree = ast.parse(source, mode="eval")
        statement = eval(  # noqa: S307 - guarded AST + empty builtins experimental boundary
            compile(tree, "<generated-sqlalchemy>", "eval"),
            {"__builtins__": {}},
            SAFE_NAMESPACE,
        )
    except Exception as exc:  # noqa: BLE001 - persist experimental construction failure
        return None, [f"BUILD_ERROR:{type(exc).__name__}:{exc}"]
    if not isinstance(statement, (Select, CompoundSelect)):
        return None, [f"NOT_READ_ONLY_SELECT:{type(statement).__name__}"]
    return statement, []


def compile_postgresql(statement: Select | CompoundSelect) -> tuple[str | None, list[str]]:
    """Compile through SQLAlchemy itself; no LLM/provider SQL translator."""
    try:
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
    except Exception as exc:  # noqa: BLE001 - persist experimental compile failure
        return None, [f"COMPILE_ERROR:{type(exc).__name__}:{exc}"]
    normalized = sql.lstrip().upper()
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        return None, ["COMPILED_SQL_NOT_READ_ONLY"]
    return sql, []


def assert_phase41_contract() -> None:
    catalog = conceptual_catalog_text()
    assert "class Employee" in catalog
    assert "class Overtime" in catalog
    assert "overtime_record" not in catalog
    assert "attendance_record" not in catalog
    assert "union" in GENERATION_PROMPT.lower()
    assert "assumptions" in GENERATION_PROMPT

    simple = "select(func.sum(Overtime.approved_minutes)).where(Overtime.work_date >= date(2026, 1, 1))"
    statement, errors = build_statement(simple)
    assert errors == []
    assert statement is not None
    sql, compile_errors = compile_postgresql(statement)
    assert compile_errors == []
    assert sql is not None and "overtime_record" in sql

    multi = (
        "union_all("
        "select(literal('jan').label('period'), func.sum(Overtime.approved_minutes)).where(Overtime.work_date >= date(2026, 1, 1), Overtime.work_date < date(2026, 2, 1)),"
        "select(literal('feb').label('period'), func.sum(Overtime.approved_minutes)).where(Overtime.work_date >= date(2026, 2, 1), Overtime.work_date < date(2026, 3, 1))"
        ")"
    )
    multi_statement, multi_errors = build_statement(multi)
    assert multi_errors == []
    assert isinstance(multi_statement, CompoundSelect)

    unsafe_statement, unsafe_errors = build_statement("__import__('os').system('id')")
    assert unsafe_statement is None
    assert unsafe_errors


if __name__ == "__main__":
    assert_phase41_contract()
    print("DIRECT_SQLALCHEMY_PHASE41_SELF_TEST_OK")
