"""Phase 3 spike: Semantic Understanding -> deterministic Query Compiler.

Inspection-only experiment. No MCP, SQL, provider execution, or executable Eloquent.
The first LLM selects capabilities. The second LLM describes what the user means
without emitting Query DSL mechanics. Deterministic code compiles that semantic AST
into the existing provider-neutral Phase 2.4.6 intent for evaluation.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase242 import (
    CAPABILITIES,
    SOURCE_DATE,
    SOURCE_TIMEZONE,
    GroupBy,
    Measure,
    OrderBy,
    scoped_catalog,
)
from semantic_query_dsl_phase243 import ScopeSelectionV243
from semantic_query_dsl_phase244 import CalendarPredicateFilter, DerivedCalendarFilter, capabilities
from semantic_query_dsl_phase246 import (
    SemanticQueryIntentV246,
    TemporalPoint,
    TimeScopeV246,
    canonicalize_intent,
    derived_answerability,
    derived_entities,
    eloquent_like,
    normalize_time_scope,
    result_mode,
    semantic_differences,
)

ROOT = Path(__file__).resolve().parents[2]


class SemanticMeasure(BaseModel):
    field: str
    aggregation: Literal["SUM", "COUNT", "AVG", "MIN", "MAX"]


class TemporalMeaning(BaseModel):
    reference_frame: Literal["EXPLICIT", "CURRENT_MONTH", "CURRENT_YEAR", "CURRENT_DATE"]
    relation: Literal["EXACT", "PREVIOUS", "LAST_N", "FROM_START"]
    unit: Literal["DAY", "MONTH", "YEAR"]
    count: int | None = Field(default=None, ge=1)
    year: int | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    months: list[int] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    through_current_date: bool = False


class BreakdownMeaning(BaseModel):
    kind: Literal["FIELD", "TIME_GRAIN"]
    field: str
    grain: Literal["YEAR_MONTH", "YEAR", "MONTH", "DAY"] | None = None


class CalendarMeaning(BaseModel):
    kind: Literal["WEEKDAY", "DAY_OF_MONTH", "LAST_DAY_OF_MONTH"]
    field: str
    value: str | int | None = None


class SemanticUnderstanding(BaseModel):
    goal: str
    requested_fields: list[str] = Field(default_factory=list)
    measure: SemanticMeasure | None = None
    temporal: TemporalMeaning | None = None
    breakdowns: list[BreakdownMeaning] = Field(default_factory=list)
    calendar_conditions: list[CalendarMeaning] = Field(default_factory=list)
    order_by: list[OrderBy] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    ambiguities: list[str] = Field(default_factory=list)
    unsupported_reasons: list[str] = Field(default_factory=list)


SCOPE_PROMPT = """Select ONLY conceptual capabilities required by what the user explicitly asks to analyze,
return, group, filter, or order. Never select a capability because it might be useful, because entities are related,
or because employee attributes could be needed later. Overtime-only => overtime. Overtime by department =>
overtime + workforce. Employee listing => workforce. Period/month/year never imply payroll."""


UNDERSTANDING_PROMPT = """Describe WHAT the user means. Do NOT build a query DSL and do NOT calculate dates.
Use only fields from the scoped conceptual catalog.

RESULTS
- requested_fields contains only attributes explicitly requested for display.
- If the user asks to list records without naming attributes, requested_fields must be [].
- A metric/filter/group/order field is not automatically a requested output field.
- measure describes an analytical quantity only.

TIME MEANING
Represent temporal meaning semantically, not as date arithmetic:
- January 2026 / 2026-01 / 202601: reference_frame=EXPLICIT, relation=EXACT, unit=MONTH, year=2026, month=1.
- During 2026: EXPLICIT + EXACT + YEAR + year=2026.
- Current month: CURRENT_MONTH + EXACT + MONTH.
- Previous month: CURRENT_MONTH + PREVIOUS + MONTH.
- Last N months including current: CURRENT_MONTH + LAST_N + MONTH + count=N.
- Year through today: CURRENT_YEAR + FROM_START + YEAR + through_current_date=true.
- Last N years through today: CURRENT_DATE + LAST_N + YEAR + count=N + through_current_date=true.
Do not emit anchors, offsets, half-open boundaries, relative_start/end, TimeScope kinds, SQL, or concrete dates for relative requests.

BREAKDOWNS
- Only create a breakdown when the user explicitly asks for one.
- 'by month' => TIME_GRAIN on the relevant date field with grain YEAR_MONTH.
- Department breakdown => FIELD department.name.
- Calendar conditions such as Monday/day 15/last day are filters, not breakdowns.

CALENDAR MEANING
- Every Monday => WEEKDAY value MONDAY.
- Day 15 => DAY_OF_MONTH value 15.
- Last day of month => LAST_DAY_OF_MONTH.

AMBIGUITY
- If a material concept is underspecified, report ambiguity instead of guessing.
- 'previous period' without an established period unit is ambiguous.
- Clear phrases such as previous month/current month/January 2026 are not ambiguous.
When ambiguities or unsupported_reasons are present, do not invent semantic query content beyond the understood subject.
"""


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def compile_temporal(t: TemporalMeaning | None, field: str) -> TimeScopeV246 | None:
    if t is None:
        return None
    if t.reference_frame == "EXPLICIT":
        if t.unit == "MONTH" and t.year and t.month:
            return TimeScopeV246(field=field, kind="EXPLICIT_MONTH", year=t.year, month=t.month)
        if t.unit == "MONTH" and t.year and t.months:
            return TimeScopeV246(field=field, kind="EXPLICIT_MONTH_LIST", year=t.year, months=t.months)
        if t.unit == "YEAR" and t.year:
            return TimeScopeV246(field=field, kind="EXPLICIT_YEAR", year=t.year)
        if t.start_date and t.end_date:
            return TimeScopeV246(
                field=field,
                kind="EXPLICIT_DATE_RANGE",
                start_inclusive=t.start_date,
                end_exclusive=t.end_date,
            )
        return None

    if t.reference_frame == "CURRENT_MONTH":
        if t.relation == "EXACT":
            start = TemporalPoint(anchor="START_OF_CURRENT_MONTH", offset=0, unit="MONTH")
            end = TemporalPoint(anchor="START_OF_CURRENT_MONTH", offset=1, unit="MONTH")
        elif t.relation == "PREVIOUS":
            start = TemporalPoint(anchor="START_OF_CURRENT_MONTH", offset=-1, unit="MONTH")
            end = TemporalPoint(anchor="START_OF_CURRENT_MONTH", offset=0, unit="MONTH")
        elif t.relation == "LAST_N" and t.count:
            start = TemporalPoint(anchor="START_OF_CURRENT_MONTH", offset=-(t.count - 1), unit="MONTH")
            end = TemporalPoint(anchor="START_OF_CURRENT_MONTH", offset=1, unit="MONTH")
        else:
            return None
        return TimeScopeV246(field=field, kind="RELATIVE_RANGE", start=start, end=end)

    if t.reference_frame == "CURRENT_YEAR" and t.relation == "FROM_START" and t.through_current_date:
        return TimeScopeV246(
            field=field,
            kind="RELATIVE_RANGE",
            start=TemporalPoint(anchor="START_OF_CURRENT_YEAR", offset=0, unit="DAY"),
            end=TemporalPoint(anchor="SOURCE_DATE", offset=1, unit="DAY"),
        )

    if t.reference_frame == "CURRENT_DATE" and t.relation == "LAST_N" and t.count:
        return TimeScopeV246(
            field=field,
            kind="RELATIVE_RANGE",
            start=TemporalPoint(anchor="SOURCE_DATE", offset=-t.count, unit=t.unit),
            end=TemporalPoint(anchor="SOURCE_DATE", offset=1, unit="DAY"),
        )
    return None


def compile_understanding(u: SemanticUnderstanding) -> SemanticQueryIntentV246:
    if u.ambiguities or u.unsupported_reasons:
        return SemanticQueryIntentV246(
            goal=u.goal,
            ambiguities=u.ambiguities,
            unsupported_reasons=u.unsupported_reasons,
        )

    temporal_field = "overtime.work_date" if u.measure and u.measure.field.startswith("overtime.") else "employee.hire_date"
    measures = [Measure(field=u.measure.field, aggregation=u.measure.aggregation)] if u.measure else []
    group_by = [
        GroupBy(field=b.field, derivation=b.grain if b.kind == "TIME_GRAIN" else None)
        for b in u.breakdowns
    ]
    derived_filters: list[DerivedCalendarFilter] = []
    predicates: list[CalendarPredicateFilter] = []
    for c in u.calendar_conditions:
        if c.kind == "WEEKDAY":
            derived_filters.append(DerivedCalendarFilter(field=c.field, derivation="WEEKDAY", operator="EQ", value=c.value))
        elif c.kind == "DAY_OF_MONTH":
            derived_filters.append(DerivedCalendarFilter(field=c.field, derivation="DAY_OF_MONTH", operator="EQ", value=c.value))
        else:
            predicates.append(CalendarPredicateFilter(field=c.field, predicate="IS_LAST_DAY_OF_MONTH"))

    intent = SemanticQueryIntentV246(
        goal=u.goal,
        result_fields=u.requested_fields,
        measures=measures,
        time_scope=compile_temporal(u.temporal, temporal_field),
        derived_calendar_filters=derived_filters,
        calendar_predicate_filters=predicates,
        group_by=group_by,
        order_by=u.order_by,
        limit=u.limit,
    )
    return canonicalize_intent(intent)


def understanding_differences(case: dict[str, Any], u: SemanticUnderstanding) -> list[str]:
    e = case["understanding"]
    diff: list[str] = []
    if sorted(u.requested_fields) != sorted(e.get("requested_fields", [])):
        diff.append("UNDERSTANDING_RESULT_FIELDS")
    em = e.get("measure")
    actual_measure = None if u.measure is None else {"field": u.measure.field, "aggregation": u.measure.aggregation}
    if actual_measure != em:
        diff.append("UNDERSTANDING_MEASURE")
    et = e.get("temporal")
    actual_t = None
    if u.temporal:
        actual_t = u.temporal.model_dump(exclude_none=True)
        if not actual_t.get("months"):
            actual_t.pop("months", None)
        if actual_t.get("through_current_date") is False:
            actual_t.pop("through_current_date", None)
    if actual_t != et:
        diff.append("UNDERSTANDING_TEMPORAL")
    actual_breakdowns = [b.model_dump(exclude_none=True) for b in u.breakdowns]
    if actual_breakdowns != e.get("breakdowns", []):
        diff.append("UNDERSTANDING_BREAKDOWN")
    actual_calendar = [c.model_dump(exclude_none=True) for c in u.calendar_conditions]
    if actual_calendar != e.get("calendar_conditions", []):
        diff.append("UNDERSTANDING_CALENDAR")
    expected_ambiguity = bool(e.get("ambiguous", False))
    if bool(u.ambiguities) != expected_ambiguity:
        diff.append("UNDERSTANDING_AMBIGUITY")
    if u.order_by and [x.model_dump(exclude_none=True) for x in u.order_by] != e.get("order_by", []):
        diff.append("UNDERSTANDING_ORDER")
    if u.limit != e.get("limit"):
        diff.append("UNDERSTANDING_LIMIT")
    return diff


def run(case_path: Path, output_dir: Path, model: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = load_cases(case_path)
    llm = OpenAIStructuredModel(api_key=os.environ["OPENAI_API_KEY"], model=model, max_retries=0)
    rows: list[dict[str, Any]] = []

    for case in cases:
        row: dict[str, Any] = {"id": case["id"], "question": case["question"]}
        started = time.perf_counter()
        try:
            scope_instructions = (
                f"{SCOPE_PROMPT}\n\nQuestion:\n{case['question']}\n\n"
                f"Capabilities:\n{json.dumps(CAPABILITIES)}"
            )
            scope = llm.parse(
                purpose="phase3-capability-scope",
                instructions=scope_instructions,
                output_model=ScopeSelectionV243,
            )
            cats = capabilities(scope)
            catalog = scoped_catalog(cats)
            row["scope"] = scope.model_dump()
            row["capabilities"] = cats
            row["scoped_catalog"] = catalog
            understanding_instructions = (
                f"{UNDERSTANDING_PROMPT}\n\nQuestion:\n{case['question']}\n\n"
                f"Source date: {SOURCE_DATE.isoformat()}\nTimezone: {SOURCE_TIMEZONE}\n"
                f"Scoped catalog:\n{json.dumps(catalog)}"
            )
            understanding = llm.parse(
                purpose="phase3-semantic-understanding",
                instructions=understanding_instructions,
                output_model=SemanticUnderstanding,
            )
            row["understanding"] = understanding.model_dump()
            udiff = understanding_differences(case, understanding)
            row["understanding_differences"] = udiff
            row["understanding_success"] = not udiff

            intent = compile_understanding(understanding)
            row["compiled_intent"] = intent.model_dump()
            row["derived_answerability"] = derived_answerability(intent)
            row["derived_result_mode"] = result_mode(intent)
            row["derived_entities"] = derived_entities(intent)
            normalization_error = None
            normalized = None
            try:
                normalized = normalize_time_scope(intent.time_scope)
            except Exception as exc:  # diagnostic artifact, not production path
                normalization_error = f"{type(exc).__name__}: {exc}"
            row["normalized_time_scope"] = normalized
            row["normalization_error"] = normalization_error
            qdiff = semantic_differences(case, cats, intent, normalized, normalization_error)
            row["query_differences"] = qdiff
            row["query_semantic_success"] = not qdiff
            row["eloquent_like"] = None if normalization_error else eloquent_like(intent, normalized)
        except Exception as exc:  # preserve batch diagnostics
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["understanding_success"] = False
            row["query_semantic_success"] = False
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        rows.append(row)

    metrics = {
        "phase": "3-semantic-understanding-query-compiler",
        "cases": len(rows),
        "understanding_success": sum(bool(r.get("understanding_success")) for r in rows),
        "compiled_semantic_success": sum(bool(r.get("query_semantic_success")) for r in rows),
        "understanding_failure_distribution": dict(Counter(d for r in rows for d in r.get("understanding_differences", []))),
        "compiled_failure_distribution": dict(Counter(d for r in rows for d in r.get("query_differences", []))),
    }
    manifest = {
        "phase": "3-semantic-understanding-query-compiler",
        "run_id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "model": model,
        "source_current_date": SOURCE_DATE.isoformat(),
        "source_timezone": SOURCE_TIMEZONE,
        "retries": 0,
        "primary_gates": ["understanding_success", "compiled_semantic_success"],
        "mcp_execution": False,
        "sql_execution": False,
    }
    (output_dir / "raw_responses.jsonl").write_text("\n".join(json.dumps(r, default=str) for r in rows) + "\n", encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=ROOT / "evaluation/spikes/semantic_understanding_phase3_cases.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / f"evaluation/runs/semantic-understanding-phase3-{int(time.time())}")
    parser.add_argument("--model", default="gpt-4o-mini")
    args = parser.parse_args()
    run(args.cases, args.output, args.model)


if __name__ == "__main__":
    main()
