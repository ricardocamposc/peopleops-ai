"""Phase 3.4.4 deterministic comparison canonicalization candidate.

This phase composes the frozen Phase 3.4.3 canonicalizer with one additional
mechanical rule that has already been proven by offline replay: remove a
redundant top-level temporal only when it is structurally equivalent to
comparison.left and doing so cannot alter relative anchoring semantics.

The rule never reads natural language, language, case IDs, or expected data.
"""
from __future__ import annotations

import semantic_comparison_canonical_redundancy as redundancy
import semantic_understanding_phase343 as phase343
import semantic_understanding_phase343_runner as phase343_runner


def canonicalize(
    value: phase343.SemanticUnderstandingV343,
) -> phase343.SemanticUnderstandingV343:
    """Apply frozen Phase 3.4.3 canonicalization, then safe redundancy removal."""
    canonical = phase343_runner.canonicalize(value)
    return redundancy.strip_redundant_top_level_temporal(canonical)


def assert_phase344_contract() -> None:
    redundancy.assert_redundancy_contract()

    current = phase343.TemporalMeaningV343(
        reference_frame="CURRENT_MONTH", relation="EXACT", unit="MONTH"
    )
    value = phase343.SemanticUnderstandingV343(
        goal="compare",
        temporal=current,
        comparison=phase343.ComparisonMeaningV343(
            left=current.model_copy(deep=True),
            right=phase343.TemporalMeaningV343(
                reference_frame="CURRENT_MONTH",
                relation="PREVIOUS",
                unit="MONTH",
                relative_to="SOURCE_DATE",
            ),
            alignment="SAME_PERIOD",
        ),
    )
    canonical = canonicalize(value)
    assert canonical.comparison is not None
    assert canonical.temporal is None

    mismatch = value.model_copy(deep=True)
    mismatch.temporal = phase343.TemporalMeaningV343(
        reference_frame="CURRENT_MONTH",
        relation="PREVIOUS",
        unit="MONTH",
        relative_to="LEFT_OPERAND",
    )
    protected = canonicalize(mismatch)
    assert protected.temporal is not None


if __name__ == "__main__":
    assert_phase344_contract()
    print("SEMANTIC_UNDERSTANDING_PHASE344_SELF_TEST_OK")
