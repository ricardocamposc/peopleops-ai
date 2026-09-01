"""Measurement evaluator v1.1.

Extends the validated v1 evaluator with an independent oracle for
CURRENT_DATE + LAST_N + YEAR temporal meanings. This is an objective
measurement bug fix required by Semantic Baseline v1; it does not change
Semantic Understanding, canonicalization, compilation, or normalization.
"""
from __future__ import annotations

from typing import Any

import semantic_comparison_baseline_evaluator_v1 as v1
import semantic_understanding_phase3 as phase3
import semantic_understanding_phase343 as phase343


def expected_scope_fingerprint(
    operand: dict[str, Any],
    *,
    field: str,
    left_operand: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Independent temporal oracle including CURRENT_DATE/LAST_N/YEAR."""
    frame = operand.get("reference_frame")
    relation = operand.get("relation")
    unit = operand.get("unit")

    if frame == "CURRENT_DATE" and relation == "LAST_N" and unit == "YEAR":
        count = operand.get("count")
        if not isinstance(count, int) or count < 1:
            return None
        return {
            "kind": "RELATIVE_RANGE",
            "field": field,
            "start": {
                "anchor": "SOURCE_DATE",
                "offset": -count,
                "unit": "YEAR",
            },
            "end": {
                "anchor": "SOURCE_DATE",
                "offset": 1 if operand.get("through_current_date") else 0,
                "unit": "DAY",
            },
        }

    return v1.expected_scope_fingerprint(
        operand,
        field=field,
        left_operand=left_operand,
    )


def compiler_differences(
    expected: dict[str, Any],
    canonical: phase343.SemanticUnderstandingV343,
    compiled: phase343.ComparisonPlan | phase3.SemanticQueryIntentV246,
) -> list[str]:
    """Audit compiler fidelity using the v1.1 temporal oracle."""
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
            expected_scope_fingerprint(expected["temporal"], field=field)
            if expected.get("temporal")
            else None
        )
        differences.extend(
            v1._audit_intent_components(
                "SIMPLE_",
                compiled,
                canonical,
                expected_scope,
            )
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
            v1._audit_intent_components(
                side_name,
                side_intent,
                canonical,
                expected_scope,
            )
        )

    return differences


def assert_evaluator_contract() -> None:
    """Run v1 checks plus the regression that invalidated Baseline v1."""
    v1.assert_evaluator_contract()
    v1._assert_non_executable_detection()

    field = "overtime.work_date"
    last_two_years = {
        "reference_frame": "CURRENT_DATE",
        "relation": "LAST_N",
        "unit": "YEAR",
        "count": 2,
        "through_current_date": True,
    }
    scope = expected_scope_fingerprint(last_two_years, field=field)
    assert scope == {
        "kind": "RELATIVE_RANGE",
        "field": field,
        "start": {
            "anchor": "SOURCE_DATE",
            "offset": -2,
            "unit": "YEAR",
        },
        "end": {
            "anchor": "SOURCE_DATE",
            "offset": 1,
            "unit": "DAY",
        },
    }
    assert v1.expected_normalized_scope(scope) == {
        "field": field,
        "start_inclusive": "2024-08-30",
        "end_exclusive": "2026-08-31",
    }


# Re-export stable helpers used by baseline runners.
expected_normalized_scope = v1.expected_normalized_scope
time_scope_fingerprint = v1.time_scope_fingerprint
temporal_point_fingerprint = v1.temporal_point_fingerprint
expected_group_by = v1.expected_group_by
expected_calendar_filters = v1.expected_calendar_filters


if __name__ == "__main__":
    assert_evaluator_contract()
    print("SEMANTIC_COMPARISON_BASELINE_EVALUATOR_V1_1_SELF_TEST_OK")
