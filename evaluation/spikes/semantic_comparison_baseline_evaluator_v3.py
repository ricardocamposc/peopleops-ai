"""Semantic baseline evaluator v3.

Builds on evaluator v2 and fixes one remaining measurement artifact: GroupBy
objects are compared by semantic content rather than Pydantic serialization
shape. In particular, a FIELD breakdown with derivation=None is equivalent to
an actual GroupBy whose exclude_none dump omits the derivation key.

No natural-language question, language, case ID, compiler, or normalizer is
used to construct grouping expectations.
"""
from __future__ import annotations

from typing import Any

import semantic_comparison_baseline_evaluator_v2 as v2
import semantic_understanding_phase3 as phase3
import semantic_understanding_phase343 as phase343


def _group_fingerprint(value: Any) -> dict[str, Any]:
    """Return only the provider-neutral semantic grouping meaning."""
    if isinstance(value, dict):
        field = value.get("field")
        derivation = value.get("derivation")
    else:
        field = value.field
        derivation = value.derivation
    result: dict[str, Any] = {"field": field}
    if derivation is not None:
        result["derivation"] = derivation
    return result


def expected_group_fingerprints(
    canonical: phase343.SemanticUnderstandingV343,
) -> list[dict[str, Any]]:
    return [
        _group_fingerprint(
            {
                "field": breakdown.field,
                "derivation": breakdown.grain
                if breakdown.kind == "TIME_GRAIN"
                else None,
            }
        )
        for breakdown in canonical.breakdowns
    ]


def actual_group_fingerprints(
    intent: phase3.SemanticQueryIntentV246,
) -> list[dict[str, Any]]:
    return [_group_fingerprint(item) for item in intent.group_by]


def _group_difference_is_real(
    compiled: phase343.ComparisonPlan | phase3.SemanticQueryIntentV246,
    canonical: phase343.SemanticUnderstandingV343,
    prefix: str,
) -> bool:
    expected = expected_group_fingerprints(canonical)
    if isinstance(compiled, phase343.ComparisonPlan):
        intent = compiled.left if prefix == "LEFT_" else compiled.right
    else:
        intent = compiled
    return actual_group_fingerprints(intent) != expected


def compiler_differences(
    expected: dict[str, Any],
    canonical: phase343.SemanticUnderstandingV343,
    compiled: phase343.ComparisonPlan | phase3.SemanticQueryIntentV246,
) -> list[str]:
    """Use v2 for all semantics, removing grouping shape-only mismatches."""
    differences = v2.compiler_differences(expected, canonical, compiled)
    result: list[str] = []
    grouping_prefixes = {
        "SIMPLE_COMPILED_GROUP_BY_MISMATCH": "SIMPLE_",
        "LEFT_COMPILED_GROUP_BY_MISMATCH": "LEFT_",
        "RIGHT_COMPILED_GROUP_BY_MISMATCH": "RIGHT_",
    }
    for difference in differences:
        prefix = grouping_prefixes.get(difference)
        if prefix is None:
            result.append(difference)
            continue
        if _group_difference_is_real(compiled, canonical, prefix):
            result.append(difference)
    return result


def assert_evaluator_contract() -> None:
    v2.assert_evaluator_contract()

    canonical = phase343.SemanticUnderstandingV343(
        goal="group by department",
        measure=phase3.SemanticMeasure(
            field="overtime.approved_minutes", aggregation="SUM"
        ),
        temporal=phase343.TemporalMeaningV343(
            reference_frame="EXPLICIT",
            relation="EXACT",
            unit="MONTH",
            year=2026,
            month=1,
        ),
        breakdowns=[
            phase3.BreakdownMeaning(kind="FIELD", field="department.name")
        ],
    )
    compiled = phase3.compile_understanding(
        phase3.SemanticUnderstanding.model_validate(
            {
                "goal": canonical.goal,
                "requested_fields": canonical.requested_fields,
                "measure": canonical.measure,
                "temporal": canonical.temporal.model_dump(
                    exclude={
                        "resolution_source",
                        "resolution_evidence",
                        "relative_to",
                    }
                ),
                "breakdowns": canonical.breakdowns,
                "calendar_conditions": canonical.calendar_conditions,
                "order_by": canonical.order_by,
                "limit": canonical.limit,
            }
        )
    )
    expected = {
        "answerability": "UNDERSTOOD_AND_EXECUTABLE",
        "requested_fields": [],
        "measure": {
            "field": "overtime.approved_minutes",
            "aggregation": "SUM",
        },
        "temporal": {
            "reference_frame": "EXPLICIT",
            "relation": "EXACT",
            "unit": "MONTH",
            "year": 2026,
            "month": 1,
        },
        "comparison": None,
        "breakdowns": [{"kind": "FIELD", "field": "department.name"}],
        "calendar_conditions": [],
        "order_by": [],
        "limit": None,
    }
    assert "SIMPLE_COMPILED_GROUP_BY_MISMATCH" in v2.compiler_differences(
        expected, canonical, compiled
    )
    assert compiler_differences(expected, canonical, compiled) == []

    broken = compiled.model_copy(deep=True)
    broken.group_by = []
    assert "SIMPLE_COMPILED_GROUP_BY_MISMATCH" in compiler_differences(
        expected, canonical, broken
    )


if __name__ == "__main__":
    assert_evaluator_contract()
    print("SEMANTIC_COMPARISON_BASELINE_EVALUATOR_V3_SELF_TEST_OK")
