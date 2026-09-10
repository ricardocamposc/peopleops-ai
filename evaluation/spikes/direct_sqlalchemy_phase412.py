"""Phase 4.1.2 — English semantic clarification before SQLAlchemy generation."""
from __future__ import annotations

import direct_sqlalchemy_phase41 as phase41
from pydantic import BaseModel, ConfigDict


class ClarificationResponse(BaseModel):
    """Minimal language and temporal-context handoff."""

    model_config = ConfigDict(extra="forbid")

    needs_clarification: bool
    questions_or_missing_information: list[str]
    original_user_request: str
    clarified_request_english: str
    period_derivation: str | None
    date_derivation: str | None
    where_derivation: str | None
    group_by_derivation: str | None
    query_syntax_derivation: str | None
    data_retrieval_request: str | None
    downstream_analysis: str | None
    additional_context: str | None


CLARIFIER_PROMPT = """
Rewrite the user's request in clear English for a second query-generation
model. This is a language clarification step, not query planning.

Preserve the user's meaning, periods, filters, grouping, ordering, output
requirements, and comparisons. Do not identify a model, choose attributes,
choose a measure, invent filters, add grouping, list columns, or write
SQLAlchemy. Do not resolve an ambiguous term by guessing.

Always populate group_by_derivation. If the user does not explicitly request
grouping, set it to: "The SQLAlchemy 2.x ORM query response does not require
group_by." If grouping is explicitly requested, describe the requested
grouping in this field, including the requested grouping dimension or
dimensions, and state that the SQLAlchemy 2.x ORM query response must include
group_by for those dimensions. Do not invent another grouping. This field
describes the query response that the second model must produce.

Always copy the user's original request exactly into original_user_request.
The second model will receive the original request through this JSON field;
do not rely on a separate unstructured copy of the request.

Explain the meaning of any period expression in period_derivation. A period
is a unit that identifies a month in a particular year. It consists of a year
and a month in YYYY-MM form. A period can be derived from the year and month
of any DATE field, or used to compare dates by deriving their year and month.
January 2026 is represented conceptually as 2026-01. When the request uses
"period" or "previous period" without another domain definition, use this
calendar-period meaning; do not reinterpret it as a payroll period,
accounting period, week, or year. Keep the representation symbolic and do
not calculate or materialize absolute dates in this step.

Whenever the request contains a calendar expression or date-based filter or
grouping (for example January 2026, current month, previous month, last N
months, year to date, a weekday, a day of month, or last day of month), set
date_derivation to a short generic explanation for the query writer: a DATE
field can be derived into year, month, day, weekday, or other calendar parts
with EXTRACT. For example: "The year and month are derived from the DATE
field used for the work date using EXTRACT." Do not identify a model or
attribute and do not calculate or materialize relative dates. If no calendar
expression is present, set date_derivation to null.

Always describe the appropriate filter construction in where_derivation. For
complete months or month ranges, require a full date range using an inclusive
start and an exclusive end boundary for each requested period; for explicit
discrete values or dates, require one iterable argument to in_(). Do not use
`in_()` to enumerate every day of a month when a date range is the correct
shape, and do not collapse multiple requested periods into one continuous
range. For year to date, require a range from January 1 of the current year
through the reference date, using an inclusive start and an exclusive end
boundary that is the day after the reference date. Describe valid
SQLAlchemy/Python expression syntax in
query_syntax_derivation and do not write SQL clauses such as FROM or WHERE.

For every request, separate data retrieval from downstream analysis. Put the
instruction for the query generator to retrieve the required source data in
data_retrieval_request. When the user asks to compare periods, only populate
data_retrieval_request if the request already makes the target entity and
metric recoverable without guessing; otherwise set needs_clarification to true
and leave the downstream fields unresolved. When the request is sufficiently
specific, have data_retrieval_request describe the source data needed for each
requested period and keep the comparison, percentage, trend, or other
interpretation in downstream_analysis. If no downstream analysis is requested,
set downstream_analysis to null.

Set needs_clarification to true only when an essential meaning is genuinely
missing, such as the unit of "previous period" or the target entity/metric for
a requested comparison. Overtime or extra hours is a sufficiently clear
business measure for this rewrite step; do not ask the generator to define it.
Do not ask for optional filters, employees, departments, statuses, or query
shape.

Return only the structured response.
""".strip()


GENERATOR_PROMPT = """
# SQLALCHEMY GENERATOR PROMPT

Generate a read-only SQLAlchemy 2.x ORM query for the user's request using
only the logical ORM models below.

Reference date: 2026-08-30. current month: 8. current day: 30. current period: 2026-08. 
Timezone: UTC. Resolve relative calendar expressions from this reference date.

You will receive a JSON object as the user input. Treat it as the authoritative
request contract.

Input contract:

- `clarified_request_english`: the primary natural-language request to solve.
- `original_user_request`: the original user wording for traceability only.
- `period_derivation`: authoritative period resolution when present.
- `date_derivation`: authoritative date-resolution guidance when present.
- `where_derivation`: authoritative WHERE-clause guidance when present.
- `query_syntax_derivation`: authoritative SQLAlchemy syntax guidance for the generated expression when present; the final output must be a single valid SQLAlchemy expression, not mixed SQL text.
- `group_by_derivation`: authoritative grouping guidance when present.
- `data_retrieval_request`: the data that this query must retrieve.
- `downstream_analysis`: analysis to be performed after retrieval; do not
  calculate it inside the database query unless explicitly required.
- `additional_context`: optional extra context; use only if it helps clarify
  the query without contradicting the other fields.

Priority rules:

1. Use `clarified_request_english` as the main request.
2. Use `period_derivation`, `date_derivation`, `where_derivation`, `query_syntax_derivation`, `group_by_derivation`, and
   `data_retrieval_request` as
   explicit instructions when present.
3. Use `original_user_request` only if it helps disambiguate the clarified
   request.

The SQLAlchemy query retrieves source data only. If `downstream_analysis` is
present, preserve the data needed for that later analysis and do not perform
the comparison, percentage calculation, trend interpretation, or other
downstream reasoning inside the database query unless the request explicitly
requires database-side calculation.

Group-by rule:

- If `group_by_derivation` says the response does not require `group_by`, do
  not add any `group_by()` call.

Return either `QUERY` or `NEEDS_INFO` in the structured response.

For `QUERY`, provide one Python expression that evaluates to a SQLAlchemy
`Select` or `CompoundSelect`.

Return `QUERY` only when you can provide a complete, valid `sqlalchemy`
expression. Do not emit `QUERY` without `sqlalchemy`.
If any essential piece is still missing, return `NEEDS_INFO` instead of
guessing or returning a partial query.

For `NEEDS_INFO`, state only the essential missing information.

The `sqlalchemy` field must be valid Python syntax and must be a single
SQLAlchemy expression, not SQL text. Use SQLAlchemy method calls only.

Hard syntax rules:

- Start from `select(...)` or another SQLAlchemy selectable expression.
- If the expression spans multiple lines, wrap the full expression in outer
  parentheses.
- Keep `select()`, `.where()`, `.group_by()`, and `.order_by()` as chained SQLAlchemy method calls; do not write them as bare SQL fragments such as `group_by func.extract(...)` or `order_by func.extract(...)`.
- Use `extract("month", Model.date_field)` for date-part extraction; do not use `func.extract(...)`.
  `func.sum(...)`, `func.count(...)`, `case(...)`, `and_(...)`, `or_(...)`,
  `union(...)`, and `union_all(...)`.
- When using `in_()`, pass exactly one iterable argument, for example
  `column.in_([value1, value2])`; never pass multiple comma-separated values
  directly to `in_()`.
- Use Python `date(YYYY, M, D)` literals for date boundaries when needed.
- Use SQLAlchemy aggregation functions such as `func.sum(...)` and
  `func.count(...)`; do not use Python built-in aggregates like `sum()` or
  `count()` to build the query expression.
- When labeling an aggregate, apply `label(...)` to the aggregate expression
  inside `select(...)`, for example `select(func.sum(...).label("total"))`,
  not `select(func.sum(...)).label("total")`.
- Never emit `select(sum(...))`, `select(sum(...)).label(...)`, or any
  `year to date` / `current date` range that is shifted to `yesterday` or to
  the first day of the current month; use the reference date itself as the
  exclusive end boundary anchor.
- Do not write SQL fragments such as `extract('day' from ...)`, `FROM`,
  `WHERE`, `GROUP BY`, `ORDER BY`, `JOIN`, `INTERVAL`, or quoted SQL clauses
  inside `sqlalchemy`.
- Do not end the expression with an incomplete root call followed by indented
  chained methods after the root expression has closed.

Query generation rules:

- Preserve the user's requested fields, filters, grouping, ordering, measures,
  and periods. Do not infer a target entity or metric from a generic retrieval
  request if the contract does not name them explicitly or through a clear
  semantic derivation.
- When the contract uses year to date, resolve it from January 1 of the current
  year through the reference date itself and use an exclusive upper bound on
  the day after the reference date. Do not replace the end boundary with the
  first day of the current month, "yesterday", or any other month-based cutoff.
- Obey `where_derivation` literally when it is present, especially for
  `WHERE`-clause shape and membership filters such as `in_()`.
- Obey `query_syntax_derivation` literally when it is present; it governs the
  SQLAlchemy/Python syntax used to express the generated query.
  When building a full name or similar text projection, use a SQLAlchemy-safe
  string concatenation expression rather than raw SQL text.
- Preserve the requested granularity implied by the input contract. Do not
  invent aggregation when the request is row-level, and do not invent row-level
  output when the request explicitly asks for a summary.
- When `downstream_analysis` is present, return only the base data needed for
  that later analysis, grouped or filtered exactly as requested, and do not
  add extra comparison dimensions or perform the comparison inside the query.
- When comparison is requested after retrieval, do not introduce extra entity
  dimensions that were not explicitly requested; keep the query at the minimal
  comparable granularity required by the input contract.
- Use normal SQLAlchemy 2.x composition, including joins, aggregates, date
  expressions, subqueries, CTEs, `UNION`, and `UNION ALL` when useful.
- Use the most appropriate available model attribute for the requested
  metric or dimension.
- If the contract does not make the target entity and metric recoverable
  without guessing, or if `data_retrieval_request` is generic enough that it
  would require inventing base fields or a source entity, return `NEEDS_INFO`
  instead of inventing them.
- Ask for `NEEDS_INFO` only when essential meaning is genuinely missing; do
  not ask for optional fields, grouping, or filters.
- Explain the result in `interpretation` and disclose any chosen assumption in
  `assumptions`.

Output safety rules:

- Do not emit SQL text, physical table or column names, imports, writes, DDL,
  locking queries, or arbitrary Python side effects.
- Prefer a small, direct, syntactically conservative expression over a clever
  one if both satisfy the request.
- If a requested aggregation or grouping is ambiguous, choose the simplest
  read-only SQLAlchemy expression that matches the clarified meaning.

Logical ORM models:
class Employee
attributes:
  - id: INTEGER
  - employee_code: VARCHAR(32)
  - first_name: VARCHAR(80)
  - last_name: VARCHAR(80)
  - status: VARCHAR(32)
  - hire_date: DATE
  - department_id: INTEGER
relationships:
  - department: many-to-one -> Department; relationship key: Employee.department_id -> Department.id
  - overtime: one-to-many -> Overtime; relationship key: Employee.id <- Overtime.employee_id
  - attendance: one-to-many -> Attendance; relationship key: Employee.id <- Attendance.employee_id

class Department
attributes:
  - id: INTEGER
  - code: VARCHAR(32)
  - name: VARCHAR(120)
  - cost_center: VARCHAR(32)
relationships:
  - employees: one-to-many -> Employee; relationship key: Department.id <- Employee.department_id

class Overtime
attributes:
  - id: INTEGER
  - employee_id: INTEGER
  - work_date: DATE
  - approved_minutes: INTEGER
    description: total approved minutes of overtime; convert to hours by dividing by 60.0 when the request asks for hours so decimals are preserved: hours = approved_minutes / 60.0
  - status: VARCHAR(32)
relationships:
  - employee: many-to-one -> Employee; relationship key: Overtime.employee_id -> Employee.id

class Attendance
attributes:
  - id: INTEGER
  - employee_id: INTEGER
  - work_date: DATE
  - status: VARCHAR(32)
  - scheduled_minutes: INTEGER
  - worked_minutes: INTEGER
  - late_minutes: INTEGER
  - absence_minutes: INTEGER
relationships:
  - employee: many-to-one -> Employee; relationship key: Attendance.employee_id -> Employee.id

""".strip()


def generator_prompt(*, question: str, clarification: ClarificationResponse) -> str:
    """Return the generator instructions owned by the application."""
    if clarification.original_user_request != question:
        raise ValueError("clarification original request does not match question")
    return GENERATOR_PROMPT


def generator_input(clarification: ClarificationResponse) -> dict[str, object]:
    """Select semantic handoff fields; exclude clarifier control metadata."""
    fields = clarification.model_dump(mode="json")
    return {
        key: fields[key]
        for key in (
            "original_user_request",
            "clarified_request_english",
            "period_derivation",
            "date_derivation",
            "where_derivation",
            "query_syntax_derivation",
            "group_by_derivation",
            "data_retrieval_request",
            "downstream_analysis",
            "additional_context",
        )
    }


def assert_phase412_contract() -> None:
    phase41.assert_phase41_contract()
    assert "Rewrite the user's request in clear English" in CLARIFIER_PROMPT
    assert "EXTRACT" in CLARIFIER_PROMPT
    clarification = ClarificationResponse(
        needs_clarification=False,
        questions_or_missing_information=[],
        original_user_request="test",
        clarified_request_english="Compare January overtime by year.",
        period_derivation=(
            "The period is a calendar month derived from the DATE field using "
            "its year and month."
        ),
        date_derivation=(
            "The year and month are derived from the DATE field used for the "
            "work date using EXTRACT."
        ),
        where_derivation=None,
        group_by_derivation=(
            "The SQLAlchemy 2.x ORM query response does not require group_by."
        ),
        query_syntax_derivation=None,
        data_retrieval_request=None,
        downstream_analysis=None,
        additional_context="The request compares January across multiple years.",
    )
    assert "Reference date: 2026-08-30" in generator_prompt(
        question="test", clarification=clarification
    )
    handoff = generator_input(clarification)
    assert "needs_clarification" not in handoff
    assert "questions_or_missing_information" not in handoff


if __name__ == "__main__":
    assert_phase412_contract()
    print("DIRECT_SQLALCHEMY_PHASE412_SELF_TEST_OK")
