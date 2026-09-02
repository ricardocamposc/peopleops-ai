"""Semantic Baseline evaluator v2.

This evaluator keeps the v1 independent-oracle approach but fixes two classes of
measurement defects discovered by the 240-row offline replay:

1. calendar filters are compared by semantic fingerprint, ignoring Pydantic
   transport metadata such as ``type`` and empty ``values``;
2. the independent temporal oracle covers the relative constructs already
   supported by the frozen semantic contract (LAST_N months, YTD/FROM_START,
   previous year, and LAST_N years through the source date).

The evaluator never reads natural-language questions and never calls the
compiler under test to construct expected values.
"""
from __future__ import annotations

from typing import Any

import semantic_comparison_baseline_evaluator_v1 as v1
import semantic_understanding_phase3 as phase3
import semantic_understanding_phase343 as phase343

EVALUATOR_VERSION = "semantic-comparison-baseline-evaluator-v2"


def expected_scope_fingerprint(
    operand: dict[str, Any],
    *,
    field: str,
    left_operand: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Independent temporal oracle for the frozen Phase 3.4.x contract."""
    base = v1.expected_scope_fingerprint(
        operand,
        field=field,
        left_operand=left_operand,
    )
    if base is not None:
        return base

    frame = operand.get("reference_frame")
    relation = operand.get("relation")
    unit = operand.get("unit")
    count = operand.get("count")
    through_current_date = bool(operand.get("through_current_date"))

    if frame == "CURRENT_MONTH" and relation == "LAST_N" and unit == "MONTH" and count:
        return {
            "kind": "RELATIVE_RANGE",
            "field": field,
            "start": {
                "anchor": "START_OF_CURRENT_MONTH",
                "offset": -(count - 1),
                "unit": "MONTH",
            },
            "end": {
                "anchor": "START_OF_CURRENT_MONTH",
                "offset": 1,
                "unit": "MONTH",
            },
        }

    if (
        frame == "CURRENT_YEAR"
        and relation == "FROM_START"
        and unit == "YEAR"
        and through_current_date
    ):
        return {
            "kind": "RELATIVE_RANGE",
            "field": field,
            "start": {
                "anchor": "START_OF_CURRENT_YEAR",
                "offset": 0,
                "unit": "DAY",
            },
            "end": {
                "anchor": "SOURCE_DATE",
                "offset": 1,
                "unit": "DAY",
            },
        }

    if (
        frame == "CURRENT_DATE"
        and relation == "LAST_N"
        and unit in {"DAY", "MONTH", "YEAR"}
        and count
        and through_current_date
    ):
        return {
            "kind": "RELATIVE_RANGE",
            "field": field,
            "start": {
                "anchor": "SOURCE_DATE",
                "offset": -count,
                "unit": unit,
            },
            "end": {
                "anchor": "SOURCE_DATE",
                "offset": 1,
                "unit": "DAY",
            },
        }

    return None


def _derived_fingerprint(item: Any) -> dict[str, Any]:
    return {
        "field": item.field,
        "derivation": item.derivation,
        "operator": item.operator,
        **({"value": item.value} if item.value is not None else {}),
        **({"values": list(item.values)} if item.values else {}),
    }


def _predicate_fingerprint(item: Any) -> dict[str, Any]:
    return {
        "field": item.field,
        "predicate": item.predicate,
    }


def expected_calendar_filters(
    canonical: phase343.SemanticUnderstandingV343,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expected semantic calendar fingerprints, without transport metadata."""
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


def _audit_intent_components(
    prefix: str,
    intent: phase3.SemanticQueryIntentV246,
    canonical: phase343.SemanticUnderstandingV343,
    expected_scope: dict[str, Any] | None,
) -> list[str]:
    differences: list[str] = []
    if [x.model_dump() for x in intent.measures] != v1._expected_measure(canonical):
        differences.append(f"{prefix}COMPILED_MEASURE_MISMATCH")
    if intent.result_fields != canonical.requested_fields:
        differences.append(f"{prefix}COMPILED_RESULT_FIELDS_MISMATCH")
    if [x.model_dump(exclude_none=True) for x in intent.group_by] != v1.expected_group_by(canonical):
        differences.append(f"{prefix}COMPILED_GROUP_BY_MISMATCH")
    if [x.model_dump(exclude_none=True) for x in intent.order_by] != [
        x.model_dump(exclude_none=True) for x in canonical.order_by
    ]:
        differences.append(f"{prefix}COMPILED_ORDER_BY_MISMATCH")
    if intent.limit != canonical.limit:
        differences.append(f"{prefix}COMPILED_LIMIT_MISMATCH")

    expected_derived, expected_predicates = expected_calendar_filters(canonical)
    actual_derived = [_derived_fingerprint(x) for x in intent.derived_calendar_filters]
    actual_predicates = [_predicate_fingerprint(x) for x in intent.calendar_predicate_filters]
    if actual_derived != expected_derived:
        differences.append(f"{prefix}COMPILED_CALENDAR_FILTER_MISMATCH")
    if actual_predicates != expected_predicates:
        differences.append(f"{prefix}COMPILED_CALENDAR_PREDICATE_MISMATCH")

    actual_scope = v1.time_scope_fingerprint(intent.time_scope)
    if actual_scope != expected_scope:
        differences.append(f"{prefix}COMPILED_TIME_SCOPE_MISMATCH")
    actual_normalized = phase3.normalize_time_scope(intent.time_scope)
    expected_normalized = v1.expected_normalized_scope(expected_scope)
    if actual_normalized != expected_normalized:
        differences.append(f"{prefix}NORMALIZED_TIME_SCOPE_MISMATCH")
    return differences


def compiler_differences(
    expected: dict[str, Any],
    canonical: phase343.SemanticUnderstandingV343,
    compiled: phase343.ComparisonPlan | phase3.SemanticQueryIntentV246,
) -> list[str]:
    """Audit compiler fidelity independently of understanding accuracy."""
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
        elif v1._has_executable_content(compiled):
            differences.append("NON_EXECUTABLE_QUERY_CONTENT_PRESENT")
        return differences

    field = v1._temporal_field(canonical)

    if expected_comparison is None:
        if isinstance(compiled, phase343.ComparisonPlan):
            differences.append("UNEXPECTED_COMPARISON_PLAN")
            return differences
        expected_scope = (
            expected_scope_fingerprint(expected.get("temporal") or {}, field=field)
            if expected.get("temporal")
            else None
        )
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
        ("RIGHT_", compiled.right, expected_comparison["right"], expected_comparison["left"]),
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
    """Synthetic checks for the measurement defects fixed by v2."""
    v1.assert_evaluator_contract()

    canonical = phase343.SemanticUnderstandingV343(
        goal="calendar",
        measure=phase3.SemanticMeasure(
            field="overtime.approved_minutes", aggregation="SUM"
        ),
        temporal=phase343.TemporalMeaningV343(
            reference_frame="EXPLICIT", relation="EXACT", unit="YEAR", year=2026
        ),
        calendar_conditions=[
            phase3.CalendarMeaning(
                kind="DAY_OF_MONTH", field="overtime.work_date", value=15
            )
        ],
    )
    compiled = phase3.compile_understanding(canonical)
    expected = {
        "answerability": "UNDERSTOOD_AND_EXECUTABLE",
        "requested_fields": [],
        "measure": {"field": "overtime.approved_minutes", "aggregation": "SUM"},
        "temporal": {
            "reference_frame": "EXPLICIT",
            "relation": "EXACT",
            "unit": "YEAR",
            "year": 2026,
        },
        "comparison": None,
        "breakdowns": [],
        "calendar_conditions": [
            {"kind": "DAY_OF_MONTH", "field": "overtime.work_date", "value": 15}
        ],
        "order_by": [],
        "limit": None,
    }
    assert compiler_differences(expected, canonical, compiled) == []

    ytd = {
        "reference_frame": "CURRENT_YEAR",
        "relation": "FROM_START",
        "unit": "YEAR",
        "through_current_date": True,
    }
    scope = expected_scope_fingerprint(ytd, field="overtime.work_date")
    assert scope is not None
    assert scope["start"]["anchor"] == "START_OF_CURRENT_YEAR"
    assert scope["end"]["anchor"] == "SOURCE_DATE"


if __name__ == "__main__":
    assert_evaluator_contract()
    print("SEMANTIC_COMPARISON_BASELINE_EVALUATOR_V2_SELF_TEST_OK")
