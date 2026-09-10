"""Phase 3.4.3 experimental comparison contract."""
from __future__ import annotations

from datetime import date
from typing import Literal

import semantic_understanding_phase3 as phase3
import semantic_understanding_phase342 as phase342
from pydantic import BaseModel, Field
from semantic_query_dsl_phase242 import SOURCE_DATE
from semantic_query_dsl_phase246 import (
    SemanticQueryIntentV246,
    TemporalPoint,
    TimeScopeV246,
)


def _comparison_self_test() -> None:
    understanding = SemanticUnderstandingV343(
        goal="overtime",
        measure=phase3.SemanticMeasure(field="overtime.approved_minutes", aggregation="SUM"),
        comparison=ComparisonMeaningV343(
            left=TemporalMeaningV343(reference_frame="CURRENT_MONTH", relation="EXACT", unit="MONTH"),
            right=TemporalMeaningV343(reference_frame="CURRENT_MONTH", relation="PREVIOUS", unit="MONTH", relative_to="SOURCE_DATE"),
            alignment="SAME_PERIOD",
        ),
    )
    plan = compile_comparison(understanding)
    assert isinstance(plan, ComparisonPlan)
    assert plan.left.time_scope is not None and plan.right.time_scope is not None
    anchored = SemanticUnderstandingV343(
        goal="overtime",
        measure=phase3.SemanticMeasure(field="overtime.approved_minutes", aggregation="SUM"),
        comparison=ComparisonMeaningV343(
            left=TemporalMeaningV343(reference_frame="EXPLICIT", relation="EXACT", unit="MONTH", year=2026, month=1),
            right=TemporalMeaningV343(reference_frame="CURRENT_MONTH", relation="PREVIOUS", unit="MONTH", relative_to="LEFT_OPERAND"),
            alignment="SAME_PERIOD",
        ),
    )
    anchored_plan = compile_comparison(anchored)
    assert isinstance(anchored_plan, ComparisonPlan)
    assert anchored_plan.right.time_scope is not None
    assert anchored_plan.right.time_scope.year == 2025
    assert anchored_plan.right.time_scope.month == 12


class TemporalMeaningV343(phase342.TemporalMeaningV342):
    """Temporal meaning with an explicit semantic relative anchor."""

    relative_to: Literal["SOURCE_DATE", "LEFT_OPERAND", "STRUCTURED_CONTEXT"] | None = None


class ComparisonMeaningV343(BaseModel):
    left: TemporalMeaningV343
    right: TemporalMeaningV343
    alignment: Literal["SAME_PERIOD", "SAME_MONTH"]
    operation: Literal["SIDE_BY_SIDE", "DELTA", "PERCENT_CHANGE"] = "SIDE_BY_SIDE"


class ComparisonPlan(BaseModel):
    """Compiled inspection plan containing two independent query intents."""

    left: SemanticQueryIntentV246
    right: SemanticQueryIntentV246
    alignment: Literal["SAME_PERIOD", "SAME_MONTH"]
    operation: Literal["SIDE_BY_SIDE", "DELTA", "PERCENT_CHANGE"]


class SemanticUnderstandingV343(BaseModel):
    goal: str
    requested_fields: list[str] = Field(default_factory=list)
    measure: phase3.SemanticMeasure | None = None
    temporal: TemporalMeaningV343 | None = None
    comparison: ComparisonMeaningV343 | None = None
    breakdowns: list[phase3.BreakdownMeaning] = Field(default_factory=list)
    calendar_conditions: list[phase3.CalendarMeaning] = Field(default_factory=list)
    order_by: list[phase3.OrderBy] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    temporal_resolution_status: Literal["RESOLVED", "AMBIGUOUS", "UNSUPPORTED"] = "RESOLVED"
    ambiguities: list[str] = Field(default_factory=list)
    unsupported_reasons: list[str] = Field(default_factory=list)


COMPARISON_CONTRACT_V343 = """
PHASE 3.4.3 — COMPARISON SEMANTICS

When the request compares periods, preserve TWO independent operands in
comparison.left and comparison.right. Each operand has its own temporal
meaning; never collapse both into one temporal value.

For every relative operand, set relative_to explicitly: SOURCE_DATE when the
reference is the experiment date, LEFT_OPERAND when it is relative to the
preceding comparison operand, or STRUCTURED_CONTEXT when supplied externally.
Never infer an anchor from materialized dates.

Use SAME_MONTH when month identities are paired across years, otherwise use
SAME_PERIOD. Use SIDE_BY_SIDE unless the user explicitly asks for a delta or
percentage change. A repeated unit may be inherited only from an unambiguous
antecedent. 'previous period' without a unit remains ambiguous.

The same analytical measure applies to both operands. Do not add measure
fields to requested_fields. Keep relative operands symbolic; do not emit
absolute calculated dates. If either operand is ambiguous or unsupported,
populate the corresponding safety fields and do not create an executable
comparison.

When several named months are compared across years, represent each operand
as the relevant year relation with unit=YEAR and months=[...], and use
SAME_MONTH. Do not use EXPLICIT merely because the source date makes the
current year calculable. Do not turn that comparison into one arbitrary month
or a full-year comparison.
For a comparison of the current calendar year with the previous calendar
year, use unit=YEAR without through_current_date unless the request explicitly
says through today or year-to-date.
Use SAME_PERIOD for adjacent complete periods such as current month versus
previous month, and for an explicit month versus its previous month. Use
SAME_MONTH only when matching the same month identities across years.
For 'previous period' without a unit, set temporal_resolution_status=AMBIGUOUS,
populate ambiguities, leave that operand unit=null, and leave unsupported_reasons
empty. Do not classify missing granularity as unsupported.
In a comparison containing a generic 'period' operand, do not treat the other
operand's month/year as an implicit unit. Set the overall status to AMBIGUOUS,
set comparison=null, and do not emit any executable comparison content.
Contrast: 'January 2026 with the previous month' is executable because MONTH
is explicit; 'January 2026 with the previous period' is ambiguous because the
word period supplies no unit, even though January itself is a month.
"""

UNDERSTANDING_PROMPT_V343 = phase342.UNDERSTANDING_PROMPT_V342 + "\n" + COMPARISON_CONTRACT_V343


def assert_phase343_contract() -> None:
    phase342.assert_phase342_contract()
    assert "comparison.left" in COMPARISON_CONTRACT_V343
    assert "comparison.right" in COMPARISON_CONTRACT_V343
    assert "SAME_MONTH" in COMPARISON_CONTRACT_V343
    _comparison_self_test()


def _as_phase3(u: SemanticUnderstandingV343, temporal: phase342.TemporalMeaningV342 | None) -> phase3.SemanticUnderstanding:
    return phase3.SemanticUnderstanding.model_validate(
        {
            "goal": u.goal,
            "requested_fields": u.requested_fields,
            "measure": u.measure,
            "temporal": temporal.model_dump(exclude={"resolution_source", "resolution_evidence", "relative_to"}) if temporal else None,
            "breakdowns": u.breakdowns,
            "calendar_conditions": u.calendar_conditions,
            "order_by": u.order_by,
            "limit": u.limit,
            "ambiguities": [],
            "unsupported_reasons": [],
        }
    )


def compile_comparison(u: SemanticUnderstandingV343) -> ComparisonPlan | phase3.SemanticQueryIntentV246:
    """Compile structured operands; natural language never reaches this function."""
    if u.ambiguities or u.unsupported_reasons:
        return phase3.compile_understanding(
            phase3.SemanticUnderstanding(
                goal=u.goal,
                ambiguities=u.ambiguities,
                unsupported_reasons=u.unsupported_reasons,
            )
        )
    if u.comparison is None:
        return phase3.compile_understanding(_as_phase3(u, u.temporal))
    left = compile_operand(u, u.comparison.left)
    right = compile_operand(u, u.comparison.right, anchor=u.comparison.left)
    return ComparisonPlan(
        left=left,
        right=right,
        alignment=u.comparison.alignment,
        operation=u.comparison.operation,
    )


def compile_operand(
    u: SemanticUnderstandingV343,
    temporal: TemporalMeaningV343,
    *,
    anchor: TemporalMeaningV343 | None = None,
) -> SemanticQueryIntentV246:
    """Extend the frozen single-period compiler only for comparison operands."""
    if (
        temporal.relative_to == "LEFT_OPERAND"
        and anchor
        and anchor.reference_frame == "EXPLICIT"
        and anchor.unit == temporal.unit == "MONTH"
        and temporal.relation == "PREVIOUS"
        and anchor.year is not None
        and anchor.month is not None
    ):
        previous = date(anchor.year, anchor.month, 1)
        previous_year = previous.year if previous.month > 1 else previous.year - 1
        previous_month = previous.month - 1 if previous.month > 1 else 12
        base = phase3.compile_understanding(_as_phase3(u, anchor))
        base.time_scope = TimeScopeV246(
            field=base.time_scope.field if base.time_scope else "overtime.work_date",
            kind="EXPLICIT_MONTH",
            year=previous_year,
            month=previous_month,
        )
        return base
    base = phase3.compile_understanding(_as_phase3(u, temporal))
    if base.time_scope is not None:
        return base
    field = "overtime.work_date" if u.measure and u.measure.field.startswith("overtime.") else "employee.hire_date"
    if temporal.reference_frame == "CURRENT_YEAR" and temporal.unit == "YEAR":
        if temporal.months:
            year = SOURCE_DATE.year if temporal.relation == "EXACT" else SOURCE_DATE.year - 1
            base.time_scope = TimeScopeV246(
                field=field,
                kind="EXPLICIT_MONTH_LIST",
                year=year,
                months=temporal.months,
            )
            return base
        if temporal.relation == "EXACT":
            start = TemporalPoint(anchor="START_OF_CURRENT_YEAR", offset=0, unit="DAY")
            end = TemporalPoint(anchor="START_OF_CURRENT_YEAR", offset=1, unit="YEAR")
            base.time_scope = TimeScopeV246(field=field, kind="RELATIVE_RANGE", start=start, end=end)
        elif temporal.relation == "PREVIOUS":
            start = TemporalPoint(anchor="START_OF_CURRENT_YEAR", offset=-1, unit="YEAR")
            end = TemporalPoint(anchor="START_OF_CURRENT_YEAR", offset=0, unit="YEAR")
            base.time_scope = TimeScopeV246(field=field, kind="RELATIVE_RANGE", start=start, end=end)
    return base
