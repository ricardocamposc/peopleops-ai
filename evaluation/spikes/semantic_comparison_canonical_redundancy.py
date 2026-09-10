"""Deterministic audit for redundant top-level temporal meaning in comparisons.

This module does not change the production/experimental canonicalizer. It proves
when a top-level ``temporal`` value duplicates ``comparison.left`` using typed
semantic structure only, and verifies that removing the duplicate does not alter
the compiled ``ComparisonPlan``.

Natural language, case IDs, languages, and expected datasets are deliberately
not inputs to the redundancy decision.
"""
from __future__ import annotations

from typing import Literal

import semantic_baseline_v1_runner_aligned as baseline_runner
import semantic_understanding_phase3 as phase3
import semantic_understanding_phase343 as phase343
import semantic_understanding_phase343_runner as phase343_runner

RedundancyClass = Literal[
    "NONE",
    "STRICT_EQUIVALENT",
    "EQUIVALENT_NON_RELATIVE_ANCHOR_METADATA",
    "NOT_EQUIVALENT",
]


def _core(value: phase343.TemporalMeaningV343) -> dict[str, object]:
    return phase343_runner.operand_core(value.model_dump())


def _without_non_relative_anchor(core: dict[str, object]) -> dict[str, object]:
    """Drop anchor metadata only when it cannot change relative semantics.

    ``relative_to`` is semantically material for PREVIOUS/LAST_N operands. For
    exact/current/explicit meanings it is non-operative metadata in the current
    compiler contract and may be ignored solely for equivalence classification.
    """
    normalized = dict(core)
    if normalized.get("relation") not in {"PREVIOUS", "LAST_N"}:
        normalized.pop("relative_to", None)
    return normalized


def classify_top_level_temporal_redundancy(
    value: phase343.SemanticUnderstandingV343,
) -> RedundancyClass:
    """Classify structural equivalence of top-level temporal and comparison.left."""
    if value.comparison is None or value.temporal is None:
        return "NONE"

    top = _core(value.temporal)
    left = _core(value.comparison.left)
    if top == left:
        return "STRICT_EQUIVALENT"
    if _without_non_relative_anchor(top) == _without_non_relative_anchor(left):
        return "EQUIVALENT_NON_RELATIVE_ANCHOR_METADATA"
    return "NOT_EQUIVALENT"


def strip_redundant_top_level_temporal(
    value: phase343.SemanticUnderstandingV343,
) -> phase343.SemanticUnderstandingV343:
    """Return a copy with duplicate top-level temporal removed when proven safe."""
    result = value.model_copy(deep=True)
    classification = classify_top_level_temporal_redundancy(result)
    if classification in {
        "STRICT_EQUIVALENT",
        "EQUIVALENT_NON_RELATIVE_ANCHOR_METADATA",
    }:
        result.temporal = None
    return result


def _plan_dump(value: phase343.SemanticUnderstandingV343) -> dict[str, object]:
    compiled = phase343.compile_comparison(value)
    return compiled.model_dump(mode="json")


def assert_redundancy_contract() -> None:
    """Synthetic adversarial tests for the mechanical redundancy rule."""
    measure = phase3.SemanticMeasure(
        field="overtime.approved_minutes", aggregation="SUM"
    )

    exact = phase343.SemanticUnderstandingV343(
        goal="compare overtime",
        measure=measure,
        temporal=phase343.TemporalMeaningV343(
            reference_frame="CURRENT_MONTH", relation="EXACT", unit="MONTH"
        ),
        comparison=phase343.ComparisonMeaningV343(
            left=phase343.TemporalMeaningV343(
                reference_frame="CURRENT_MONTH",
                relation="EXACT",
                unit="MONTH",
                relative_to="SOURCE_DATE",
            ),
            right=phase343.TemporalMeaningV343(
                reference_frame="CURRENT_MONTH",
                relation="PREVIOUS",
                unit="MONTH",
                relative_to="SOURCE_DATE",
            ),
            alignment="SAME_PERIOD",
        ),
    )
    assert (
        classify_top_level_temporal_redundancy(exact)
        == "EQUIVALENT_NON_RELATIVE_ANCHOR_METADATA"
    )
    stripped = strip_redundant_top_level_temporal(exact)
    assert stripped.temporal is None
    assert _plan_dump(exact) == _plan_dump(stripped)

    expected = {
        "answerability": "UNDERSTOOD_AND_EXECUTABLE",
        "requested_fields": [],
        "measure": {
            "field": "overtime.approved_minutes",
            "aggregation": "SUM",
        },
        "temporal": None,
        "comparison": {
            "left": {
                "reference_frame": "CURRENT_MONTH",
                "relation": "EXACT",
                "unit": "MONTH",
                "relative_to": "SOURCE_DATE",
            },
            "right": {
                "reference_frame": "CURRENT_MONTH",
                "relation": "PREVIOUS",
                "unit": "MONTH",
                "relative_to": "SOURCE_DATE",
            },
        },
        "alignment": "SAME_PERIOD",
        "operation": "SIDE_BY_SIDE",
        "breakdowns": [],
        "calendar_conditions": [],
        "order_by": [],
        "limit": None,
    }
    before = baseline_runner.understanding_differences(expected, exact)
    after = baseline_runner.understanding_differences(expected, stripped)
    assert "UNEXPECTED_SIMPLE_TEMPORAL" in before
    assert "UNEXPECTED_SIMPLE_TEMPORAL" not in after

    contradiction = exact.model_copy(deep=True)
    contradiction.temporal = phase343.TemporalMeaningV343(
        reference_frame="CURRENT_MONTH", relation="PREVIOUS", unit="MONTH"
    )
    assert classify_top_level_temporal_redundancy(contradiction) == "NOT_EQUIVALENT"
    assert strip_redundant_top_level_temporal(contradiction).temporal is not None

    anchor_mismatch = phase343.SemanticUnderstandingV343(
        goal="compare overtime",
        measure=measure,
        temporal=phase343.TemporalMeaningV343(
            reference_frame="CURRENT_MONTH",
            relation="PREVIOUS",
            unit="MONTH",
            relative_to="SOURCE_DATE",
        ),
        comparison=phase343.ComparisonMeaningV343(
            left=phase343.TemporalMeaningV343(
                reference_frame="CURRENT_MONTH",
                relation="PREVIOUS",
                unit="MONTH",
                relative_to="LEFT_OPERAND",
            ),
            right=phase343.TemporalMeaningV343(
                reference_frame="CURRENT_MONTH",
                relation="PREVIOUS",
                unit="MONTH",
                relative_to="SOURCE_DATE",
            ),
            alignment="SAME_PERIOD",
        ),
    )
    assert classify_top_level_temporal_redundancy(anchor_mismatch) == "NOT_EQUIVALENT"


if __name__ == "__main__":
    assert_redundancy_contract()
    print("SEMANTIC_COMPARISON_CANONICAL_REDUNDANCY_SELF_TEST_OK")
