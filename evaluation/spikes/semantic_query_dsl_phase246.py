"""Phase 2.4.6 — composable TemporalExpression experiment.

Focused change vs 2.4.5: relative time uses two composable TemporalPoint
expressions (anchor + offset + unit). No named YTD/LAST_N windows, no textual
relative bounds, and no include-anchor flag. Everything else remains an
inspection-only experiment: no MCP, SQL, or executable Eloquent.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase242 import (
    CAPABILITIES,
    SOURCE_DATE,
    SOURCE_TIMEZONE,
    TYPE_CAPABILITIES,
    GroupBy,
    Measure,
    OrderBy,
    ScalarCondition,
    scoped_catalog,
)
from semantic_query_dsl_phase243 import ScopeSelectionV243
from semantic_query_dsl_phase244 import (
    CalendarPredicateFilter,
    DerivedCalendarFilter,
    capabilities,
    validate_operations,
)

ROOT = Path(__file__).resolve().parents[2]


class TemporalPoint(BaseModel):
    anchor: Literal["SOURCE_DATE", "START_OF_CURRENT_MONTH", "START_OF_CURRENT_YEAR"]
    offset: int = 0
    unit: Literal["DAY", "MONTH", "YEAR"] = "DAY"


class TimeScopeV246(BaseModel):
    field: str
    kind: Literal[
        "EXPLICIT_DATE_RANGE",
        "EXPLICIT_YEAR",
        "EXPLICIT_MONTH",
        "EXPLICIT_MONTH_LIST",
        "RELATIVE_RANGE",
    ]
    start_inclusive: str | None = None
    end_exclusive: str | None = None
    year: int | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    months: list[int] = Field(default_factory=list)
    start: TemporalPoint | None = None
    end: TemporalPoint | None = None


class SemanticQueryIntentV246(BaseModel):
    goal: str
    result_fields: list[str] = Field(default_factory=list)
    measures: list[Measure] = Field(default_factory=list)
    time_scope: TimeScopeV246 | None = None
    derived_calendar_filters: list[DerivedCalendarFilter] = Field(default_factory=list)
    calendar_predicate_filters: list[CalendarPredicateFilter] = Field(default_factory=list)
    scalar_conditions: list[ScalarCondition] = Field(default_factory=list)
    group_by: list[GroupBy] = Field(default_factory=list)
    order_by: list[OrderBy] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    ambiguities: list[str] = Field(default_factory=list)
    unsupported_reasons: list[str] = Field(default_factory=list)


SCOPE_PROMPT_V246 = """Select ONLY capabilities required now by an explicit subject, requested result, grouping,
filter, or ordering. Every capability needs one present use and reason. Never select a capability speculatively,
because it may be useful, because a related entity exists, or because employee attributes might be needed later.
Overtime-only => overtime. Overtime by department => overtime + workforce. Listing employees => workforce.
Period/month/year never imply payroll. Do not decide fields, SQL, joins, entities, or answerability."""


INTENT_PROMPT_V246 = """Translate the question into the MINIMAL provider-neutral Semantic Query Intent using ONLY
scoped conceptual fields.

RESULTS:
- result_fields contains ONLY attributes explicitly named by the user. If no output attributes are named, use [].
- Never copy useful/default/helpful fields into result_fields.
- measures contains analytical quantities only.
- a measure/filter/group/order/time field does not automatically belong in result_fields.

GROUPING:
- group_by only for an explicit requested breakdown.
- 'by month' MUST use YEAR_MONTH so year-month identity is preserved.
- WEEKDAY/DAY_OF_MONTH used as calendar conditions are NOT groupings unless grouping is explicitly requested.

TIME SCOPE:
- exactly one time_scope limits WHEN data is considered.
- January 2026 / 2026-01 / 202601 => EXPLICIT_MONTH(year=2026, month=1).
- During 2026 => EXPLICIT_YEAR(year=2026).
- Literal date interval => EXPLICIT_DATE_RANGE.
- Explicit list of months in one year => EXPLICIT_MONTH_LIST.
- Relative requests MUST use RELATIVE_RANGE with start and end TemporalPoint objects.
- A TemporalPoint is ONLY anchor + offset + unit. Never emit textual relative expressions or absolute dates for a relative request.
- Current month: start START_OF_CURRENT_MONTH +0 MONTH; end START_OF_CURRENT_MONTH +1 MONTH.
- Previous month: start START_OF_CURRENT_MONTH -1 MONTH; end START_OF_CURRENT_MONTH +0 MONTH.
- Last N months including current: start START_OF_CURRENT_MONTH -(N-1) MONTH; end START_OF_CURRENT_MONTH +1 MONTH.
- Year through today: start START_OF_CURRENT_YEAR +0 DAY; end SOURCE_DATE +1 DAY.
- Last N years through today: start SOURCE_DATE -N YEAR; end SOURCE_DATE +1 DAY.
The end TemporalPoint is already the EXCLUSIVE boundary. There is no inclusive-end flag.

CALENDAR FILTERS:
- Every Monday => WEEKDAY EQ MONDAY.
- Day 15 of each month => DAY_OF_MONTH EQ 15.
- First day => DAY_OF_MONTH EQ 1.
- Last day => IS_LAST_DAY_OF_MONTH.
Calendar filters are separate from time_scope and never imply grouping.

AMBIGUITY:
- If materially ambiguous, add ambiguities and do not build executable query content.
- 'previous period' without an established period unit is ambiguous; do not assume month/year/payroll period.
- Clear requests such as previous month/current month/January 2026 are not ambiguous.

Do not emit SQL, Eloquent/PHP, entities, relationships, physical schema, raw expressions, or fields outside scope."""


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def derived_answerability(intent: SemanticQueryIntentV246) -> str:
    if intent.unsupported_reasons:
        return "UNSUPPORTED_QUERY"
    if intent.ambiguities:
        return "NEEDS_CLARIFICATION"
    return "UNDERSTOOD_AND_EXECUTABLE"


def result_mode(intent: SemanticQueryIntentV246) -> str:
    if intent.measures:
        return "AGGREGATED"
    if intent.result_fields:
        return "EXPLICIT_FIELDS"
    return "DEFAULT_FIELDS"


def referenced_fields(intent: SemanticQueryIntentV246) -> list[str]:
    refs = list(intent.result_fields)
    refs.extend(x.field for x in intent.measures)
    refs.extend(x.field for x in intent.scalar_conditions)
    refs.extend(x.field for x in intent.group_by)
    refs.extend(x.field for x in intent.order_by)
    if intent.time_scope:
        refs.append(intent.time_scope.field)
    refs.extend(x.field for x in intent.derived_calendar_filters)
    refs.extend(x.field for x in intent.calendar_predicate_filters)
    return refs


def derived_entities(intent: SemanticQueryIntentV246) -> list[str]:
    return sorted({x.split(".", 1)[0] for x in referenced_fields(intent) if "." in x})


def _add_months(value: date, months: int) -> date:
    idx = value.year * 12 + value.month - 1 + months
    year, month0 = divmod(idx, 12)
    month = month0 + 1
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(value.day, last_day))


def _resolve_point(point: TemporalPoint) -> date:
    if point.anchor == "START_OF_CURRENT_MONTH":
        base = date(SOURCE_DATE.year, SOURCE_DATE.month, 1)
    elif point.anchor == "START_OF_CURRENT_YEAR":
        base = date(SOURCE_DATE.year, 1, 1)
    else:
        base = SOURCE_DATE
    if point.unit == "MONTH":
        return _add_months(base, point.offset)
    if point.unit == "YEAR":
        try:
            return base.replace(year=base.year + point.offset)
        except ValueError:
            return base.replace(year=base.year + point.offset, day=28)
    return base + timedelta(days=point.offset)


def canonicalize_intent(intent: SemanticQueryIntentV246) -> SemanticQueryIntentV246:
    data = intent.model_dump()
    if intent.ambiguities or intent.unsupported_reasons:
        data.update({
            "result_fields": [], "measures": [], "time_scope": None,
            "derived_calendar_filters": [], "calendar_predicate_filters": [],
            "scalar_conditions": [], "group_by": [], "order_by": [], "limit": None,
        })
        return SemanticQueryIntentV246.model_validate(data)
    if intent.time_scope:
        s = intent.time_scope
        common: dict[str, Any] = {"field": s.field, "kind": s.kind}
        if s.kind == "EXPLICIT_DATE_RANGE":
            common.update(start_inclusive=s.start_inclusive, end_exclusive=s.end_exclusive)
        elif s.kind == "EXPLICIT_YEAR":
            common.update(year=s.year)
        elif s.kind == "EXPLICIT_MONTH":
            common.update(year=s.year, month=s.month)
        elif s.kind == "EXPLICIT_MONTH_LIST":
            common.update(year=s.year, months=s.months)
        else:
            common.update(start=s.start.model_dump() if s.start else None, end=s.end.model_dump() if s.end else None)
        data["time_scope"] = common
    data["group_by"] = [
        {**x.model_dump(), "derivation": "YEAR_MONTH" if x.derivation == "MONTH" else x.derivation}
        for x in intent.group_by
    ]
    return SemanticQueryIntentV246.model_validate(data)


def time_scope_shape_errors(scope: TimeScopeV246 | None) -> list[str]:
    if scope is None:
        return []
    values = {
        "start_inclusive": scope.start_inclusive, "end_exclusive": scope.end_exclusive,
        "year": scope.year, "month": scope.month, "months": scope.months,
        "start": scope.start, "end": scope.end,
    }
    present = {k for k, v in values.items() if v not in (None, [], "")}
    allowed = {
        "EXPLICIT_DATE_RANGE": {"start_inclusive", "end_exclusive"},
        "EXPLICIT_YEAR": {"year"},
        "EXPLICIT_MONTH": {"year", "month"},
        "EXPLICIT_MONTH_LIST": {"year", "months"},
        "RELATIVE_RANGE": {"start", "end"},
    }[scope.kind]
    return [f"TIME_SCOPE_EXTRA_FIELD:{scope.kind}:{x}" for x in sorted(present - allowed)] + [
        f"TIME_SCOPE_MISSING_FIELD:{scope.kind}:{x}" for x in sorted(allowed - present)
    ]


def normalize_time_scope(scope: TimeScopeV246 | None) -> dict[str, Any] | None:
    if scope is None:
        return None
    errors = [x for x in time_scope_shape_errors(scope) if "MISSING_FIELD" in x]
    if errors:
        raise ValueError(";".join(errors))
    if scope.kind == "EXPLICIT_YEAR":
        return {"field": scope.field, "start_inclusive": f"{scope.year:04d}-01-01", "end_exclusive": f"{scope.year + 1:04d}-01-01"}
    if scope.kind == "EXPLICIT_MONTH":
        start = date(scope.year, scope.month, 1)
        end = _add_months(start, 1)
        return {"field": scope.field, "start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()}
    if scope.kind == "EXPLICIT_DATE_RANGE":
        return {"field": scope.field, "start_inclusive": scope.start_inclusive, "end_exclusive": scope.end_exclusive}
    if scope.kind == "EXPLICIT_MONTH_LIST":
        return {"field": scope.field, "periods": [{"year": scope.year, "month": m} for m in scope.months]}
    return {"field": scope.field, "start_inclusive": _resolve_point(scope.start).isoformat(), "end_exclusive": _resolve_point(scope.end).isoformat()}


def validate_operations_v246(cats: list[str], intent: SemanticQueryIntentV246) -> list[str]:
    return validate_operations(cats, intent)  # compatible field-oriented contract


def eloquent_like(intent: SemanticQueryIntentV246, normalized: dict[str, Any] | None) -> str:
    entities = derived_entities(intent)
    root = entities[0].title().replace("_", "") if entities else "Query"
    lines = [f"{root}::query()"]
    if result_mode(intent) == "DEFAULT_FIELDS":
        lines.append("    ->selectDefaultFields()")
    elif intent.result_fields:
        lines.append("    ->select(" + repr(intent.result_fields) + ")")
    for m in intent.measures:
        lines.append(f"    ->measure('{m.aggregation}', '{m.field}')")
    if normalized and "start_inclusive" in normalized:
        lines.append(f"    ->whereRange('{normalized['field']}', '{normalized['start_inclusive']}', '{normalized['end_exclusive']}')")
    for x in intent.derived_calendar_filters:
        value = x.value if x.operator == "EQ" else x.values
        lines.append(f"    ->whereDerived('{x.field}', '{x.derivation}', '{x.operator}', {value!r})")
    for x in intent.calendar_predicate_filters:
        lines.append(f"    ->whereCalendar('{x.field}', '{x.predicate}')")
    for g in intent.group_by:
        lines.append(f"    ->groupByDerived('{g.field}', '{g.derivation}')" if g.derivation else f"    ->groupBy('{g.field}')")
    for o in intent.order_by:
        lines.append(f"    ->orderBy('{o.field}', '{o.direction}')")
    if intent.limit:
        lines.append(f"    ->limit({intent.limit})")
    lines.append("    ->get();")
    return "\n".join(lines)


def semantic_differences(case: dict[str, Any], cats: list[str], intent: SemanticQueryIntentV246, normalized: dict[str, Any] | None, normalization_error: str | None) -> list[str]:
    e = case["expected"]
    diff: list[str] = []
    if sorted(cats) != sorted(e.get("capabilities", [])): diff.append("CAPABILITY_SCOPE_MISMATCH")
    if result_mode(intent) != e.get("result_mode", result_mode(intent)): diff.append("RESULT_MODE_MISMATCH")
    if sorted(intent.result_fields) != sorted(e.get("result_fields", [])): diff.append("RESULT_FIELDS_MISMATCH")
    if sorted((x.field, x.aggregation) for x in intent.measures) != sorted((x["field"], x["aggregation"]) for x in e.get("measures", [])): diff.append("MEASURE_MISMATCH")
    if sorted((x.field, x.derivation) for x in intent.group_by) != sorted((x["field"], x.get("derivation")) for x in e.get("group_by", [])): diff.append("GROUP_BY_MISMATCH")
    if sorted((x.field, x.derivation, x.direction) for x in intent.order_by) != sorted((x["field"], x.get("derivation"), x["direction"]) for x in e.get("order_by", [])): diff.append("ORDER_BY_MISMATCH")
    if intent.limit != e.get("limit"): diff.append("LIMIT_MISMATCH")
    if derived_answerability(intent) != e.get("answerability", "UNDERSTOOD_AND_EXECUTABLE"): diff.append("ANSWERABILITY_MISMATCH")
    if e.get("relative_required") and (not intent.time_scope or intent.time_scope.kind != "RELATIVE_RANGE"): diff.append("RELATIVE_INTENT_NOT_SYMBOLIC")
    actual_ranges = [] if normalized is None or "periods" in normalized else [normalized]
    if normalization_error: diff.append("NORMALIZATION_ERROR")
    if sorted((x["field"], x["start_inclusive"], x["end_exclusive"]) for x in actual_ranges) != sorted((x["field"], x["start_inclusive"], x["end_exclusive"]) for x in e.get("normalized_ranges", [])): diff.append("RANGE_MISMATCH")
    actual_derived = sorted((x.field, x.derivation, x.operator, str(x.value), tuple(map(str, x.values))) for x in intent.derived_calendar_filters)
    expected_derived = sorted((x["field"], x["derivation"], x["operator"], str(x.get("value")), tuple(map(str, x.get("values", [])))) for x in e.get("derived_conditions", []))
    if actual_derived != expected_derived: diff.append("DERIVED_CONDITION_MISMATCH")
    actual_calendar = sorted((x.field, x.predicate) for x in intent.calendar_predicate_filters)
    expected_calendar = sorted((x["field"], x["predicate"]) for x in e.get("calendar_conditions", []))
    if actual_calendar != expected_calendar: diff.append("CALENDAR_CONDITION_MISMATCH")
    diff.extend(time_scope_shape_errors(intent.time_scope))
    diff.extend(validate_operations_v246(cats, intent))
    return sorted(set(diff))


def run(cases: list[dict[str, Any]], repetitions: int, output: Path, model_name: str) -> None:
    model = OpenAIStructuredModel(api_key=os.environ.get("OPENAI_API_KEY"), model=model_name, timeout_seconds=60, max_retries=0, max_output_tokens=4096)
    output.mkdir(parents=True, exist_ok=False)
    descriptions = {k: v["description"] for k, v in CAPABILITIES.items()}
    rows: list[dict[str, Any]] = []
    for case in cases:
        for repetition in range(1, repetitions + 1):
            started = time.monotonic()
            row: dict[str, Any] = {"attempt_id": str(uuid.uuid4()), "question_id": case["id"], "question": case["question"], "repetition": repetition}
            try:
                scope = model.parse(purpose=SCOPE_PROMPT_V246, instructions="Capability catalog: " + json.dumps(descriptions, ensure_ascii=False) + "\nQuestion: " + case["question"], output_model=ScopeSelectionV243)
                cats = capabilities(scope)
                catalog = scoped_catalog(cats)
                row.update({"scope": scope.model_dump(mode="json"), "capabilities": cats, "scoped_fields": sorted(catalog["fields"])})
                raw = model.parse(
                    purpose=INTENT_PROMPT_V246,
                    instructions="Provider temporal context: " + json.dumps({"source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE}) + "\nType capabilities: " + json.dumps(TYPE_CAPABILITIES) + "\nScoped conceptual fields: " + json.dumps(catalog["fields"], ensure_ascii=False) + "\nDefault result fields are platform metadata and MUST NOT be copied unless explicitly named: " + json.dumps(catalog["default_result_fields"], ensure_ascii=False) + "\nQuestion: " + case["question"],
                    output_model=SemanticQueryIntentV246,
                )
                intent = canonicalize_intent(raw)
                normalization_error = None
                normalized = None
                try:
                    normalized = normalize_time_scope(intent.time_scope)
                except Exception as exc:
                    normalization_error = f"{type(exc).__name__}: {str(exc)[:240]}"
                differences = semantic_differences(case, cats, intent, normalized, normalization_error)
                row.update({
                    "structured_output_success": True,
                    "raw_intent": raw.model_dump(mode="json"),
                    "canonical_intent": intent.model_dump(mode="json"),
                    "raw_time_scope_errors": time_scope_shape_errors(raw.time_scope),
                    "canonical_time_scope_errors": time_scope_shape_errors(intent.time_scope),
                    "derived_result_mode": result_mode(intent),
                    "derived_answerability": derived_answerability(intent),
                    "derived_entities": derived_entities(intent),
                    "normalized_time_scope": normalized,
                    "normalization_error": normalization_error,
                    "semantic_differences": differences,
                    "semantic_success": not differences,
                    "eloquent_like": eloquent_like(intent, normalized) if normalization_error is None else None,
                })
            except Exception as exc:
                row.update({"structured_output_success": False, "semantic_success": False, "semantic_differences": [model.last_failure_class or "MODEL_OR_TRANSPORT_FAILURE"], "exception_class": type(exc).__name__, "error": str(exc)[:300]})
            row["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("question_id", "semantic_success", "semantic_differences", "latency_ms")}, ensure_ascii=False), flush=True)
    (output / "raw_responses.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    failures = Counter(e for r in rows for e in r.get("semantic_differences", []))
    metrics = {
        "total": len(rows),
        "structured_output_success_rate": sum(bool(r.get("structured_output_success")) for r in rows) / len(rows),
        "semantic_success_count": sum(bool(r.get("semantic_success")) for r in rows),
        "semantic_success_rate": sum(bool(r.get("semantic_success")) for r in rows) / len(rows),
        "failure_distribution": dict(failures),
    }
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"created_at": datetime.utcnow().isoformat() + "Z", "phase": "2.4.6", "primary_gate": "semantic_success", "model": model_name, "source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE, "cases": len(cases), "repetitions": repetitions}, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", type=Path, default=ROOT / "evaluation/spikes/semantic_query_dsl_phase246_cases.jsonl")
    p.add_argument("--repetitions", type=int, default=1)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    a = p.parse_args()
    run(load_cases(a.cases), a.repetitions, a.output, a.model)


if __name__ == "__main__":
    main()
