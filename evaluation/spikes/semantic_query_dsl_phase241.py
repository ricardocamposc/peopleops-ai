"""Phase 2.4.1: corrected ORM-inspired Semantic Query Intent spike.

This preserves the validated Phase 2.4 ideas (capability scoping, qualified
conceptual fields, deterministic entity derivation) while removing redundant
or ambiguous decisions from the LLM:

- result mode is derived deterministically from result_fields/measures;
- answerability is decided once, during capability scoping;
- explicit year, month and month-list periods use separate structures;
- relative range start/end use different endpoint models so inclusive-end
  semantics can never shift the start boundary;
- relative requests must remain symbolic until deterministic normalization;
- Eloquent-like rendering is deterministic inspection output only.

No MCP, SQL, provider execution, Eloquent execution or production contract is
used by this spike.
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
            },
            "employee.full_name": {
                "data_type": "STRING",
                "semantic_type": "label",
            },
            "employee.hire_date": {
                "data_type": "DATE",
                "semantic_type": "calendar_date",
                "description": "Date on which the employee joined the company.",
            },
            "department.name": {
                "data_type": "STRING",
                "semantic_type": "label",
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
            },
            "payroll_period.code": {
                "data_type": "STRING",
                "semantic_type": "period_identifier",
                "description": "Payroll business period identifier; it is not a calendar DATE.",
            },
        },
    },
}

TYPE_CAPABILITIES = {
    "DATE": {
        "derivations": [
            "YEAR",
            "YEAR_MONTH",
            "MONTH",
            "DAY_OF_MONTH",
            "QUARTER",
            "WEEK",
            "WEEKDAY",
        ],
        "calendar_predicates": ["IS_LAST_DAY_OF_MONTH"],
    }
}


class Answerability(BaseModel):
    status: Literal[
        "UNDERSTOOD_AND_EXECUTABLE",
        "NEEDS_CLARIFICATION",
        "UNSUPPORTED_QUERY",
    ]
    reason: str | None = None


class ScopeSelection(BaseModel):
    capabilities: list[Literal["overtime", "workforce", "payroll"]] = Field(
        default_factory=list
    )
    answerability: Answerability


class Measure(BaseModel):
    field: str
    aggregation: Literal["SUM", "COUNT", "AVG", "MIN", "MAX"]
    alias: str | None = None


class ExplicitDateRange(BaseModel):
    field: str
    start_inclusive: str
    end_exclusive: str


class YearPeriod(BaseModel):
    field: str
    year: int


class MonthPeriod(BaseModel):
    field: str
    year: int
    month: int = Field(ge=1, le=12)


class MonthListPeriod(BaseModel):
    field: str
    year: int
    months: list[int] = Field(min_length=1)


class RelativeStart(BaseModel):
    anchor: Literal[
        "SOURCE_DATE",
        "START_OF_CURRENT_MONTH",
        "START_OF_CURRENT_YEAR",
    ]
    offset: int = 0
    unit: Literal["DAY", "MONTH", "YEAR"] = "DAY"


class RelativeEnd(BaseModel):
    anchor: Literal[
        "SOURCE_DATE",
        "START_OF_CURRENT_MONTH",
        "START_OF_CURRENT_YEAR",
    ]
    offset: int = 0
    unit: Literal["DAY", "MONTH", "YEAR"] = "DAY"
    include_anchor_day: bool = False


class RelativeDateRange(BaseModel):
    field: str
    start: RelativeStart
    end: RelativeEnd


class DerivedCondition(BaseModel):
    field: str
    derivation: Literal[
        "YEAR",
        "YEAR_MONTH",
        "MONTH",
        "DAY_OF_MONTH",
        "QUARTER",
        "WEEK",
        "WEEKDAY",
    ]
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
    derivation: Literal[
        "YEAR",
        "YEAR_MONTH",
        "MONTH",
        "DAY_OF_MONTH",
        "QUARTER",
        "WEEK",
        "WEEKDAY",
    ] | None = None


class OrderBy(BaseModel):
    field: str
    derivation: Literal[
        "YEAR",
        "YEAR_MONTH",
        "MONTH",
        "DAY_OF_MONTH",
        "QUARTER",
        "WEEK",
        "WEEKDAY",
    ] | None = None
    direction: Literal["ASC", "DESC"] = "ASC"


class SemanticQueryIntentV241(BaseModel):
    goal: str
    result_fields: list[str] = Field(default_factory=list)
    measures: list[Measure] = Field(default_factory=list)
    explicit_date_ranges: list[ExplicitDateRange] = Field(default_factory=list)
    year_periods: list[YearPeriod] = Field(default_factory=list)
    month_periods: list[MonthPeriod] = Field(default_factory=list)
    month_list_periods: list[MonthListPeriod] = Field(default_factory=list)
    relative_date_ranges: list[RelativeDateRange] = Field(default_factory=list)
    derived_conditions: list[DerivedCondition] = Field(default_factory=list)
    calendar_conditions: list[CalendarCondition] = Field(default_factory=list)
    scalar_conditions: list[ScalarCondition] = Field(default_factory=list)
    group_by: list[GroupBy] = Field(default_factory=list)
    order_by: list[OrderBy] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)


SCOPE_PROMPT = """Select the minimum conceptual capabilities required to answer the request.
Payroll is distinct and restricted; never select it merely because the user says period/month/year.
Do not select fields, entities, relationships, SQL, joins, or provider syntax.

Use NEEDS_CLARIFICATION only when a missing or ambiguous value would materially change the query and cannot
be determined from the question or provider temporal context. Concrete requests such as January 2026,
current month, every Monday during a specified year, the last day of each month, or the latest N employees
are executable when the capability exists. Use UNSUPPORTED_QUERY only when the requested concept or operation
cannot be expressed by the available capabilities. Do not use clarification as a generic uncertainty fallback.
"""

INTENT_PROMPT = """Translate the executable question into a minimal provider-neutral ORM/query-builder style
Semantic Query Intent. Use ONLY the scoped conceptual fields below. Do not emit entities, relationships,
joins, SQL, PHP, Eloquent text, raw expressions, DBMS functions, or fields outside scope.

RESULT semantics:
- result_fields contains ONLY row/detail attributes explicitly requested by the user.
- If the user asks to list/show records without naming output fields, leave result_fields empty. Safe default
  fields are supplied deterministically by the platform.
- measures contains analytical quantities/aggregations. Follow query_role/default_aggregation metadata.
- Do not copy filter fields or group_by fields into result_fields.
- There is NO result-mode field. The platform derives result mode deterministically:
    measures present -> AGGREGATED
    otherwise result_fields present -> EXPLICIT_FIELDS
    otherwise -> DEFAULT_FIELDS

DATE semantics:
- Explicit calendar year -> year_periods.
- Explicit single month with a year (January 2026, 2026-01, 202601) -> month_periods.
- Explicit list of months in one year -> month_list_periods.
- Explicit literal date-to-date request -> explicit_date_ranges.
- Relative requests MUST use relative_date_ranges. Never calculate/materialize absolute dates for relative requests.
- Do not duplicate one temporal intention across explicit and relative structures.
- current month: start START_OF_CURRENT_MONTH; end START_OF_CURRENT_MONTH +1 MONTH.
- previous month: start START_OF_CURRENT_MONTH -1 MONTH; end START_OF_CURRENT_MONTH.
- year through today: start START_OF_CURRENT_YEAR; end SOURCE_DATE with include_anchor_day=true.
- last two years through today: start SOURCE_DATE -2 YEAR; end SOURCE_DATE with include_anchor_day=true.
- last N months ending at the end of the current month: use START_OF_CURRENT_MONTH -(N-1) MONTH through
  START_OF_CURRENT_MONTH +1 MONTH.

Grouping is separate from filtering:
- 'by month' over more than one year should preserve year-month identity; YEAR_MONTH is preferred.
- A filter field is not automatically group_by.
- Every Monday uses derived_conditions WEEKDAY = MONDAY, never numeric weekday and never group_by unless
  the user explicitly requests grouping by weekday.
- First day of each month uses DAY_OF_MONTH = 1.
- Last day of each month uses IS_LAST_DAY_OF_MONTH.

Keep the intent minimal and do not duplicate semantics.
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


def all_refs(intent: SemanticQueryIntentV241) -> list[str]:
    refs = list(intent.result_fields)
    for collection in (
        intent.measures,
        intent.explicit_date_ranges,
        intent.year_periods,
        intent.month_periods,
        intent.month_list_periods,
        intent.relative_date_ranges,
        intent.derived_conditions,
        intent.calendar_conditions,
        intent.scalar_conditions,
        intent.group_by,
        intent.order_by,
    ):
        refs.extend(item.field for item in collection)
    return refs


def derived_entities(intent: SemanticQueryIntentV241) -> list[str]:
    return sorted({ref.split(".", 1)[0] for ref in all_refs(intent) if "." in ref})


def derived_result_mode(intent: SemanticQueryIntentV241) -> str:
    if intent.measures:
        return "AGGREGATED"
    if intent.result_fields:
        return "EXPLICIT_FIELDS"
    return "DEFAULT_FIELDS"


def days_in_month(year: int, month: int) -> int:
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (next_month - date(year, month, 1)).days


def add_months(value: date, amount: int) -> date:
    index = value.year * 12 + value.month - 1 + amount
    year, month_zero = divmod(index, 12)
    month = month_zero + 1
    return date(year, month, min(value.day, days_in_month(year, month)))


def add_years(value: date, amount: int) -> date:
    year = value.year + amount
    return date(year, value.month, min(value.day, days_in_month(year, value.month)))


def resolve_anchor(
    anchor: str,
    offset: int,
    unit: str,
    source: date = SOURCE_DATE,
) -> date:
    if anchor == "SOURCE_DATE":
        base = source
    elif anchor == "START_OF_CURRENT_MONTH":
        base = date(source.year, source.month, 1)
    else:
        base = date(source.year, 1, 1)

    if unit == "DAY":
        return base + timedelta(days=offset)
    if unit == "MONTH":
        return add_months(base, offset)
    return add_years(base, offset)


def resolve_relative_range(
    relative: RelativeDateRange,
    source: date = SOURCE_DATE,
) -> dict[str, str]:
    start = resolve_anchor(
        relative.start.anchor,
        relative.start.offset,
        relative.start.unit,
        source,
    )
    end = resolve_anchor(
        relative.end.anchor,
        relative.end.offset,
        relative.end.unit,
        source,
    )
    if relative.end.include_anchor_day:
        end += timedelta(days=1)
    return {
        "field": relative.field,
        "start_inclusive": start.isoformat(),
        "end_exclusive": end.isoformat(),
    }


def normalize_periods(intent: SemanticQueryIntentV241) -> list[dict[str, str]]:
    ranges: list[dict[str, str]] = []
    for period in intent.year_periods:
        ranges.append(
            {
                "field": period.field,
                "start_inclusive": f"{period.year:04d}-01-01",
                "end_exclusive": f"{period.year + 1:04d}-01-01",
            }
        )
    for period in intent.month_periods:
        start = date(period.year, period.month, 1)
        end = add_months(start, 1)
        ranges.append(
            {
                "field": period.field,
                "start_inclusive": start.isoformat(),
                "end_exclusive": end.isoformat(),
            }
        )
    for period in intent.month_list_periods:
        for month in period.months:
            if month < 1 or month > 12:
                continue
            start = date(period.year, month, 1)
            end = add_months(start, 1)
            ranges.append(
                {
                    "field": period.field,
                    "start_inclusive": start.isoformat(),
                    "end_exclusive": end.isoformat(),
                }
            )
    return ranges


def normalized_ranges(intent: SemanticQueryIntentV241) -> list[dict[str, str]]:
    result = [
        {
            "field": item.field,
            "start_inclusive": item.start_inclusive,
            "end_exclusive": item.end_exclusive,
        }
        for item in intent.explicit_date_ranges
    ]
    result.extend(normalize_periods(intent))
    result.extend(resolve_relative_range(item) for item in intent.relative_date_ranges)
    return result


def temporal_representation_counts(intent: SemanticQueryIntentV241) -> dict[str, int]:
    return {
        "explicit_date_ranges": len(intent.explicit_date_ranges),
        "year_periods": len(intent.year_periods),
        "month_periods": len(intent.month_periods),
        "month_list_periods": len(intent.month_list_periods),
        "relative_date_ranges": len(intent.relative_date_ranges),
    }


def validate(scope: ScopeSelection, intent: SemanticQueryIntentV241) -> dict[str, Any]:
    catalog = scoped_catalog(scope.capabilities)
    fields = catalog["fields"]
    refs = all_refs(intent)
    field_valid = all(ref in fields for ref in refs)

    measure_valid = all(
        fields.get(measure.field, {}).get("query_role") == "measure"
        for measure in intent.measures
    )

    derivations_valid = True
    weekday_valid = True
    for item in [*intent.derived_conditions, *intent.group_by, *intent.order_by]:
        derivation = getattr(item, "derivation", None)
        if derivation:
            metadata = fields.get(item.field, {})
            supported = TYPE_CAPABILITIES.get(metadata.get("data_type"), {}).get(
                "derivations", []
            )
            derivations_valid &= derivation in supported

    for item in intent.derived_conditions:
        if item.derivation == "WEEKDAY":
            supplied = [item.value] if item.operator == "EQ" else item.values
            weekday_valid &= all(
                value
                in {
                    "MONDAY",
                    "TUESDAY",
                    "WEDNESDAY",
                    "THURSDAY",
                    "FRIDAY",
                    "SATURDAY",
                    "SUNDAY",
                }
                for value in supplied
            )

    ranges = normalized_ranges(intent)
    ranges_valid = all(
        item["start_inclusive"] < item["end_exclusive"] for item in ranges
    )

    result_shape_valid = not (intent.result_fields and intent.measures)
    payroll_contamination = "payroll" not in scope.capabilities and any(
        ref.startswith("payroll") for ref in refs
    )

    return {
        "field_catalog_valid": field_valid,
        "measure_fields_valid": measure_valid,
        "derivations_valid": derivations_valid,
        "weekday_values_valid": weekday_valid,
        "ranges_valid": ranges_valid,
        "result_shape_valid": result_shape_valid,
        "derived_result_mode": derived_result_mode(intent),
        "derived_entities": derived_entities(intent),
        "payroll_contamination": payroll_contamination,
        "temporal_representation_counts": temporal_representation_counts(intent),
    }


def eloquent_like(intent: SemanticQueryIntentV241) -> str:
    """Deterministic, non-executable representation for human inspection."""
    entities = derived_entities(intent)
    root = entities[0] if entities else "Model"
    lines = [f"{root.title().replace('_', '')}::query()"]

    mode = derived_result_mode(intent)
    if mode == "DEFAULT_FIELDS":
        lines.append("    ->selectDefaultFields()")
    elif mode == "EXPLICIT_FIELDS":
        lines.append(
            "    ->select(["
            + ", ".join(repr(field) for field in intent.result_fields)
            + "])"
        )

    for measure in intent.measures:
        lines.append(
            f"    ->measure('{measure.aggregation}', '{measure.field}')"
        )

    for item in normalized_ranges(intent):
        lines.append(
            "    ->whereRange("
            f"'{item['field']}', '{item['start_inclusive']}', "
            f"'{item['end_exclusive']}'"
            ")"
        )

    for condition in intent.derived_conditions:
        value = condition.value if condition.operator == "EQ" else condition.values
        lines.append(
            "    ->whereDerived("
            f"'{condition.field}', '{condition.derivation}', "
            f"'{condition.operator}', {value!r}"
            ")"
        )

    for condition in intent.calendar_conditions:
        lines.append(
            f"    ->whereCalendar('{condition.field}', '{condition.predicate}')"
        )

    for condition in intent.scalar_conditions:
        lines.append(
            f"    ->where('{condition.field}', '{condition.operator}', {condition.value!r})"
        )

    for grouping in intent.group_by:
        if grouping.derivation:
            lines.append(
                f"    ->groupByDerived('{grouping.field}', '{grouping.derivation}')"
            )
        else:
            lines.append(f"    ->groupBy('{grouping.field}')")

    for ordering in intent.order_by:
        if ordering.derivation:
            lines.append(
                "    ->orderByDerived("
                f"'{ordering.field}', '{ordering.derivation}', "
                f"'{ordering.direction}'"
                ")"
            )
        else:
            lines.append(
                f"    ->orderBy('{ordering.field}', '{ordering.direction}')"
            )

    if intent.limit:
        lines.append(f"    ->limit({intent.limit})")
    lines.append("    ->get();")
    return "\n".join(lines)


def fingerprint(intent: SemanticQueryIntentV241) -> str:
    payload = {
        "result_mode": derived_result_mode(intent),
        "result_fields": sorted(intent.result_fields),
        "measures": sorted(
            (item.field, item.aggregation) for item in intent.measures
        ),
        "ranges": sorted(
            (item["field"], item["start_inclusive"], item["end_exclusive"])
            for item in normalized_ranges(intent)
        ),
        "derived": sorted(
            (
                item.field,
                item.derivation,
                item.operator,
                str(item.value),
                tuple(map(str, item.values)),
            )
            for item in intent.derived_conditions
        ),
        "calendar": sorted(
            (item.field, item.predicate) for item in intent.calendar_conditions
        ),
        "scalar": sorted(
            (item.field, item.operator, str(item.value))
            for item in intent.scalar_conditions
        ),
        "group_by": sorted(
            (item.field, item.derivation) for item in intent.group_by
        ),
        "order_by": sorted(
            (item.field, item.derivation, item.direction) for item in intent.order_by
        ),
        "limit": intent.limit,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def semantic_check(
    case: dict[str, Any],
    scope: ScopeSelection,
    intent: SemanticQueryIntentV241,
    checks: dict[str, Any],
) -> tuple[bool, list[str]]:
    expected = case["expected"]
    failures: list[str] = []
    expected_status = expected.get(
        "answerability", "UNDERSTOOD_AND_EXECUTABLE"
    )

    if scope.answerability.status != expected_status:
        failures.append("ANSWERABILITY_MISMATCH")
        return False, failures

    if expected_status != "UNDERSTOOD_AND_EXECUTABLE":
        return True, failures

    if sorted(scope.capabilities) != sorted(expected.get("capabilities", [])):
        failures.append("CAPABILITY_SCOPE_MISMATCH")
    if not checks["field_catalog_valid"]:
        failures.append("FIELD_OUTSIDE_SCOPED_CATALOG")
    if not checks["measure_fields_valid"]:
        failures.append("INVALID_MEASURE_FIELD")
    if not checks["derivations_valid"]:
        failures.append("UNSUPPORTED_DERIVATION")
    if not checks["weekday_values_valid"]:
        failures.append("NON_SEMANTIC_WEEKDAY_VALUE")
    if not checks["ranges_valid"]:
        failures.append("INVALID_RANGE")
    if not checks["result_shape_valid"]:
        failures.append("RESULT_SHAPE_CONFLICT")
    if checks["payroll_contamination"]:
        failures.append("PAYROLL_CONTAMINATION")

    if checks["derived_result_mode"] != expected.get("result_mode"):
        failures.append("RESULT_MODE_MISMATCH")
    if sorted(intent.result_fields) != sorted(expected.get("result_fields", [])):
        failures.append("RESULT_FIELDS_MISMATCH")
    if sorted(
        (item.field, item.aggregation) for item in intent.measures
    ) != sorted(
        (item["field"], item["aggregation"])
        for item in expected.get("measures", [])
    ):
        failures.append("MEASURE_MISMATCH")

    actual_ranges = sorted(
        (item["field"], item["start_inclusive"], item["end_exclusive"])
        for item in normalized_ranges(intent)
    )
    expected_ranges = sorted(
        (item["field"], item["start_inclusive"], item["end_exclusive"])
        for item in expected.get("normalized_ranges", [])
    )
    if actual_ranges != expected_ranges:
        failures.append("RANGE_MISMATCH")

    if expected.get("relative_required") and not intent.relative_date_ranges:
        failures.append("RELATIVE_INTENT_NOT_SYMBOLIC")
    if expected.get("relative_required") and (
        intent.explicit_date_ranges
        or intent.year_periods
        or intent.month_periods
        or intent.month_list_periods
    ):
        failures.append("RELATIVE_INTENT_DUPLICATED_AS_EXPLICIT")

    if sorted(
        (
            item.field,
            item.derivation,
            item.operator,
            str(item.value),
            tuple(map(str, item.values)),
        )
        for item in intent.derived_conditions
    ) != sorted(
        (
            item["field"],
            item["derivation"],
            item["operator"],
            str(item.get("value")),
            tuple(map(str, item.get("values", []))),
        )
        for item in expected.get("derived_conditions", [])
    ):
        failures.append("DERIVED_CONDITION_MISMATCH")

    if sorted(
        (item.field, item.predicate) for item in intent.calendar_conditions
    ) != sorted(
        (item["field"], item["predicate"])
        for item in expected.get("calendar_conditions", [])
    ):
        failures.append("CALENDAR_CONDITION_MISMATCH")

    if sorted(
        (item.field, item.derivation) for item in intent.group_by
    ) != sorted(
        (item["field"], item.get("derivation"))
        for item in expected.get("group_by", [])
    ):
        failures.append("GROUP_BY_MISMATCH")

    if sorted(
        (item.field, item.derivation, item.direction) for item in intent.order_by
    ) != sorted(
        (item["field"], item.get("derivation"), item["direction"])
        for item in expected.get("order_by", [])
    ):
        failures.append("ORDER_BY_MISMATCH")

    if intent.limit != expected.get("limit"):
        failures.append("LIMIT_MISMATCH")

    return not failures, failures


def run(
    cases: list[dict[str, Any]],
    repetitions: int,
    output: Path,
    model_name: str,
) -> None:
    model = OpenAIStructuredModel(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model=model_name,
        timeout_seconds=60,
        max_retries=0,
        max_output_tokens=4096,
    )
    output.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []

    for case in cases:
        for repetition in range(1, repetitions + 1):
            started = time.monotonic()
            row: dict[str, Any] = {
                "attempt_id": str(uuid.uuid4()),
                "question_id": case["id"],
                "question": case["question"],
                "repetition": repetition,
                "model": model.model_name,
            }
            try:
                scope = model.parse(
                    purpose=SCOPE_PROMPT,
                    instructions=(
                        "Capabilities: "
                        + json.dumps(
                            {
                                name: value["description"]
                                for name, value in CAPABILITIES.items()
                            },
                            ensure_ascii=False,
                        )
                        + "\nProvider temporal context: "
                        + json.dumps(
                            {
                                "source_current_date": SOURCE_DATE.isoformat(),
                                "source_timezone": SOURCE_TIMEZONE,
                            }
                        )
                        + "\nQuestion: "
                        + case["question"]
                    ),
                    output_model=ScopeSelection,
                )
                assert isinstance(scope, ScopeSelection)

                if scope.answerability.status == "UNDERSTOOD_AND_EXECUTABLE":
                    catalog = scoped_catalog(scope.capabilities)
                    intent = model.parse(
                        purpose=INTENT_PROMPT,
                        instructions=(
                            "Provider temporal context: "
                            + json.dumps(
                                {
                                    "source_current_date": SOURCE_DATE.isoformat(),
                                    "source_timezone": SOURCE_TIMEZONE,
                                }
                            )
                            + "\nType capabilities: "
                            + json.dumps(TYPE_CAPABILITIES)
                            + "\nScoped conceptual catalog: "
                            + json.dumps(catalog, ensure_ascii=False)
                            + "\nQuestion: "
                            + case["question"]
                        ),
                        output_model=SemanticQueryIntentV241,
                    )
                    assert isinstance(intent, SemanticQueryIntentV241)
                else:
                    intent = SemanticQueryIntentV241(goal="")

                checks = validate(scope, intent)
                semantic_success, failures = semantic_check(
                    case, scope, intent, checks
                )
                row.update(
                    {
                        "structured_output_success": True,
                        "scope": scope.model_dump(mode="json"),
                        "scoped_fields": sorted(
                            scoped_catalog(scope.capabilities)["fields"]
                        ),
                        "raw_intent": intent.model_dump(mode="json"),
                        "derived_result_mode": derived_result_mode(intent),
                        "normalized_ranges": normalized_ranges(intent),
                        "derived_entities": derived_entities(intent),
                        "eloquent_like": eloquent_like(intent),
                        "validation": checks,
                        "semantic_success": semantic_success,
                        "semantic_failures": failures,
                        "first_failure": failures[0] if failures else None,
                        "semantic_fingerprint": fingerprint(intent),
                        "response_diagnostics": model.last_response_diagnostics,
                    }
                )
            except Exception as exc:
                row.update(
                    {
                        "structured_output_success": False,
                        "semantic_success": False,
                        "semantic_failures": [
                            model.last_failure_class or "MODEL_FAILURE"
                        ],
                        "first_failure": model.last_failure_class
                        or "MODEL_FAILURE",
                        "exception_class": type(exc).__name__,
                        "error": str(exc)[:240],
                        "response_diagnostics": model.last_response_diagnostics,
                    }
                )

            row["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            rows.append(row)
            print(
                json.dumps(
                    {
                        key: row.get(key)
                        for key in (
                            "question_id",
                            "repetition",
                            "structured_output_success",
                            "semantic_success",
                            "first_failure",
                            "latency_ms",
                        )
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    (output / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    failure_counter: Counter[str] = Counter()
    for row in rows:
        failure_counter.update(row.get("semantic_failures", []))

    fingerprints: dict[str, Counter[str]] = {}
    for row in rows:
        fingerprint_value = row.get("semantic_fingerprint")
        if fingerprint_value:
            fingerprints.setdefault(row["question_id"], Counter())[
                fingerprint_value
            ] += 1
    consistency = {
        case_id: max(counter.values()) / sum(counter.values())
        for case_id, counter in fingerprints.items()
    }

    metrics = {
        "total": len(rows),
        "structured_output_success_rate": sum(
            bool(row.get("structured_output_success")) for row in rows
        )
        / len(rows),
        "semantic_success_rate": sum(
            bool(row.get("semantic_success")) for row in rows
        )
        / len(rows),
        "failure_distribution_all": dict(failure_counter),
        "semantic_fingerprint_consistency": consistency,
        "average_fingerprint_consistency": (
            sum(consistency.values()) / len(consistency) if consistency else None
        ),
    }
    (output / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": datetime.utcnow().isoformat() + "Z",
                "phase": "2.4.1",
                "model": model.model_name,
                "source_current_date": SOURCE_DATE.isoformat(),
                "source_timezone": SOURCE_TIMEZONE,
                "retries": 0,
                "cases": len(cases),
                "repetitions": repetitions,
                "production_mcp_executed": False,
                "production_contract_changed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=ROOT
        / "evaluation/spikes/semantic_query_dsl_phase241_cases.jsonl",
    )
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    )
    args = parser.parse_args()
    run(load_cases(args.cases), args.repetitions, args.output, args.model)


if __name__ == "__main__":
    main()
