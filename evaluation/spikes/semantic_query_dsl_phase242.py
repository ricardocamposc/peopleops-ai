"""Phase 2.4.2 — constrained Semantic Query Intent spike.

Changes vs 2.4.1:
- capability selection no longer decides answerability;
- answerability is derived after semantic interpretation from ambiguity/unsupported evidence;
- field metadata explicitly declares allowed query operations;
- measures/groupings/orderings are validated against those operation capabilities;
- temporal semantics are emitted through ONE temporal_conditions list;
- deterministic normalization is the only component that materializes relative dates;
- entities and result mode remain deterministic;
- Eloquent-like output remains inspection-only and provider-neutral.

No MCP, SQL, Eloquent execution, physical schema, or production contract is used.
"""

from __future__ import annotations

import argparse
import hashlib
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

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATE = date(2026, 8, 30)
SOURCE_TIMEZONE = "UTC"

CAPABILITIES: dict[str, dict[str, Any]] = {
    "overtime": {
        "description": "Recorded and approved employee overtime.",
        "default_result_fields": ["overtime.work_date", "overtime.approved_minutes"],
        "fields": {
            "overtime.work_date": {
                "data_type": "DATE",
                "semantic_type": "calendar_date",
                "description": "Business date on which overtime was worked.",
                "operations": ["RESULT", "FILTER", "GROUP", "ORDER", "TEMPORAL"],
            },
            "overtime.approved_minutes": {
                "data_type": "INTEGER",
                "semantic_type": "duration_minutes",
                "query_role": "measure",
                "default_aggregation": "SUM",
                "description": "Approved overtime duration in minutes.",
                "operations": ["RESULT", "MEASURE", "FILTER", "ORDER"],
            },
        },
    },
    "workforce": {
        "description": "Employee and organization attributes for listing and analytical breakdowns.",
        "default_result_fields": [
            "employee.employee_code",
            "employee.full_name",
            "employee.hire_date",
            "department.name",
        ],
        "fields": {
            "employee.employee_code": {
                "data_type": "STRING",
                "semantic_type": "identifier",
                "operations": ["RESULT", "FILTER", "GROUP", "ORDER"],
            },
            "employee.full_name": {
                "data_type": "STRING",
                "semantic_type": "label",
                "operations": ["RESULT", "FILTER", "GROUP", "ORDER"],
            },
            "employee.hire_date": {
                "data_type": "DATE",
                "semantic_type": "calendar_date",
                "description": "Date on which the employee joined the company.",
                "operations": ["RESULT", "FILTER", "GROUP", "ORDER", "TEMPORAL"],
            },
            "department.name": {
                "data_type": "STRING",
                "semantic_type": "label",
                "operations": ["RESULT", "FILTER", "GROUP", "ORDER"],
            },
        },
    },
    "payroll": {
        "description": "Restricted payroll analytical data.",
        "default_result_fields": ["payroll.net_amount", "payroll_period.code"],
        "fields": {
            "payroll.net_amount": {
                "data_type": "DECIMAL",
                "semantic_type": "currency",
                "query_role": "measure",
                "default_aggregation": "SUM",
                "operations": ["RESULT", "MEASURE", "FILTER", "ORDER"],
            },
            "payroll_period.code": {
                "data_type": "STRING",
                "semantic_type": "period_identifier",
                "description": "Payroll business period identifier; not a calendar DATE.",
                "operations": ["RESULT", "FILTER", "GROUP", "ORDER"],
            },
        },
    },
}

TYPE_CAPABILITIES = {
    "DATE": {
        "derivations": ["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY"],
        "calendar_predicates": ["IS_LAST_DAY_OF_MONTH"],
    }
}

WEEKDAYS = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"}


class ScopeSelection(BaseModel):
    capabilities: list[Literal["overtime", "workforce", "payroll"]] = Field(default_factory=list)


class Measure(BaseModel):
    field: str
    aggregation: Literal["SUM", "COUNT", "AVG", "MIN", "MAX"]


class GroupBy(BaseModel):
    field: str
    derivation: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY"] | None = None


class OrderBy(BaseModel):
    field: str
    derivation: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY"] | None = None
    direction: Literal["ASC", "DESC"] = "ASC"


class RelativeStart(BaseModel):
    anchor: Literal["SOURCE_DATE", "START_OF_CURRENT_MONTH", "START_OF_CURRENT_YEAR"]
    offset: int = 0
    unit: Literal["DAY", "MONTH", "YEAR"] = "DAY"


class RelativeEnd(BaseModel):
    anchor: Literal["SOURCE_DATE", "START_OF_CURRENT_MONTH", "START_OF_CURRENT_YEAR"]
    offset: int = 0
    unit: Literal["DAY", "MONTH", "YEAR"] = "DAY"
    include_anchor_day: bool = False


class TemporalCondition(BaseModel):
    field: str
    kind: Literal[
        "EXPLICIT_DATE_RANGE",
        "EXPLICIT_YEAR",
        "EXPLICIT_MONTH",
        "EXPLICIT_MONTH_LIST",
        "RELATIVE_RANGE",
        "DERIVED_VALUE",
        "CALENDAR_PREDICATE",
    ]
    start_inclusive: str | None = None
    end_exclusive: str | None = None
    year: int | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    months: list[int] = Field(default_factory=list)
    relative_start: RelativeStart | None = None
    relative_end: RelativeEnd | None = None
    derivation: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY"] | None = None
    operator: Literal["EQ", "IN"] | None = None
    value: str | int | None = None
    values: list[str | int] = Field(default_factory=list)
    predicate: Literal["IS_LAST_DAY_OF_MONTH"] | None = None


class ScalarCondition(BaseModel):
    field: str
    operator: Literal["EQ", "GT", "GTE", "LT", "LTE"]
    value: str | int | float


class SemanticQueryIntentV242(BaseModel):
    goal: str
    result_fields: list[str] = Field(default_factory=list)
    measures: list[Measure] = Field(default_factory=list)
    temporal_conditions: list[TemporalCondition] = Field(default_factory=list)
    scalar_conditions: list[ScalarCondition] = Field(default_factory=list)
    group_by: list[GroupBy] = Field(default_factory=list)
    order_by: list[OrderBy] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    ambiguities: list[str] = Field(default_factory=list)
    unsupported_reasons: list[str] = Field(default_factory=list)


SCOPE_PROMPT = """Select the minimum conceptual capabilities needed to interpret the user's request.
Select dimensions/output capabilities too: for example, overtime by department requires overtime + workforce.
Payroll is distinct and restricted; never select it merely because the user says period/month/year.
Do not decide answerability here. Do not select fields, entities, relationships, SQL, joins, or provider syntax.
"""

INTENT_PROMPT = """Translate the question into a minimal provider-neutral Semantic Query Intent using ONLY
scoped conceptual fields. Do not emit entities, relationships, joins, SQL, PHP, Eloquent text, raw expressions,
DBMS functions, or fields outside scope.

FIELD OPERATIONS:
- Respect each field's operations metadata. A field without MEASURE must NEVER appear in measures.
- result_fields contains only attributes explicitly requested by the user. If records are requested without
  named fields, leave result_fields empty; the platform will use safe default fields.
- measures contains analytical quantities. Prefer default_aggregation metadata when the request asks for the
  amount/total of a measure and does not specify another aggregation.
- group_by contains only breakdowns explicitly requested ('by department', 'by month').
- order_by is sorting only. Sorting by employee.hire_date DESC does not require a date derivation unless the
  user explicitly asks to order by a derived calendar component.

TEMPORAL SEMANTICS:
- Express ALL temporal meaning through temporal_conditions only. Never duplicate the same temporal meaning.
- Explicit literal date range -> kind EXPLICIT_DATE_RANGE.
- Explicit year -> EXPLICIT_YEAR.
- Explicit month/year (January 2026, 2026-01, 202601) -> EXPLICIT_MONTH.
- Explicit list of months in one year -> EXPLICIT_MONTH_LIST.
- Relative periods MUST be RELATIVE_RANGE. Never materialize absolute dates for a relative request.
- Current month: start START_OF_CURRENT_MONTH offset 0 MONTH; end START_OF_CURRENT_MONTH offset +1 MONTH.
- Previous month: start START_OF_CURRENT_MONTH offset -1 MONTH; end START_OF_CURRENT_MONTH offset 0 MONTH.
- Year through today: start START_OF_CURRENT_YEAR; end SOURCE_DATE include_anchor_day=true.
- Last two years through today: start SOURCE_DATE offset -2 YEAR; end SOURCE_DATE include_anchor_day=true.
- Last N months ending with current month: start START_OF_CURRENT_MONTH offset -(N-1) MONTH; end
  START_OF_CURRENT_MONTH offset +1 MONTH.
- Every Monday -> DERIVED_VALUE with derivation WEEKDAY, operator EQ, value MONDAY. Never numeric weekday.
- Day 15 of each month -> DERIVED_VALUE DAY_OF_MONTH = 15.
- First day of each month -> DERIVED_VALUE DAY_OF_MONTH = 1.
- Last day of each month -> CALENDAR_PREDICATE IS_LAST_DAY_OF_MONTH.
- A condition such as 'each Monday during 2026' needs two temporal_conditions: EXPLICIT_YEAR 2026 plus
  DERIVED_VALUE WEEKDAY=MONDAY. These are complementary, not duplicate representations.

ANSWERABILITY EVIDENCE:
- Do not output a final answerability status.
- ambiguities: include only unresolved ambiguity that materially changes the query. Example: 'previous period'
  when no prior period type is known.
- unsupported_reasons: include only a requested concept/operation that cannot be expressed with the scoped
  catalog/type capabilities.
- Clear requests such as January 2026, current month, every Monday in 2026, day 15 in 2026, or latest five
  employees are not ambiguous.

Keep the intent minimal. Never enumerate individual dates when a general temporal condition expresses the request.
"""


def scoped_catalog(capabilities: list[str]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    defaults: dict[str, list[str]] = {}
    for capability in capabilities:
        item = CAPABILITIES.get(capability, {})
        fields.update(item.get("fields", {}))
        defaults[capability] = item.get("default_result_fields", [])
    return {
        "source_current_date": SOURCE_DATE.isoformat(),
        "source_timezone": SOURCE_TIMEZONE,
        "type_capabilities": TYPE_CAPABILITIES,
        "fields": fields,
        "default_result_fields": defaults,
    }


def all_refs(intent: SemanticQueryIntentV242) -> list[str]:
    result = list(intent.result_fields)
    for collection in (intent.measures, intent.temporal_conditions, intent.scalar_conditions, intent.group_by, intent.order_by):
        result.extend(item.field for item in collection)
    return result


def derived_entities(intent: SemanticQueryIntentV242) -> list[str]:
    return sorted({ref.split(".", 1)[0] for ref in all_refs(intent) if "." in ref})


def derived_result_mode(intent: SemanticQueryIntentV242) -> str:
    if intent.measures:
        return "AGGREGATED"
    if intent.result_fields:
        return "EXPLICIT_FIELDS"
    return "DEFAULT_FIELDS"


def derived_answerability(intent: SemanticQueryIntentV242) -> str:
    if intent.unsupported_reasons:
        return "UNSUPPORTED_QUERY"
    if intent.ambiguities:
        return "NEEDS_CLARIFICATION"
    return "UNDERSTOOD_AND_EXECUTABLE"


def days_in_month(year: int, month: int) -> int:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def add_months(value: date, amount: int) -> date:
    index = value.year * 12 + value.month - 1 + amount
    year, month_zero = divmod(index, 12)
    month = month_zero + 1
    return date(year, month, min(value.day, days_in_month(year, month)))


def add_years(value: date, amount: int) -> date:
    year = value.year + amount
    return date(year, value.month, min(value.day, days_in_month(year, value.month)))


def resolve_anchor(anchor: str, offset: int, unit: str) -> date:
    if anchor == "SOURCE_DATE":
        base = SOURCE_DATE
    elif anchor == "START_OF_CURRENT_MONTH":
        base = date(SOURCE_DATE.year, SOURCE_DATE.month, 1)
    else:
        base = date(SOURCE_DATE.year, 1, 1)
    if unit == "DAY":
        return base + timedelta(days=offset)
    if unit == "MONTH":
        return add_months(base, offset)
    return add_years(base, offset)


def normalize_temporal(intent: SemanticQueryIntentV242) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in intent.temporal_conditions:
        if item.kind == "EXPLICIT_DATE_RANGE":
            normalized.append({"kind": "RANGE", "field": item.field, "start_inclusive": item.start_inclusive, "end_exclusive": item.end_exclusive})
        elif item.kind == "EXPLICIT_YEAR" and item.year is not None:
            normalized.append({"kind": "RANGE", "field": item.field, "start_inclusive": f"{item.year:04d}-01-01", "end_exclusive": f"{item.year + 1:04d}-01-01"})
        elif item.kind == "EXPLICIT_MONTH" and item.year is not None and item.month is not None:
            start = date(item.year, item.month, 1)
            normalized.append({"kind": "RANGE", "field": item.field, "start_inclusive": start.isoformat(), "end_exclusive": add_months(start, 1).isoformat()})
        elif item.kind == "EXPLICIT_MONTH_LIST" and item.year is not None:
            for month in item.months:
                if 1 <= month <= 12:
                    start = date(item.year, month, 1)
                    normalized.append({"kind": "RANGE", "field": item.field, "start_inclusive": start.isoformat(), "end_exclusive": add_months(start, 1).isoformat()})
        elif item.kind == "RELATIVE_RANGE" and item.relative_start and item.relative_end:
            start = resolve_anchor(item.relative_start.anchor, item.relative_start.offset, item.relative_start.unit)
            end = resolve_anchor(item.relative_end.anchor, item.relative_end.offset, item.relative_end.unit)
            if item.relative_end.include_anchor_day:
                end += timedelta(days=1)
            normalized.append({"kind": "RANGE", "field": item.field, "start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()})
        elif item.kind == "DERIVED_VALUE":
            normalized.append({"kind": "DERIVED_VALUE", "field": item.field, "derivation": item.derivation, "operator": item.operator, "value": item.value, "values": item.values})
        elif item.kind == "CALENDAR_PREDICATE":
            normalized.append({"kind": "CALENDAR_PREDICATE", "field": item.field, "predicate": item.predicate})
    return normalized


def validate_field_operations(scope: ScopeSelection, intent: SemanticQueryIntentV242) -> list[str]:
    fields = scoped_catalog(scope.capabilities)["fields"]
    errors: list[str] = []
    for ref in all_refs(intent):
        if ref not in fields:
            errors.append(f"FIELD_OUTSIDE_SCOPE:{ref}")
    for measure in intent.measures:
        if "MEASURE" not in fields.get(measure.field, {}).get("operations", []):
            errors.append(f"INVALID_MEASURE_FIELD:{measure.field}")
    for item in intent.group_by:
        if "GROUP" not in fields.get(item.field, {}).get("operations", []):
            errors.append(f"INVALID_GROUP_FIELD:{item.field}")
    for item in intent.order_by:
        if "ORDER" not in fields.get(item.field, {}).get("operations", []):
            errors.append(f"INVALID_ORDER_FIELD:{item.field}")
    for item in intent.temporal_conditions:
        if "TEMPORAL" not in fields.get(item.field, {}).get("operations", []):
            errors.append(f"INVALID_TEMPORAL_FIELD:{item.field}")
        if item.kind == "DERIVED_VALUE" and item.derivation == "WEEKDAY":
            supplied = [item.value] if item.operator == "EQ" else item.values
            if any(value not in WEEKDAYS for value in supplied):
                errors.append("NON_SEMANTIC_WEEKDAY_VALUE")
    return errors


def temporal_shape_errors(intent: SemanticQueryIntentV242) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for item in intent.temporal_conditions:
        key = json.dumps(item.model_dump(mode="json"), sort_keys=True)
        if key in seen:
            errors.append("DUPLICATE_TEMPORAL_CONDITION")
        seen.add(key)
        if item.kind == "EXPLICIT_DATE_RANGE" and not (item.start_inclusive and item.end_exclusive):
            errors.append("INVALID_EXPLICIT_RANGE")
        elif item.kind == "EXPLICIT_YEAR" and item.year is None:
            errors.append("INVALID_EXPLICIT_YEAR")
        elif item.kind == "EXPLICIT_MONTH" and (item.year is None or item.month is None):
            errors.append("INVALID_EXPLICIT_MONTH")
        elif item.kind == "EXPLICIT_MONTH_LIST" and (item.year is None or not item.months):
            errors.append("INVALID_EXPLICIT_MONTH_LIST")
        elif item.kind == "RELATIVE_RANGE" and not (item.relative_start and item.relative_end):
            errors.append("INVALID_RELATIVE_RANGE")
        elif item.kind == "DERIVED_VALUE" and not (item.derivation and item.operator):
            errors.append("INVALID_DERIVED_VALUE")
        elif item.kind == "CALENDAR_PREDICATE" and not item.predicate:
            errors.append("INVALID_CALENDAR_PREDICATE")
    return errors


def eloquent_like(intent: SemanticQueryIntentV242) -> str:
    entities = derived_entities(intent)
    model = "QueryModel" if not entities else "".join(part.title() for part in entities[0].split("_"))
    lines = [f"{model}::query()"]
    mode = derived_result_mode(intent)
    if mode == "DEFAULT_FIELDS":
        lines.append("    ->selectDefaultFields()")
    elif mode == "EXPLICIT_FIELDS":
        lines.append("    ->select([" + ", ".join(repr(x) for x in intent.result_fields) + "])")
    for measure in intent.measures:
        lines.append(f"    ->measure('{measure.aggregation}', '{measure.field}')")
    for item in normalize_temporal(intent):
        if item["kind"] == "RANGE":
            lines.append(f"    ->whereRange('{item['field']}', '{item['start_inclusive']}', '{item['end_exclusive']}')")
        elif item["kind"] == "DERIVED_VALUE":
            value = item["value"] if item["operator"] == "EQ" else item["values"]
            lines.append(f"    ->whereDerived('{item['field']}', '{item['derivation']}', '{item['operator']}', {value!r})")
        else:
            lines.append(f"    ->whereCalendar('{item['field']}', '{item['predicate']}')")
    for item in intent.group_by:
        if item.derivation:
            lines.append(f"    ->groupByDerived('{item.field}', '{item.derivation}')")
        else:
            lines.append(f"    ->groupBy('{item.field}')")
    for item in intent.order_by:
        if item.derivation:
            lines.append(f"    ->orderByDerived('{item.field}', '{item.derivation}', '{item.direction}')")
        else:
            lines.append(f"    ->orderBy('{item.field}', '{item.direction}')")
    if intent.limit:
        lines.append(f"    ->limit({intent.limit})")
    lines.append("    ->get();")
    return "\n".join(lines)


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def semantic_differences(case: dict[str, Any], scope: ScopeSelection, intent: SemanticQueryIntentV242) -> list[str]:
    expected = case["expected"]
    diffs: list[str] = []
    if sorted(scope.capabilities) != sorted(expected.get("capabilities", [])):
        diffs.append("CAPABILITY_SCOPE_MISMATCH")
    if derived_answerability(intent) != expected.get("answerability", "UNDERSTOOD_AND_EXECUTABLE"):
        diffs.append("ANSWERABILITY_MISMATCH")
    if derived_result_mode(intent) != expected.get("result_mode", derived_result_mode(intent)):
        diffs.append("RESULT_MODE_MISMATCH")
    if sorted(intent.result_fields) != sorted(expected.get("result_fields", [])):
        diffs.append("RESULT_FIELDS_MISMATCH")
    actual_measures = sorted((x.field, x.aggregation) for x in intent.measures)
    expected_measures = sorted((x["field"], x["aggregation"]) for x in expected.get("measures", []))
    if actual_measures != expected_measures:
        diffs.append("MEASURE_MISMATCH")
    actual_group = sorted((x.field, x.derivation) for x in intent.group_by)
    expected_group = sorted((x["field"], x.get("derivation")) for x in expected.get("group_by", []))
    if actual_group != expected_group:
        diffs.append("GROUP_BY_MISMATCH")
    actual_order = sorted((x.field, x.derivation, x.direction) for x in intent.order_by)
    expected_order = sorted((x["field"], x.get("derivation"), x["direction"]) for x in expected.get("order_by", []))
    if actual_order != expected_order:
        diffs.append("ORDER_BY_MISMATCH")
    if intent.limit != expected.get("limit"):
        diffs.append("LIMIT_MISMATCH")
    actual_norm = normalize_temporal(intent)
    actual_ranges = sorted((x["field"], x["start_inclusive"], x["end_exclusive"]) for x in actual_norm if x["kind"] == "RANGE")
    expected_ranges = sorted((x["field"], x["start_inclusive"], x["end_exclusive"]) for x in expected.get("normalized_ranges", []))
    if actual_ranges != expected_ranges:
        diffs.append("RANGE_MISMATCH")
    actual_derived = sorted((x["field"], x.get("derivation"), x.get("operator"), str(x.get("value"))) for x in actual_norm if x["kind"] == "DERIVED_VALUE")
    expected_derived = sorted((x["field"], x["derivation"], x["operator"], str(x.get("value"))) for x in expected.get("derived_conditions", []))
    if actual_derived != expected_derived:
        diffs.append("DERIVED_CONDITION_MISMATCH")
    actual_calendar = sorted((x["field"], x.get("predicate")) for x in actual_norm if x["kind"] == "CALENDAR_PREDICATE")
    expected_calendar = sorted((x["field"], x["predicate"]) for x in expected.get("calendar_conditions", []))
    if actual_calendar != expected_calendar:
        diffs.append("CALENDAR_CONDITION_MISMATCH")
    if expected.get("relative_required") and not any(x.kind == "RELATIVE_RANGE" for x in intent.temporal_conditions):
        diffs.append("RELATIVE_INTENT_NOT_SYMBOLIC")
    diffs.extend(validate_field_operations(scope, intent))
    diffs.extend(temporal_shape_errors(intent))
    return list(dict.fromkeys(diffs))


def fingerprint(intent: SemanticQueryIntentV242) -> str:
    payload = {
        "intent": intent.model_dump(mode="json"),
        "mode": derived_result_mode(intent),
        "answerability": derived_answerability(intent),
        "normalized_temporal": normalize_temporal(intent),
        "entities": derived_entities(intent),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def run(cases: list[dict[str, Any]], repetitions: int, output: Path, model_name: str) -> None:
    model = OpenAIStructuredModel(api_key=os.environ.get("OPENAI_API_KEY"), model=model_name, timeout_seconds=60, max_retries=0, max_output_tokens=4096)
    output.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    for case in cases:
        for repetition in range(1, repetitions + 1):
            started = time.monotonic()
            row: dict[str, Any] = {"attempt_id": str(uuid.uuid4()), "question_id": case["id"], "question": case["question"], "repetition": repetition, "model": model.model_name}
            try:
                scope = model.parse(
                    purpose=SCOPE_PROMPT,
                    instructions="Capabilities: " + json.dumps({k: v["description"] for k, v in CAPABILITIES.items()}, ensure_ascii=False) + "\nQuestion: " + case["question"],
                    output_model=ScopeSelection,
                )
                assert isinstance(scope, ScopeSelection)
                catalog = scoped_catalog(scope.capabilities)
                intent = model.parse(
                    purpose=INTENT_PROMPT,
                    instructions="Provider temporal context: " + json.dumps({"source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE}) + "\nType capabilities: " + json.dumps(TYPE_CAPABILITIES) + "\nScoped conceptual fields: " + json.dumps(catalog["fields"], ensure_ascii=False) + "\nQuestion: " + case["question"],
                    output_model=SemanticQueryIntentV242,
                )
                assert isinstance(intent, SemanticQueryIntentV242)
                diffs = semantic_differences(case, scope, intent)
                row.update({
                    "structured_output_success": True,
                    "scope": scope.model_dump(mode="json"),
                    "scoped_fields": sorted(catalog["fields"]),
                    "raw_intent": intent.model_dump(mode="json"),
                    "derived_result_mode": derived_result_mode(intent),
                    "derived_answerability": derived_answerability(intent),
                    "derived_entities": derived_entities(intent),
                    "normalized_temporal": normalize_temporal(intent),
                    "eloquent_like": eloquent_like(intent),
                    "semantic_differences": diffs,
                    "semantic_success": not diffs,
                    "semantic_fingerprint": fingerprint(intent),
                    "response_diagnostics": model.last_response_diagnostics,
                })
            except Exception as exc:
                row.update({"structured_output_success": False, "semantic_success": False, "semantic_differences": [model.last_failure_class or "MODEL_FAILURE"], "exception_class": type(exc).__name__, "error": str(exc)[:300], "response_diagnostics": model.last_response_diagnostics})
            row["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("question_id", "repetition", "structured_output_success", "semantic_success", "semantic_differences", "latency_ms")}, ensure_ascii=False), flush=True)

    (output / "raw_responses.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    failures = Counter(diff for row in rows for diff in row.get("semantic_differences", []))
    metrics = {
        "total": len(rows),
        "structured_output_success_rate": sum(bool(x.get("structured_output_success")) for x in rows) / len(rows),
        "semantic_success_rate": sum(bool(x.get("semantic_success")) for x in rows) / len(rows),
        "failure_distribution": dict(failures),
    }
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"created_at": datetime.utcnow().isoformat() + "Z", "phase": "2.4.2", "model": model.model_name, "source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE, "retries": 0, "cases": len(cases), "repetitions": repetitions, "production_mcp_executed": False, "production_contract_changed": False}, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=ROOT / "evaluation/spikes/semantic_query_dsl_phase242_cases.jsonl")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    run(load_cases(args.cases), args.repetitions, args.output, args.model)


if __name__ == "__main__":
    main()
