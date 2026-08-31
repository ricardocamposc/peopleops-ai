"""Phase 2.4: ORM-inspired Semantic Query Intent spike.

Goals:
- keep capability scoping and qualified conceptual fields from Phase 2.3;
- replace ambiguous projections with an explicit result contract;
- use a structured, provider-neutral Query Builder shape familiar to LLMs;
- keep relative and calendar semantics symbolic until deterministic normalization;
- derive entities from fields; do not let the LLM select entities/relationships;
- render an Eloquent-like representation deterministically for inspection only;
- do NOT execute Eloquent, SQL, MCP, or provider code.
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
            },
            "overtime.approved_minutes": {
                "data_type": "INTEGER",
                "semantic_type": "duration_minutes",
                "query_role": "measure",
                "default_aggregation": "SUM",
                "description": "Approved overtime duration in minutes.",
            },
        },
    },
    "workforce": {
        "description": "Employee and organization attributes used for identification and analytical breakdowns.",
        "default_result_fields": [
            "employee.employee_code",
            "employee.full_name",
            "employee.hire_date",
            "department.name",
        ],
        "fields": {
            "employee.employee_code": {"data_type": "STRING", "semantic_type": "identifier"},
            "employee.full_name": {"data_type": "STRING", "semantic_type": "label"},
            "employee.hire_date": {
                "data_type": "DATE",
                "semantic_type": "calendar_date",
                "description": "Date on which the employee joined the company.",
            },
            "department.name": {"data_type": "STRING", "semantic_type": "label"},
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
            },
            "payroll_period.code": {
                "data_type": "STRING",
                "semantic_type": "period_identifier",
                "description": "Payroll business period identifier; it is not a DATE.",
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


class Answerability(BaseModel):
    status: Literal["UNDERSTOOD_AND_EXECUTABLE", "NEEDS_CLARIFICATION", "UNSUPPORTED_QUERY"]
    reason: str | None = None


class ScopeSelection(BaseModel):
    capabilities: list[Literal["overtime", "workforce", "payroll"]] = Field(default_factory=list)
    answerability: Answerability


class ResultSpec(BaseModel):
    mode: Literal["DEFAULT_FIELDS", "EXPLICIT_FIELDS", "AGGREGATED"]
    fields: list[str] = Field(default_factory=list)


class Measure(BaseModel):
    field: str
    aggregation: Literal["SUM", "COUNT", "AVG", "MIN", "MAX"]
    alias: str | None = None


class ExplicitDateRange(BaseModel):
    field: str
    start_inclusive: str
    end_exclusive: str


class ExplicitPeriod(BaseModel):
    field: str
    grain: Literal["YEAR", "YEAR_MONTH", "MONTH"]
    year: int | None = None
    month: int | None = None
    months: list[int] = Field(default_factory=list)


class RelativeEndpoint(BaseModel):
    anchor: Literal["SOURCE_DATE", "START_OF_CURRENT_MONTH", "START_OF_CURRENT_YEAR"]
    offset: int = 0
    unit: Literal["DAY", "MONTH", "YEAR"] = "DAY"
    end_inclusive_day: bool = False


class RelativeDateRange(BaseModel):
    field: str
    start: RelativeEndpoint
    end: RelativeEndpoint


class DerivedCondition(BaseModel):
    field: str
    derivation: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY"]
    operator: Literal["EQ", "IN"]
    value: str | int | None = None
    values: list[str | int] = Field(default_factory=list)


class CalendarCondition(BaseModel):
    field: str
    predicate: Literal["IS_LAST_DAY_OF_MONTH"]


class ScalarCondition(BaseModel):
    field: str
    operator: Literal["EQ", "GT", "GTE", "LT", "LTE"]
    value: str | int | float


class GroupBy(BaseModel):
    field: str
    derivation: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY"] | None = None


class OrderBy(BaseModel):
    field: str
    derivation: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY"] | None = None
    direction: Literal["ASC", "DESC"] = "ASC"


class SemanticQueryIntentV24(BaseModel):
    goal: str
    result: ResultSpec
    measures: list[Measure] = Field(default_factory=list)
    explicit_date_ranges: list[ExplicitDateRange] = Field(default_factory=list)
    explicit_periods: list[ExplicitPeriod] = Field(default_factory=list)
    relative_date_ranges: list[RelativeDateRange] = Field(default_factory=list)
    derived_conditions: list[DerivedCondition] = Field(default_factory=list)
    calendar_conditions: list[CalendarCondition] = Field(default_factory=list)
    scalar_conditions: list[ScalarCondition] = Field(default_factory=list)
    group_by: list[GroupBy] = Field(default_factory=list)
    order_by: list[OrderBy] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    answerability: Answerability


SCOPE_PROMPT = """Select the minimum conceptual capabilities required to answer the request.
Payroll is distinct and restricted; never select it merely because the user says period/month/year.
Do not select fields, entities, relationships, SQL, joins, or provider syntax. If ambiguity materially
changes the result, use NEEDS_CLARIFICATION. If the requested concept is unavailable, use UNSUPPORTED_QUERY.
"""

INTENT_PROMPT = """Translate the question into a provider-neutral ORM/query-builder style Semantic Query Intent.
Use ONLY the scoped conceptual fields below. Do not emit entities, relationships, joins, SQL, PHP, Eloquent text,
raw expressions, DBMS functions, or fields outside scope.

RESULT semantics:
- DEFAULT_FIELDS: user asks to list/show records without naming output fields. The platform/provider will supply safe default fields.
- EXPLICIT_FIELDS: user explicitly names attributes to return as row/detail fields.
- AGGREGATED: result is analytical/aggregated; use measures. Do not add result fields just because they are used in filters or group_by.

Measures are analytical quantities. Follow catalog query_role/default_aggregation metadata.
A filter field is NOT automatically a result field. A group_by field is NOT automatically an extra result field in this intent contract.
The provider/query IR may later include grouping expressions in physical SELECT if required.

DATE semantics:
- Explicit month/year expressions belong in explicit_periods, not absolute ranges calculated by the model.
- Explicit literal date-to-date requests belong in explicit_date_ranges.
- Relative requests MUST use relative_date_ranges. Never calculate absolute dates for relative requests.
- RelativeEndpoint is generic: anchor + offset/unit. For an inclusive 'through today' end, use anchor SOURCE_DATE and end_inclusive_day=true.
- 'current month' = start START_OF_CURRENT_MONTH; end START_OF_CURRENT_MONTH offset +1 MONTH.
- 'previous month' = start START_OF_CURRENT_MONTH offset -1 MONTH; end START_OF_CURRENT_MONTH.
- 'last two years through today' = start SOURCE_DATE offset -2 YEAR; end SOURCE_DATE with end_inclusive_day=true.
- Grouping by month/year uses group_by derivations and is distinct from filtering by time.
- Every Monday uses derived_conditions WEEKDAY = MONDAY, never numeric weekday and never group_by unless user asks to group by weekday.
- First day of each month uses DAY_OF_MONTH = 1. Last day of each month uses calendar predicate IS_LAST_DAY_OF_MONTH.

Keep the output minimal. Do not duplicate semantics across multiple condition types.
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


def all_refs(intent: SemanticQueryIntentV24) -> list[str]:
    refs = list(intent.result.fields)
    for collection in (
        intent.measures,
        intent.explicit_date_ranges,
        intent.explicit_periods,
        intent.relative_date_ranges,
        intent.derived_conditions,
        intent.calendar_conditions,
        intent.scalar_conditions,
        intent.group_by,
        intent.order_by,
    ):
        refs.extend(item.field for item in collection)
    return refs


def derived_entities(intent: SemanticQueryIntentV24) -> list[str]:
    return sorted({ref.split(".", 1)[0] for ref in all_refs(intent) if "." in ref})


def days_in_month(year: int, month: int) -> int:
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (next_month - date(year, month, 1)).days


def add_months(value: date, amount: int) -> date:
    idx = value.year * 12 + value.month - 1 + amount
    year, month0 = divmod(idx, 12)
    month = month0 + 1
    return date(year, month, min(value.day, days_in_month(year, month)))


def add_years(value: date, amount: int) -> date:
    year = value.year + amount
    return date(year, value.month, min(value.day, days_in_month(year, value.month)))


def resolve_endpoint(endpoint: RelativeEndpoint, source: date = SOURCE_DATE) -> date:
    if endpoint.anchor == "SOURCE_DATE":
        base = source
    elif endpoint.anchor == "START_OF_CURRENT_MONTH":
        base = date(source.year, source.month, 1)
    else:
        base = date(source.year, 1, 1)

    if endpoint.unit == "DAY":
        value = base + timedelta(days=endpoint.offset)
    elif endpoint.unit == "MONTH":
        value = add_months(base, endpoint.offset)
    else:
        value = add_years(base, endpoint.offset)

    if endpoint.end_inclusive_day:
        value += timedelta(days=1)
    return value


def normalize_period(period: ExplicitPeriod) -> list[dict[str, str]]:
    ranges: list[dict[str, str]] = []
    if period.grain == "YEAR":
        if period.year is None:
            return []
        ranges.append({"field": period.field, "start_inclusive": f"{period.year:04d}-01-01", "end_exclusive": f"{period.year + 1:04d}-01-01"})
    elif period.grain == "YEAR_MONTH":
        if period.year is None or period.month is None:
            return []
        start = date(period.year, period.month, 1)
        end = add_months(start, 1)
        ranges.append({"field": period.field, "start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()})
    elif period.grain == "MONTH":
        if period.year is None or not period.months:
            return []
        for month in period.months:
            start = date(period.year, month, 1)
            end = add_months(start, 1)
            ranges.append({"field": period.field, "start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()})
    return ranges


def normalized_ranges(intent: SemanticQueryIntentV24) -> list[dict[str, str]]:
    result = [
        {"field": x.field, "start_inclusive": x.start_inclusive, "end_exclusive": x.end_exclusive}
        for x in intent.explicit_date_ranges
    ]
    for period in intent.explicit_periods:
        result.extend(normalize_period(period))
    for relative in intent.relative_date_ranges:
        result.append({
            "field": relative.field,
            "start_inclusive": resolve_endpoint(relative.start).isoformat(),
            "end_exclusive": resolve_endpoint(relative.end).isoformat(),
        })
    return result


def validate(scope: ScopeSelection, intent: SemanticQueryIntentV24) -> dict[str, Any]:
    catalog = scoped_catalog(scope.capabilities)
    fields = catalog["fields"]
    refs = all_refs(intent)
    field_valid = all(ref in fields for ref in refs)
    measure_valid = True
    for m in intent.measures:
        meta = fields.get(m.field, {})
        measure_valid &= meta.get("query_role") == "measure"
    derivations_valid = True
    weekday_valid = True
    for item in [*intent.derived_conditions, *intent.group_by, *intent.order_by]:
        derivation = getattr(item, "derivation", None)
        if derivation:
            meta = fields.get(item.field, {})
            derivations_valid &= derivation in TYPE_CAPABILITIES.get(meta.get("data_type"), {}).get("derivations", [])
    for item in intent.derived_conditions:
        if item.derivation == "WEEKDAY":
            supplied = [item.value] if item.operator == "EQ" else item.values
            weekday_valid &= all(v in {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"} for v in supplied)
    ranges = normalized_ranges(intent)
    ranges_valid = all(x["start_inclusive"] < x["end_exclusive"] for x in ranges)
    result_contract_valid = True
    if intent.result.mode == "DEFAULT_FIELDS":
        result_contract_valid &= not intent.result.fields
        result_contract_valid &= not intent.measures
    elif intent.result.mode == "EXPLICIT_FIELDS":
        result_contract_valid &= bool(intent.result.fields)
        result_contract_valid &= not intent.measures
    else:
        result_contract_valid &= bool(intent.measures)
        result_contract_valid &= not intent.result.fields
    payroll_contamination = "payroll" not in scope.capabilities and any(ref.startswith("payroll") for ref in refs)
    return {
        "field_catalog_valid": field_valid,
        "measure_fields_valid": measure_valid,
        "derivations_valid": derivations_valid,
        "weekday_values_valid": weekday_valid,
        "ranges_valid": ranges_valid,
        "result_contract_valid": result_contract_valid,
        "derived_entities": derived_entities(intent),
        "payroll_contamination": payroll_contamination,
    }


def eloquent_like(intent: SemanticQueryIntentV24) -> str:
    """Deterministic, non-executable rendering for human inspection only."""
    entities = derived_entities(intent)
    root = entities[0] if entities else "Model"
    lines = [f"{root.title().replace('_', '')}::query()"]
    if intent.result.mode == "DEFAULT_FIELDS":
        lines.append("    ->selectDefaultFields()")
    elif intent.result.mode == "EXPLICIT_FIELDS":
        lines.append("    ->select([" + ", ".join(repr(x) for x in intent.result.fields) + "])")
    for measure in intent.measures:
        lines.append(f"    ->measure('{measure.aggregation}', '{measure.field}')")
    for r in normalized_ranges(intent):
        lines.append(f"    ->whereRange('{r['field']}', '{r['start_inclusive']}', '{r['end_exclusive']}')")
    for c in intent.derived_conditions:
        value = c.value if c.operator == "EQ" else c.values
        lines.append(f"    ->whereDerived('{c.field}', '{c.derivation}', '{c.operator}', {value!r})")
    for c in intent.calendar_conditions:
        lines.append(f"    ->whereCalendar('{c.field}', '{c.predicate}')")
    for c in intent.scalar_conditions:
        lines.append(f"    ->where('{c.field}', '{c.operator}', {c.value!r})")
    for g in intent.group_by:
        if g.derivation:
            lines.append(f"    ->groupByDerived('{g.field}', '{g.derivation}')")
        else:
            lines.append(f"    ->groupBy('{g.field}')")
    for o in intent.order_by:
        if o.derivation:
            lines.append(f"    ->orderByDerived('{o.field}', '{o.derivation}', '{o.direction}')")
        else:
            lines.append(f"    ->orderBy('{o.field}', '{o.direction}')")
    if intent.limit:
        lines.append(f"    ->limit({intent.limit})")
    lines.append("    ->get();")
    return "\n".join(lines)


def fingerprint(intent: SemanticQueryIntentV24) -> str:
    payload = {
        "result": intent.result.model_dump(mode="json"),
        "measures": sorted((x.field, x.aggregation) for x in intent.measures),
        "ranges": sorted((x["field"], x["start_inclusive"], x["end_exclusive"]) for x in normalized_ranges(intent)),
        "derived": sorted((x.field, x.derivation, x.operator, str(x.value), tuple(map(str, x.values))) for x in intent.derived_conditions),
        "calendar": sorted((x.field, x.predicate) for x in intent.calendar_conditions),
        "scalar": sorted((x.field, x.operator, str(x.value)) for x in intent.scalar_conditions),
        "group_by": sorted((x.field, x.derivation) for x in intent.group_by),
        "order_by": sorted((x.field, x.derivation, x.direction) for x in intent.order_by),
        "limit": intent.limit,
        "answerability": intent.answerability.status,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def semantic_check(case: dict[str, Any], scope: ScopeSelection, intent: SemanticQueryIntentV24, checks: dict[str, Any]) -> tuple[bool, str | None]:
    e = case["expected"]
    expected_status = e.get("answerability", "UNDERSTOOD_AND_EXECUTABLE")
    if intent.answerability.status != expected_status:
        return False, "ANSWERABILITY_MISMATCH"
    if expected_status != "UNDERSTOOD_AND_EXECUTABLE":
        return True, None
    if sorted(scope.capabilities) != sorted(e.get("capabilities", [])):
        return False, "CAPABILITY_SCOPE_MISMATCH"
    for name, code in (
        ("field_catalog_valid", "FIELD_OUTSIDE_SCOPED_CATALOG"),
        ("measure_fields_valid", "INVALID_MEASURE_FIELD"),
        ("derivations_valid", "UNSUPPORTED_DERIVATION"),
        ("weekday_values_valid", "NON_SEMANTIC_WEEKDAY_VALUE"),
        ("ranges_valid", "INVALID_RANGE"),
        ("result_contract_valid", "RESULT_CONTRACT_MISMATCH"),
    ):
        if not checks[name]:
            return False, code
    if checks["payroll_contamination"]:
        return False, "PAYROLL_CONTAMINATION"
    if intent.result.mode != e.get("result_mode"):
        return False, "RESULT_MODE_MISMATCH"
    if sorted(intent.result.fields) != sorted(e.get("result_fields", [])):
        return False, "RESULT_FIELDS_MISMATCH"
    if sorted((x.field, x.aggregation) for x in intent.measures) != sorted((x["field"], x["aggregation"]) for x in e.get("measures", [])):
        return False, "MEASURE_MISMATCH"
    if sorted((x["field"], x["start_inclusive"], x["end_exclusive"]) for x in normalized_ranges(intent)) != sorted((x["field"], x["start_inclusive"], x["end_exclusive"]) for x in e.get("normalized_ranges", [])):
        return False, "RANGE_MISMATCH"
    if sorted((x.field, x.derivation, x.operator, str(x.value), tuple(map(str, x.values))) for x in intent.derived_conditions) != sorted((x["field"], x["derivation"], x["operator"], str(x.get("value")), tuple(map(str, x.get("values", [])))) for x in e.get("derived_conditions", [])):
        return False, "DERIVED_CONDITION_MISMATCH"
    if sorted((x.field, x.predicate) for x in intent.calendar_conditions) != sorted((x["field"], x["predicate"]) for x in e.get("calendar_conditions", [])):
        return False, "CALENDAR_CONDITION_MISMATCH"
    if sorted((x.field, x.derivation) for x in intent.group_by) != sorted((x["field"], x.get("derivation")) for x in e.get("group_by", [])):
        return False, "GROUP_BY_MISMATCH"
    if sorted((x.field, x.derivation, x.direction) for x in intent.order_by) != sorted((x["field"], x.get("derivation"), x["direction"]) for x in e.get("order_by", [])):
        return False, "ORDER_BY_MISMATCH"
    if intent.limit != e.get("limit"):
        return False, "LIMIT_MISMATCH"
    return True, None


def run(cases: list[dict[str, Any]], repetitions: int, output: Path, model_name: str) -> None:
    model = OpenAIStructuredModel(api_key=os.environ.get("OPENAI_API_KEY"), model=model_name, timeout_seconds=60, max_retries=0, max_output_tokens=4096)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for case in cases:
        for repetition in range(1, repetitions + 1):
            started = time.monotonic()
            row = {"attempt_id": str(uuid.uuid4()), "question_id": case["id"], "question": case["question"], "repetition": repetition, "model": model.model_name}
            try:
                scope = model.parse(purpose=SCOPE_PROMPT, instructions="Capabilities: " + json.dumps({k: v["description"] for k, v in CAPABILITIES.items()}, ensure_ascii=False) + "\nQuestion: " + case["question"], output_model=ScopeSelection)
                assert isinstance(scope, ScopeSelection)
                if scope.answerability.status == "UNDERSTOOD_AND_EXECUTABLE":
                    catalog = scoped_catalog(scope.capabilities)
                    intent = model.parse(purpose=INTENT_PROMPT, instructions="Provider temporal context: " + json.dumps({"source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE}) + "\nType capabilities: " + json.dumps(TYPE_CAPABILITIES) + "\nScoped conceptual catalog: " + json.dumps(catalog, ensure_ascii=False) + "\nQuestion: " + case["question"], output_model=SemanticQueryIntentV24)
                    assert isinstance(intent, SemanticQueryIntentV24)
                else:
                    intent = SemanticQueryIntentV24(goal="", result=ResultSpec(mode="DEFAULT_FIELDS"), answerability=scope.answerability)
                checks = validate(scope, intent)
                ok, failure = semantic_check(case, scope, intent, checks)
                row.update({"structured_output_success": True, "scope": scope.model_dump(mode="json"), "scoped_fields": sorted(scoped_catalog(scope.capabilities)["fields"]), "raw_intent": intent.model_dump(mode="json"), "normalized_ranges": normalized_ranges(intent), "derived_entities": derived_entities(intent), "eloquent_like": eloquent_like(intent), "validation": checks, "semantic_success": ok, "first_failure": failure, "semantic_fingerprint": fingerprint(intent), "response_diagnostics": model.last_response_diagnostics})
            except Exception as exc:
                row.update({"structured_output_success": False, "semantic_success": False, "first_failure": model.last_failure_class or "MODEL_FAILURE", "exception_class": type(exc).__name__, "error": str(exc)[:240], "response_diagnostics": model.last_response_diagnostics})
            row["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("question_id", "repetition", "structured_output_success", "semantic_success", "first_failure", "latency_ms")}, ensure_ascii=False), flush=True)
    (output / "raw_responses.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    failures = Counter(x.get("first_failure") for x in rows if x.get("first_failure"))
    fingerprints: dict[str, Counter[str]] = {}
    for x in rows:
        if x.get("semantic_fingerprint"):
            fingerprints.setdefault(x["question_id"], Counter())[x["semantic_fingerprint"]] += 1
    consistency = {k: max(v.values()) / sum(v.values()) for k, v in fingerprints.items()}
    metrics = {"total": len(rows), "structured_output_success_rate": sum(bool(x.get("structured_output_success")) for x in rows) / len(rows), "semantic_success_rate": sum(bool(x.get("semantic_success")) for x in rows) / len(rows), "failure_distribution": dict(failures), "semantic_fingerprint_consistency": consistency, "average_fingerprint_consistency": sum(consistency.values()) / len(consistency) if consistency else None}
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"created_at": datetime.utcnow().isoformat() + "Z", "phase": "2.4", "model": model.model_name, "source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE, "retries": 0, "cases": len(cases), "repetitions": repetitions, "eloquent_like_is_non_executable_debug_rendering": True, "production_mcp_executed": False, "production_contract_changed": False}, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=ROOT / "evaluation/spikes/semantic_query_dsl_phase24_cases.jsonl")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    run(load_cases(args.cases), args.repetitions, args.output, args.model)


if __name__ == "__main__":
    main()
