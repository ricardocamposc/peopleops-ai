"""Independent evaluator for Semantic Understanding comparison baselines.

The evaluator never reads natural-language questions and never calls the
production/query compiler to construct its expected compiler oracle. It checks
that a valid canonical SemanticUnderstanding is faithfully compiled into two
independent provider-neutral query intents.
"""
from __future__ import annotations

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


def expected_scope_fingerprint(
    operand: dict[str, Any],
    *,
    field: str,
    left_operand: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Independent oracle for the temporal constructs supported by Phase 3.4.3."""
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
    if expected_comparison is None:
        if isinstance(compiled, phase343.ComparisonPlan):
            differences.append("UNEXPECTED_COMPARISON_PLAN")
        return differences

    if not isinstance(compiled, phase343.ComparisonPlan):
        differences.append("MISSING_COMPARISON_PLAN")
        return differences

    if compiled.alignment != expected.get("alignment"):
        differences.append("COMPILED_ALIGNMENT_MISMATCH")
    if compiled.operation != expected.get("operation"):
        differences.append("COMPILED_OPERATION_MISMATCH")

    expected_measure = [] if canonical.measure is None else [canonical.measure.model_dump()]
    expected_derived, expected_predicates = expected_calendar_filters(canonical)
    expected_groups = expected_group_by(canonical)
    expected_order = _model_dump_list(canonical.order_by)

    field = (
        "overtime.work_date"
        if canonical.measure and canonical.measure.field.startswith("overtime.")
        else "employee.hire_date"
    )

    for side_name, side_intent, operand, left_operand in (
        ("LEFT", compiled.left, expected_comparison["left"], None),
        (
            "RIGHT",
            compiled.right,
            expected_comparison["right"],
            expected_comparison["left"],
        ),
    ):
        if _model_dump_list(side_intent.measures) != expected_measure:
            differences.append(f"{side_name}_COMPILED_MEASURE_MISMATCH")
        if side_intent.result_fields != canonical.requested_fields:
            differences.append(f"{side_name}_COMPILED_RESULT_FIELDS_MISMATCH")
        if _model_dump_list(side_intent.group_by) != expected_groups:
            differences.append(f"{side_name}_COMPILED_GROUP_BY_MISMATCH")
        if _model_dump_list(side_intent.order_by) != expected_order:
            differences.append(f"{side_name}_COMPILED_ORDER_BY_MISMATCH")
        if side_intent.limit != canonical.limit:
            differences.append(f"{side_name}_COMPILED_LIMIT_MISMATCH")
        if _model_dump_list(side_intent.derived_calendar_filters) != expected_derived:
            differences.append(f"{side_name}_COMPILED_CALENDAR_FILTER_MISMATCH")
        if _model_dump_list(side_intent.calendar_predicate_filters) != expected_predicates:
            differences.append(f"{side_name}_COMPILED_CALENDAR_PREDICATE_MISMATCH")

        expected_scope = expected_scope_fingerprint(
            operand,
            field=field,
            left_operand=left_operand,
        )
        actual_scope = time_scope_fingerprint(side_intent.time_scope)
        if actual_scope != expected_scope:
            differences.append(f"{side_name}_COMPILED_TIME_SCOPE_MISMATCH")

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
    assert expected_scope_fingerprint(january, field=field) == {
        "kind": "EXPLICIT_MONTH",
        "field": field,
        "year": 2026,
        "month": 1,
    }
    assert expected_scope_fingerprint(
        previous, field=field, left_operand=january
    ) == {
        "kind": "EXPLICIT_MONTH",
        "field": field,
        "year": 2025,
        "month": 12,
    }
    current_month = {
        "reference_frame": "CURRENT_MONTH",
        "relation": "EXACT",
        "unit": "MONTH",
        "relative_to": "SOURCE_DATE",
    }
    assert expected_scope_fingerprint(current_month, field=field)["kind"] == "RELATIVE_RANGE"
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


if __name__ == "__main__":
    assert_evaluator_contract()
    print("SEMANTIC_COMPARISON_BASELINE_EVALUATOR_V1_SELF_TEST_OK")
