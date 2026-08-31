"""Phase 2.4.4 — focused Semantic Query Intent spike.

Changes vs 2.4.3:
1) time_scope is separated from calendar_filters;
2) capability scoping forbids speculative/preventive capabilities;
3) ambiguous relative period references must remain ambiguities.

Everything else stays experimental and inspection-only. No MCP/SQL/Eloquent execution.
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
from typing import Literal

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
    RelativeEnd,
    RelativeStart,
    ScalarCondition,
    derived_result_mode,
    scoped_catalog,
)
from semantic_query_dsl_phase243 import CapabilityUse, ScopeSelectionV243

ROOT = Path(__file__).resolve().parents[2]


class TimeScope(BaseModel):
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
    relative_start: RelativeStart | None = None
    relative_end: RelativeEnd | None = None


class DerivedCalendarFilter(BaseModel):
    field: str
    type: Literal["DERIVED_VALUE"] = "DERIVED_VALUE"
    derivation: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY"]
    operator: Literal["EQ", "IN"]
    value: str | int | None = None
    values: list[str | int] = Field(default_factory=list)


class CalendarPredicateFilter(BaseModel):
    field: str
    type: Literal["CALENDAR_PREDICATE"] = "CALENDAR_PREDICATE"
    predicate: Literal["IS_LAST_DAY_OF_MONTH"]


class SemanticQueryIntentV244(BaseModel):
    goal: str
    result_fields: list[str] = Field(default_factory=list)
    measures: list[Measure] = Field(default_factory=list)
    time_scope: TimeScope | None = None
    derived_calendar_filters: list[DerivedCalendarFilter] = Field(default_factory=list)
    calendar_predicate_filters: list[CalendarPredicateFilter] = Field(default_factory=list)
    scalar_conditions: list[ScalarCondition] = Field(default_factory=list)
    group_by: list[GroupBy] = Field(default_factory=list)
    order_by: list[OrderBy] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    ambiguities: list[str] = Field(default_factory=list)
    unsupported_reasons: list[str] = Field(default_factory=list)


SCOPE_PROMPT_V244 = """Select ONLY capabilities that are required now by an explicit subject, requested result,
requested grouping, filter, or ordering in the user's question. Every capability must have one concrete usage and
reason. Never add a capability because it might be useful, might be needed later, is commonly related, or could
provide optional employee attributes. Overtime-only questions require only overtime. Overtime by department requires
overtime + workforce. Listing/latest employees requires workforce. The words period/month/year never imply payroll.
Do not decide fields, joins, answerability, SQL, entities, or provider syntax."""

INTENT_PROMPT_V244 = """Translate the question into a MINIMAL provider-neutral Semantic Query Intent using ONLY
scoped conceptual fields.

RESULTS AND OPERATIONS:
- result_fields contains ONLY attributes explicitly named by the user. Listing records without named attributes => [].
- measures contains analytical quantities only and must respect field operations/default aggregation metadata.
- group_by only for explicit breakdowns such as 'by department' or 'by month'.
- order_by only for explicit sorting semantics.

TIME MODEL — EXACTLY TWO CONCERNS:
1. time_scope: the single interval/set that limits WHEN data is considered.
2. calendar filters: properties dates inside that scope must satisfy.
Never duplicate temporal meaning across these concerns.

TIME_SCOPE:
- January 2026 / 2026-01 / 202601 => EXPLICIT_MONTH(year=2026,month=1).
- During 2026 => EXPLICIT_YEAR(year=2026).
- Explicit literal date interval => EXPLICIT_DATE_RANGE.
- Explicit list of months in one year => EXPLICIT_MONTH_LIST.
- Relative requests MUST use RELATIVE_RANGE and MUST NOT materialize absolute dates.
- Current month: start START_OF_CURRENT_MONTH 0 MONTH; end START_OF_CURRENT_MONTH +1 MONTH.
- Previous month: start START_OF_CURRENT_MONTH -1 MONTH; end START_OF_CURRENT_MONTH 0 MONTH.
- Last N months including current: start START_OF_CURRENT_MONTH -(N-1) MONTH; end START_OF_CURRENT_MONTH +1 MONTH.
- Year through today: start START_OF_CURRENT_YEAR; end SOURCE_DATE with include_anchor_day=true.
- Last N years through today: start SOURCE_DATE -N YEAR; end SOURCE_DATE include_anchor_day=true.

CALENDAR FILTERS:
- Every Monday => derived_calendar_filters WEEKDAY EQ MONDAY.
- Day 15 of each month => DAY_OF_MONTH EQ 15.
- First day of each month => DAY_OF_MONTH EQ 1.
- Last day of each month => calendar_predicate_filters IS_LAST_DAY_OF_MONTH.
Calendar filters never carry year/month/range bounds; the time_scope carries the interval.

AMBIGUITY:
- Do not guess a temporal unit that the user did not specify when multiple interpretations materially differ.
- 'previous period' with no established period type is ambiguous; add an ambiguity explaining that the period unit
  (month/year/etc.) is unspecified and DO NOT create a time_scope for it.
- Clear requests such as previous month/current month/January 2026/every Monday in 2026 are not ambiguous.

Do not emit SQL, Eloquent/PHP, entities, relationships, physical schema, raw expressions, or fields outside scope.
Keep the intent minimal and do not add optional/helpful data not explicitly requested."""


def capabilities(scope: ScopeSelectionV243) -> list[str]:
    return sorted({item.capability for item in scope.selected})


def derived_answerability(intent: SemanticQueryIntentV244) -> str:
    if intent.unsupported_reasons:
        return "UNSUPPORTED_QUERY"
    if intent.ambiguities:
        return "NEEDS_CLARIFICATION"
    return "UNDERSTOOD_AND_EXECUTABLE"


def result_mode(intent: SemanticQueryIntentV244) -> str:
    if intent.measures:
        return "AGGREGATED"
    if intent.result_fields:
        return "EXPLICIT_FIELDS"
    return "DEFAULT_FIELDS"


def referenced_fields(intent: SemanticQueryIntentV244) -> list[str]:
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


def derived_entities(intent: SemanticQueryIntentV244) -> list[str]:
    return sorted({x.split(".", 1)[0] for x in referenced_fields(intent) if "." in x})


def _add_months(value: date, months: int) -> date:
    idx = value.year * 12 + value.month - 1 + months
    year, month0 = divmod(idx, 12)
    month = month0 + 1
    day = min(value.day, (date(year + (month == 12), 1 if month == 12 else month + 1, 1) - date(year, month, 1)).days)
    return date(year, month, day)


def _resolve_start(bound: RelativeStart) -> date:
    if bound.anchor == "START_OF_CURRENT_MONTH":
        base = date(SOURCE_DATE.year, SOURCE_DATE.month, 1)
    elif bound.anchor == "START_OF_CURRENT_YEAR":
        base = date(SOURCE_DATE.year, 1, 1)
    else:
        base = SOURCE_DATE
    if bound.unit == "MONTH":
        return _add_months(base, bound.offset)
    if bound.unit == "YEAR":
        try:
            return base.replace(year=base.year + bound.offset)
        except ValueError:
            return base.replace(year=base.year + bound.offset, day=28)
    return base + timedelta(days=bound.offset)


def _resolve_end(bound: RelativeEnd) -> date:
    if bound.anchor == "START_OF_CURRENT_MONTH":
        base = date(SOURCE_DATE.year, SOURCE_DATE.month, 1)
    elif bound.anchor == "START_OF_CURRENT_YEAR":
        base = date(SOURCE_DATE.year, 1, 1)
    else:
        base = SOURCE_DATE
    if bound.unit == "MONTH":
        value = _add_months(base, bound.offset)
    elif bound.unit == "YEAR":
        try:
            value = base.replace(year=base.year + bound.offset)
        except ValueError:
            value = base.replace(year=base.year + bound.offset, day=28)
    else:
        value = base + timedelta(days=bound.offset)
    return value + timedelta(days=1 if bound.include_anchor_day else 0)


def normalize_time_scope(scope: TimeScope | None) -> dict | None:
    if scope is None:
        return None
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
    return {"field": scope.field, "start_inclusive": _resolve_start(scope.relative_start).isoformat(), "end_exclusive": _resolve_end(scope.relative_end).isoformat()}


def scope_shape_errors(scope: TimeScope | None) -> list[str]:
    if scope is None:
        return []
    values = {
        "start_inclusive": scope.start_inclusive,
        "end_exclusive": scope.end_exclusive,
        "year": scope.year,
        "month": scope.month,
        "months": scope.months,
        "relative_start": scope.relative_start,
        "relative_end": scope.relative_end,
    }
    present = {k for k, v in values.items() if v not in (None, [], "")}
    allowed = {
        "EXPLICIT_DATE_RANGE": {"start_inclusive", "end_exclusive"},
        "EXPLICIT_YEAR": {"year"},
        "EXPLICIT_MONTH": {"year", "month"},
        "EXPLICIT_MONTH_LIST": {"year", "months"},
        "RELATIVE_RANGE": {"relative_start", "relative_end"},
    }[scope.kind]
    required = allowed
    errors = [f"TIME_SCOPE_EXTRA_FIELD:{scope.kind}:{x}" for x in sorted(present - allowed)]
    errors += [f"TIME_SCOPE_MISSING_FIELD:{scope.kind}:{x}" for x in sorted(required - present)]
    return errors


def validate_operations(cats: list[str], intent: SemanticQueryIntentV244) -> list[str]:
    catalog = scoped_catalog(cats)["fields"]
    errors: list[str] = []
    for field in intent.result_fields:
        if field not in catalog or "RESULT" not in catalog[field].get("operations", []): errors.append(f"INVALID_RESULT_FIELD:{field}")
    for x in intent.measures:
        if x.field not in catalog or "MEASURE" not in catalog[x.field].get("operations", []): errors.append(f"INVALID_MEASURE_FIELD:{x.field}")
    for x in intent.group_by:
        if x.field not in catalog or "GROUP" not in catalog[x.field].get("operations", []): errors.append(f"INVALID_GROUP_FIELD:{x.field}")
    for x in intent.order_by:
        if x.field not in catalog or "ORDER" not in catalog[x.field].get("operations", []): errors.append(f"INVALID_ORDER_FIELD:{x.field}")
    if intent.time_scope and (intent.time_scope.field not in catalog or "TEMPORAL" not in catalog[intent.time_scope.field].get("operations", [])):
        errors.append(f"INVALID_TEMPORAL_FIELD:{intent.time_scope.field}")
    for x in [*intent.derived_calendar_filters, *intent.calendar_predicate_filters]:
        if x.field not in catalog or "TEMPORAL" not in catalog[x.field].get("operations", []): errors.append(f"INVALID_CALENDAR_FIELD:{x.field}")
    return errors


def semantic_differences(case, cats, intent: SemanticQueryIntentV244) -> list[str]:
    e = case["expected"]; diff: list[str] = []
    if sorted(cats) != sorted(e.get("capabilities", [])): diff.append("CAPABILITY_SCOPE_MISMATCH")
    if result_mode(intent) != e.get("result_mode", result_mode(intent)): diff.append("RESULT_MODE_MISMATCH")
    if sorted(intent.result_fields) != sorted(e.get("result_fields", [])): diff.append("RESULT_FIELDS_MISMATCH")
    if sorted((x.field,x.aggregation) for x in intent.measures) != sorted((x["field"],x["aggregation"]) for x in e.get("measures", [])): diff.append("MEASURE_MISMATCH")
    if sorted((x.field,x.derivation,x.direction) for x in intent.order_by) != sorted((x["field"],x.get("derivation"),x["direction"]) for x in e.get("order_by", [])): diff.append("ORDER_BY_MISMATCH")
    if intent.limit != e.get("limit"): diff.append("LIMIT_MISMATCH")
    if sorted((x.field,x.derivation) for x in intent.group_by) != sorted((x["field"],x.get("derivation")) for x in e.get("group_by", [])): diff.append("GROUP_BY_MISMATCH")
    if derived_answerability(intent) != e.get("answerability", "UNDERSTOOD_AND_EXECUTABLE"): diff.append("ANSWERABILITY_MISMATCH")
    normalized = normalize_time_scope(intent.time_scope)
    expected_ranges = e.get("normalized_ranges", [])
    actual_ranges = [] if normalized is None or "periods" in normalized else [normalized]
    if sorted((x["field"],x["start_inclusive"],x["end_exclusive"]) for x in actual_ranges) != sorted((x["field"],x["start_inclusive"],x["end_exclusive"]) for x in expected_ranges): diff.append("RANGE_MISMATCH")
    if e.get("relative_required") and (not intent.time_scope or intent.time_scope.kind != "RELATIVE_RANGE"): diff.append("RELATIVE_INTENT_NOT_SYMBOLIC")
    actual_derived = sorted((x.field,x.derivation,x.operator,str(x.value),tuple(map(str,x.values))) for x in intent.derived_calendar_filters)
    expected_derived = sorted((x["field"],x["derivation"],x["operator"],str(x.get("value")),tuple(map(str,x.get("values",[])))) for x in e.get("derived_conditions", []))
    if actual_derived != expected_derived: diff.append("DERIVED_CONDITION_MISMATCH")
    actual_cal = sorted((x.field,x.predicate) for x in intent.calendar_predicate_filters)
    expected_cal = sorted((x["field"],x["predicate"]) for x in e.get("calendar_conditions", []))
    if actual_cal != expected_cal: diff.append("CALENDAR_CONDITION_MISMATCH")
    diff.extend(scope_shape_errors(intent.time_scope))
    diff.extend(validate_operations(cats, intent))
    return sorted(set(diff))


def eloquent_like(intent: SemanticQueryIntentV244) -> str:
    entities = derived_entities(intent); root = entities[0].title().replace("_", "") if entities else "Query"
    lines = [f"{root}::query()"]
    if result_mode(intent) == "DEFAULT_FIELDS": lines.append("    ->selectDefaultFields()")
    elif intent.result_fields: lines.append("    ->select(" + repr(intent.result_fields) + ")")
    for m in intent.measures: lines.append(f"    ->measure('{m.aggregation}', '{m.field}')")
    n = normalize_time_scope(intent.time_scope)
    if n and "start_inclusive" in n: lines.append(f"    ->whereRange('{n['field']}', '{n['start_inclusive']}', '{n['end_exclusive']}')")
    for x in intent.derived_calendar_filters: lines.append(f"    ->whereDerived('{x.field}', '{x.derivation}', '{x.operator}', {repr(x.value if x.operator == 'EQ' else x.values)})")
    for x in intent.calendar_predicate_filters: lines.append(f"    ->whereCalendar('{x.field}', '{x.predicate}')")
    for g in intent.group_by: lines.append(f"    ->groupByDerived('{g.field}', '{g.derivation}')" if g.derivation else f"    ->groupBy('{g.field}')")
    for o in intent.order_by: lines.append(f"    ->orderBy('{o.field}', '{o.direction}')")
    if intent.limit: lines.append(f"    ->limit({intent.limit})")
    lines.append("    ->get();")
    return "\n".join(lines)


def load_cases(path: Path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def run(cases, repetitions: int, output: Path, model_name: str):
    model = OpenAIStructuredModel(api_key=os.environ.get("OPENAI_API_KEY"), model=model_name, timeout_seconds=60, max_retries=0, max_output_tokens=4096)
    output.mkdir(parents=True, exist_ok=False); rows=[]; descriptions={k:v["description"] for k,v in CAPABILITIES.items()}
    for case in cases:
        for repetition in range(1,repetitions+1):
            started=time.monotonic(); row={"attempt_id":str(uuid.uuid4()),"question_id":case["id"],"question":case["question"],"repetition":repetition}
            try:
                scope=model.parse(purpose=SCOPE_PROMPT_V244,instructions="Capability catalog: "+json.dumps(descriptions,ensure_ascii=False)+"\nQuestion: "+case["question"],output_model=ScopeSelectionV243)
                cats=capabilities(scope); catalog=scoped_catalog(cats)
                intent=model.parse(purpose=INTENT_PROMPT_V244,instructions="Provider temporal context: "+json.dumps({"source_current_date":SOURCE_DATE.isoformat(),"source_timezone":SOURCE_TIMEZONE})+"\nType capabilities: "+json.dumps(TYPE_CAPABILITIES)+"\nScoped conceptual fields: "+json.dumps(catalog["fields"],ensure_ascii=False)+"\nDefault result fields are platform metadata; do not copy them unless explicitly named: "+json.dumps(catalog["default_result_fields"],ensure_ascii=False)+"\nQuestion: "+case["question"],output_model=SemanticQueryIntentV244)
                differences=semantic_differences(case,cats,intent)
                row.update({"structured_output_success":True,"scope":scope.model_dump(mode="json"),"capabilities":cats,"scoped_fields":sorted(catalog["fields"]),"raw_intent":intent.model_dump(mode="json"),"derived_result_mode":result_mode(intent),"derived_answerability":derived_answerability(intent),"derived_entities":derived_entities(intent),"normalized_time_scope":normalize_time_scope(intent.time_scope),"eloquent_like":eloquent_like(intent),"semantic_success":not differences,"semantic_differences":differences})
            except Exception as exc:
                row.update({"structured_output_success":False,"semantic_success":False,"semantic_differences":[model.last_failure_class or "MODEL_FAILURE"],"exception_class":type(exc).__name__,"error":str(exc)[:300]})
            row["latency_ms"]=round((time.monotonic()-started)*1000,1); rows.append(row); print(json.dumps({k:row.get(k) for k in ("question_id","semantic_success","semantic_differences","latency_ms")},ensure_ascii=False),flush=True)
    (output/"raw_responses.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in rows)+"\n",encoding="utf-8")
    failures=Counter(e for r in rows for e in r.get("semantic_differences",[])); metrics={"total":len(rows),"structured_output_success_rate":sum(bool(r.get("structured_output_success")) for r in rows)/len(rows),"semantic_success_rate":sum(bool(r.get("semantic_success")) for r in rows)/len(rows),"failure_distribution":dict(failures)}
    (output/"metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); (output/"manifest.json").write_text(json.dumps({"created_at":datetime.utcnow().isoformat()+"Z","phase":"2.4.4","model":model_name,"source_current_date":SOURCE_DATE.isoformat(),"source_timezone":SOURCE_TIMEZONE,"cases":len(cases),"repetitions":repetitions},indent=2)+"\n",encoding="utf-8")


def main():
    p=argparse.ArgumentParser(); p.add_argument("--cases",type=Path,default=ROOT/"evaluation/spikes/semantic_query_dsl_phase244_cases.jsonl"); p.add_argument("--repetitions",type=int,default=1); p.add_argument("--output",type=Path,required=True); p.add_argument("--model",default=os.environ.get("OPENAI_MODEL","gpt-4o-mini")); a=p.parse_args(); run(load_cases(a.cases),a.repetitions,a.output,a.model)

if __name__ == "__main__": main()
