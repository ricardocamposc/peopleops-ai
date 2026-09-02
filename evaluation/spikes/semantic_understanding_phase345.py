"""Phase 3.4.5 deterministic compiler candidate.

Extends the validated Phase 3.4.4 canonicalization with one compiler-only rule:
CURRENT_YEAR + PREVIOUS + YEAR is compiled as the previous complete calendar
year using provider-neutral TemporalPoint boundaries.

The rule consumes only structured Semantic Understanding. It never reads the
natural-language question, language, case ID, or expected dataset.
"""
from __future__ import annotations

import semantic_understanding_phase3 as phase3
import semantic_understanding_phase343 as phase343
import semantic_understanding_phase344 as phase344
from semantic_query_dsl_phase246 import (
    SemanticQueryIntentV246,
    TemporalPoint,
    TimeScopeV246,
)


def canonicalize(
    value: phase343.SemanticUnderstandingV343,
) -> phase343.SemanticUnderstandingV343:
    return phase344.canonicalize(value)


def _is_previous_calendar_year(
    temporal: phase343.TemporalMeaningV343 | None,
) -> bool:
    if temporal is None:
        return False
    return (
        temporal.reference_frame == "CURRENT_YEAR"
        and temporal.relation == "PREVIOUS"
        and temporal.unit == "YEAR"
        and temporal.relative_to in (None, "SOURCE_DATE")
    )


def _temporal_field(u: phase343.SemanticUnderstandingV343) -> str:
    if u.measure and u.measure.field.startswith("overtime."):
        return "overtime.work_date"
    return "employee.hire_date"


def _compile_previous_calendar_year(
    intent: SemanticQueryIntentV246,
    *,
    field: str,
) -> SemanticQueryIntentV246:
    if intent.time_scope is not None:
        return intent
    result = intent.model_copy(deep=True)
    result.time_scope = TimeScopeV246(
        field=field,
        kind="RELATIVE_RANGE",
        start=TemporalPoint(
            anchor="START_OF_CURRENT_YEAR", offset=-1, unit="YEAR"
        ),
        end=TemporalPoint(
            anchor="START_OF_CURRENT_YEAR", offset=0, unit="YEAR"
        ),
    )
    return result


def compile_semantic(
    u: phase343.SemanticUnderstandingV343,
) -> phase343.ComparisonPlan | SemanticQueryIntentV246:
    """Compile canonical semantics, adding only previous-calendar-year support."""
    compiled = phase343.compile_comparison(u)

    # Comparison operands already have CURRENT_YEAR/PREVIOUS support in
    # Phase 3.4.3 compile_operand(). The missing path is the simple-query
    # compiler inherited from Phase 3.
    if isinstance(compiled, phase343.ComparisonPlan):
        return compiled
    if u.comparison is not None or u.ambiguities or u.unsupported_reasons:
        return compiled
    if _is_previous_calendar_year(u.temporal):
        return _compile_previous_calendar_year(compiled, field=_temporal_field(u))
    return compiled


def assert_phase345_contract() -> None:
    phase344.assert_phase344_contract()

    value = phase343.SemanticUnderstandingV343(
        goal="previous year overtime",
        measure=phase3.SemanticMeasure(
            field="overtime.approved_minutes", aggregation="SUM"
        ),
        temporal=phase343.TemporalMeaningV343(
            reference_frame="CURRENT_YEAR",
            relation="PREVIOUS",
            unit="YEAR",
            relative_to="SOURCE_DATE",
        ),
    )
    canonical = canonicalize(value)
    compiled = compile_semantic(canonical)
    assert isinstance(compiled, SemanticQueryIntentV246)
    assert compiled.time_scope is not None
    assert compiled.time_scope.kind == "RELATIVE_RANGE"
    assert compiled.time_scope.start is not None
    assert compiled.time_scope.end is not None
    assert compiled.time_scope.start.anchor == "START_OF_CURRENT_YEAR"
    assert compiled.time_scope.start.offset == -1
    assert compiled.time_scope.start.unit == "YEAR"
    assert compiled.time_scope.end.anchor == "START_OF_CURRENT_YEAR"
    assert compiled.time_scope.end.offset == 0
    assert compiled.time_scope.end.unit == "YEAR"

    current = value.model_copy(deep=True)
    current.temporal = phase343.TemporalMeaningV343(
        reference_frame="CURRENT_YEAR",
        relation="FROM_START",
        unit="YEAR",
        through_current_date=True,
    )
    current_compiled = compile_semantic(canonicalize(current))
    assert isinstance(current_compiled, SemanticQueryIntentV246)
    assert current_compiled.time_scope is not None
    assert current_compiled.time_scope.end is not None
    assert current_compiled.time_scope.end.anchor == "SOURCE_DATE"


if __name__ == "__main__":
    assert_phase345_contract()
    print("SEMANTIC_UNDERSTANDING_PHASE345_SELF_TEST_OK")
