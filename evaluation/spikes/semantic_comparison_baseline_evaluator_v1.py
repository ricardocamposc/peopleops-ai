"""Independent evaluator for Semantic Understanding comparison baselines.

The evaluator never reads natural-language questions and never calls the
compiler under test to construct its expected oracle. It validates both
comparison plans and simple query intents, including non-executable safety and
independent normalized temporal expectations.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import semantic_understanding_phase3 as phase3
import semantic_understanding_phase343 as phase343
from semantic_query_dsl_phase242 import SOURCE_DATE


def temporal_point_fingerprint(point: Any) -> dict[str, Any] | None:
    if point is None:
        return None
    return {
        "anchor": point.anchor,
        "offset": point.offset,
        "unit": point.unit,
    }


def time_scope_fingerprint(scope: Any) -> dict[str, Any] | None:
    if scope is None:
        return None
    result: dict[str, Any] = {"kind": scope.kind, "field": scope.field}
    for key in ("year", "month"):
        value = getattr(scope, key, None)
        if value is not None:
            result[key] = value
    months = getattr(scope, "months", None)
    if months:
        result["months"] = list(months)
    start = temporal_point_fingerprint(getattr(scope, "start", None))
    end = temporal_point_fingerprint(getattr(scope, "end", None))
    if start is not None:
        result["start"] = start
    if end is not None:
        result["end"] = end
    start_inclusive = getattr(scope, "start_inclusive", None)
    end_exclusive = getattr(scope, "end_exclusive", None)
    if start_inclusive is not None:
        result["start_inclusive"] = start_inclusive
    if end_exclusive is not None:
        result["end_exclusive"] = end_exclusive
    return result


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year, month - 1) if month > 1 else (year - 1, 12)


def _add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    return date(year, month, 1)


def _resolve_expected_point(point: dict[str, Any]) -> date:
    anchor = point["anchor"]
    if anchor == "START_OF_CURRENT_MONTH":
        base = date(SOURCE_DATE.year, SOURCE_DATE.month, 1)
    elif anchor == "START_OF_CURRENT_YEAR":
        base = date(SOURCE_DATE.year, 1, 1)
    else:
        base = SOURCE_DATE
    offset = point.get("offset", 0)
    unit = point.get("unit", "DAY")
    if unit == "MONTH":
        return _add_months(base, offset)
    if unit == "YEAR":
        try:
            return base.replace(year=base.year + offset)
        except ValueError:
            return base.replace(year=base.year + offset, day=28)
    return base + timedelta(days=offset)


def expected_scope_fingerprint(
    operand: dict[str, Any],
    *,
    field: str,
    left_operand: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Independent oracle for temporal constructs supported by Phase 3.4.3."""
    frame = operand.get("reference_frame")
    relation = operand.get("relation")
    unit = operand.get("unit")
    relative_to = operand.get("relative_to")

    if frame == "EXPLICIT" and relation == "EXACT" and unit == "MONTH":
        return {
            "kind": "EXPLICIT_MONTH",
            "field": field,
            "year": operand["year"],
            "month": operand["month"],
        }
    if frame == "EXPLICIT" and relation == "EXACT" and unit == "YEAR":
        return {
            "kind": "EXPLICIT_YEAR",
            "field": field,
            "year": operand["year"],
        }

    if (
        relation == "PREVIOUS"
        and unit == "MONTH"
        and relative_to == "LEFT_OPERAND"
        and left_operand
        and left_operand.get("reference_frame") == "EXPLICIT"
        and left_operand.get("unit") == "MONTH"
    ):
        year, month = _previous_month(left_operand["year"], left_operand["month"])
        return {
            "kind": "EXPLICIT_MONTH",
            "field": field,
            "year": year,
            "month": month,
        }

    if frame == "CURRENT_MONTH" and unit == "MONTH":
        if relation == "EXACT":
            return {
                "kind": "RELATIVE_RANGE",
                "field": field,
                "start": {
                    "anchor": "START_OF_CURRENT_MONTH",
                    "offset": 0,
                    "unit": "MONTH",
                },
                "end": {
                    "anchor": "START_OF_CURRENT_MONTH",
                    "offset": 1,
                    "unit": "MONTH",
                },
            }
        if relation == "PREVIOUS":
            return {
                "kind": "RELATIVE_RANGE",
                "field": field,
                "start": {
                    "anchor": "START_OF_CURRENT_MONTH",
                    "offset": -1,
                    "unit": "MONTH",
                },
                "end": {
                    "anchor": "START_OF_CURRENT_MONTH",
                    "offset": 0,
                    "unit": "MONTH",
                },
            }

    if frame == "CURRENT_YEAR" and unit == "YEAR":
        months = operand.get("months") or []
        if months:
            year = SOURCE_DATE.year if relation == "EXACT" else SOURCE_DATE.year - 1
            return {
                "kind": "EXPLICIT_MONTH_LIST",
                "field": field,
                "year": year,
                "months": list(months),
            }
        if relation == "EXACT":
            return {
                "kind": "RELATIVE_RANGE",
                "field": field,
                "start": {
                    "anchor": "START_OF_CURRENT_YEAR",
                    "offset": 0,
                    "unit": "DAY",
                },
                "end": {
                    "anchor": "START_OF_CURRENT_YEAR",
                    "offset": 1,
                    "unit": "YEAR",
                },
            }
        if relation == "PREVIOUS":
            return {
                "kind": "RELATIVE_RANGE",
                "field": field,
                "start": {
                    "anchor": "START_OF_CURRENT_YEAR",
                    "offset": -1,
                    "unit": "YEAR",
                },
                "end": {
                    "anchor": "START_OF_CURRENT_YEAR",
                    "offset": 0,
                    "unit": "YEAR",
                },
            }

    return None


def expected_normalized_scope(scope: dict[str, Any] | None) -> dict[str, Any] | None:
    """Materialize an expected scope without using the compiler/normalizer under test."""
    if scope is None:
        return None
    kind = scope["kind"]
    field = scope["field"]
    if kind == "EXPLICIT_MONTH":
        start = date(scope["year"], scope["month"], 1)
        end = _add_months(start, 1)
        return {
            "field": field,
            "start_inclusive": start.isoformat(),
            "end_exclusive": end.isoformat(),
        }
    if kind == "EXPLICIT_YEAR":
        return {
            "field": field,
            "start_inclusive": f"{scope['year']:04d}-01-01",
            "end_exclusive": f"{scope['year'] + 1:04d}-01-01",
        }
    if kind == "EXPLICIT_MONTH_LIST":
        return {
            "field": field,
            "periods": [
                {"year": scope["year"], "month": month}
                for month in scope["months"]
            ],
        }
    if kind == "RELATIVE_RANGE":
        return {
            "field": field,
            "start_inclusive": _resolve_expected_point(scope["start"]).isoformat(),
            "end_exclusive": _resolve_expected_point(scope["end"]).isoformat(),
        }
    if kind == "EXPLICIT_DATE_RANGE":
        return {
            "field": field,
            "start_inclusive": scope["start_inclusive"],
            "end_exclusive": scope["end_exclusive"],
        }
    return None


def expected_group_by(canonical: phase343.SemanticUnderstandingV343) -> list[dict[str, Any]]:
    return [
        {
            "field": breakdown.field,
            "derivation": breakdown.grain if breakdown.kind == "TIME_GRAIN" else None,
        }
        for breakdown in canonical.breakdowns
    ]


def expected_calendar_filters(
    canonical: phase343.SemanticUnderstandingV343,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    derived: list[dict[str, Any]] = []
    predicates: list[dict[str, Any]] = []
    for condition in canonical.calendar_conditions:
        if condition.kind == "WEEKDAY":
            derived.append(
                {
                    "field": condition.field,
                    "derivation": "WEEKDAY",
                    "operator": "EQ",
                    "value": condition.value,
                }
            )
        elif condition.kind == "DAY_OF_MONTH":
            derived.append(
                {
                    "field": condition.field,
                    "derivation": "DAY_OF_MONTH",
                    "operator": "EQ",
                    "value": condition.value,
                }
            )
        elif condition.kind == "FIRST_DAY_OF_MONTH":
            derived.append(
                {
                    "field": condition.field,
                    "derivation": "DAY_OF_MONTH",
                    "operator": "EQ",
                    "value": 1,
                }
            )
        elif condition.kind == "LAST_DAY_OF_MONTH":
            predicates.append(
                {
                    "field": condition.field,
                    "predicate": "IS_LAST_DAY_OF_MONTH",
                }
            )
    return derived, predicates


def _model_dump_list(items: list[Any]) -> list[dict[str, Any]]:
    return [item.model_dump(exclude_none=True) for item in items]


def _has_executable_content(intent: phase3.SemanticQueryIntentV246) -> bool:
    return bool(
        intent.result_fields
        or intent.measures
        or intent.time_scope is not None
        or intent.derived_calendar_filters
        or intent.calendar_predicate_filters
        or intent.scalar_conditions
        or intent.group_by
        or intent.order_by
        or intent.limit is not None
    )


def _expected_measure(canonical: phase343.SemanticUnderstandingV343) -> list[dict[str, Any]]:
    return [] if canonical.measure is None else [canonical.measure.model_dump()]


def _temporal_field(canonical: phase343.SemanticUnderstandingV343) -> str:
    if canonical.measure and canonical.measure.field.startswith("overtime."):
        return "overtime.work_date"
    return "employee.hire_date"


def _audit_intent_components(
    prefix: str,
    intent: phase3.SemanticQueryIntentV246,
    canonical: phase343.SemanticUnderstandingV343,
    expected_scope: dict[str, Any] | None,
) -> list[str]:
    differences: list[str] = []
    if _model_dump_list(intent.measures) != _expected_measure(canonical):
        differences.append(f"{prefix}COMPILED_MEASURE_MISMATCH")
    if intent.result_fields != canonical.requested_fields:
        differences.append(f"{prefix}COMPILED_RESULT_FIELDS_MISMATCH")
    if _model_dump_list(intent.group_by) != expected_group_by(canonical):
        differences.append(f"{prefix}COMPILED_GROUP_BY_MISMATCH")
    if _model_dump_list(intent.order_by) != _model_dump_list(canonical.order_by):
        differences.append(f"{prefix}COMPILED_ORDER_BY_MISMATCH")
    if intent.limit != canonical.limit:
        differences.append(f"{prefix}COMPILED_LIMIT_MISMATCH")
    expected_derived, expected_predicates = expected_calendar_filters(canonical)
    if _model_dump_list(intent.derived_calendar_filters) != expected_derived:
        differences.append(f"{prefix}COMPILED_CALENDAR_FILTER_MISMATCH")
    if _model_dump_list(intent.calendar_predicate_filters) != expected_predicates:
        differences.append(f"{prefix}COMPILED_CALENDAR_PREDICATE_MISMATCH")
    actual_scope = time_scope_fingerprint(intent.time_scope)
    if actual_scope != expected_scope:
        differences.append(f"{prefix}COMPILED_TIME_SCOPE_MISMATCH")
    actual_normalized = phase3.normalize_time_scope(intent.time_scope)
    expected_normalized = expected_normalized_scope(expected_scope)
    if actual_normalized != expected_normalized:
        differences.append(f"{prefix}NORMALIZED_TIME_SCOPE_MISMATCH")
    return differences


def compiler_differences(
    expected: dict[str, Any],
    canonical: phase343.SemanticUnderstandingV343,
    compiled: phase343.ComparisonPlan | phase3.SemanticQueryIntentV246,
) -> list[str]:
    """Audit compiler fidelity independently from Semantic Understanding accuracy."""
    differences: list[str] = []
    expected_answerability = expected["answerability"]

    if canonical.unsupported_reasons:
        actual_answerability = "UNSUPPORTED_QUERY"
    elif canonical.ambiguities:
        actual_answerability = "NEEDS_CLARIFICATION"
    elif isinstance(compiled, phase343.ComparisonPlan):
        actual_answerability = "UNDERSTOOD_AND_EXECUTABLE"
    else:
        actual_answerability = phase3.derived_answerability(compiled)
    if actual_answerability != expected_answerability:
        differences.append("COMPILED_ANSWERABILITY_MISMATCH")

    expected_comparison = expected.get("comparison")
    if expected_answerability != "UNDERSTOOD_AND_EXECUTABLE":
        if isinstance(compiled, phase343.ComparisonPlan):
            differences.append("NON_EXECUTABLE_COMPARISON_PLAN_PRESENT")
        elif _has_executable_content(compiled):
            differences.append("NON_EXECUTABLE_QUERY_CONTENT_PRESENT")
        return differences

    field = _temporal_field(canonical)

    if expected_comparison is None:
        if isinstance(compiled, phase343.ComparisonPlan):
            differences.append("UNEXPECTED_COMPARISON_PLAN")
            return differences
        expected_scope = expected_scope_fingerprint(
            expected.get("temporal") or {},
            field=field,
        ) if expected.get("temporal") else None
        differences.extend(
            _audit_intent_components("SIMPLE_", compiled, canonical, expected_scope)
        )
        return differences

    if not isinstance(compiled, phase343.ComparisonPlan):
        differences.append("MISSING_COMPARISON_PLAN")
        return differences

    if compiled.alignment != expected.get("alignment"):
        differences.append("COMPILED_ALIGNMENT_MISMATCH")
    if compiled.operation != expected.get("operation"):
        differences.append("COMPILED_OPERATION_MISMATCH")

    for side_name, side_intent, operand, left_operand in (
        ("LEFT_", compiled.left, expected_comparison["left"], None),
        (
            "RIGHT_",
            compiled.right,
            expected_comparison["right"],
            expected_comparison["left"],
        ),
    ):
        expected_scope = expected_scope_fingerprint(
            operand,
            field=field,
            left_operand=left_operand,
        )
        differences.extend(
            _audit_intent_components(side_name, side_intent, canonical, expected_scope)
        )

    return differences


def assert_evaluator_contract() -> None:
    field = "overtime.work_date"
    january = {
        "reference_frame": "EXPLICIT",
        "relation": "EXACT",
        "unit": "MONTH",
        "year": 2026,
        "month": 1,
    }
    previous = {
        "reference_frame": "CURRENT_MONTH",
        "relation": "PREVIOUS",
        "unit": "MONTH",
        "relative_to": "LEFT_OPERAND",
    }
    january_scope = expected_scope_fingerprint(january, field=field)
    assert january_scope == {
        "kind": "EXPLICIT_MONTH",
        "field": field,
        "year": 2026,
        "month": 1,
    }
    previous_scope = expected_scope_fingerprint(
        previous,
        field=field,
        left_operand=january,
    )
    assert previous_scope == {
        "kind": "EXPLICIT_MONTH",
        "field": field,
        "year": 2025,
        "month": 12,
    }
    assert expected_normalized_scope(previous_scope) == {
        "field": field,
        "start_inclusive": "2025-12-01",
        "end_exclusive": "2026-01-01",
    }

    current_month = {
        "reference_frame": "CURRENT_MONTH",
        "relation": "EXACT",
        "unit": "MONTH",
        "relative_to": "SOURCE_DATE",
    }
    current_scope = expected_scope_fingerprint(current_month, field=field)
    assert current_scope is not None
    assert current_scope["kind"] == "RELATIVE_RANGE"
    assert expected_normalized_scope(current_scope) == {
        "field": field,
        "start_inclusive": "2026-08-01",
        "end_exclusive": "2026-09-01",
    }

    previous_year = {
        "reference_frame": "CURRENT_YEAR",
        "relation": "PREVIOUS",
        "unit": "YEAR",
        "relative_to": "SOURCE_DATE",
    }
    previous_year_scope = expected_scope_fingerprint(previous_year, field=field)
    assert previous_year_scope is not None
    assert previous_year_scope["start"]["offset"] == -1
    assert previous_year_scope["end"]["offset"] == 0


def _assert_non_executable_detection() -> None:
    canonical = phase343.SemanticUnderstandingV343(
        goal="ambiguous",
        ambiguities=["missing period unit"],
    )
    compiled = phase3.SemanticQueryIntentV246(
        goal="ambiguous",
        measures=[{"field": "overtime.approved_minutes", "aggregation": "SUM"}],
        ambiguities=["missing period unit"],
    )
    differences = compiler_differences(
        {"answerability": "NEEDS_CLARIFICATION", "comparison": None},
        canonical,
        compiled,
    )
    assert "NON_EXECUTABLE_QUERY_CONTENT_PRESENT" in differences


if __name__ == "__main__":
    assert_evaluator_contract()
    _assert_non_executable_detection()
    print("SEMANTIC_COMPARISON_BASELINE_EVALUATOR_V1_SELF_TEST_OK")
