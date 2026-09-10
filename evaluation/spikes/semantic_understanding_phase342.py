"""Phase 3.4.2 — structured temporal resolution and safe abstention.

Experimental-only layer. It does not modify Phase 3.4.1, the canonicalizer,
compiler, normalizer, capability closure, or provider boundaries.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Literal

import semantic_understanding_phase3 as phase3
import semantic_understanding_phase34 as phase34
import semantic_understanding_phase341 as phase341
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]


class TemporalMeaningV342(BaseModel):
    reference_frame: Literal["EXPLICIT", "CURRENT_MONTH", "CURRENT_YEAR", "CURRENT_DATE"]
    relation: Literal["EXACT", "PREVIOUS", "LAST_N", "FROM_START"]
    unit: Literal["DAY", "MONTH", "YEAR", "WEEK", "PAYROLL_PERIOD"] | None = None
    count: int | None = Field(default=None, ge=1)
    year: int | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    months: list[int] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    through_current_date: bool = False
    resolution_source: Literal["EXPLICIT", "ANTECEDENT", "STRUCTURED_CONTEXT", "UNRESOLVED"] = "EXPLICIT"
    resolution_evidence: str | None = None


class TemporalComparisonV342(BaseModel):
    left: TemporalMeaningV342
    right: TemporalMeaningV342


class SemanticUnderstandingV342(BaseModel):
    """Phase-local output contract; existing compiler remains unchanged."""

    goal: str
    requested_fields: list[str] = Field(default_factory=list)
    measure: phase3.SemanticMeasure | None = None
    temporal: TemporalMeaningV342 | None = None
    comparison: TemporalComparisonV342 | None = None
    breakdowns: list[phase3.BreakdownMeaning] = Field(default_factory=list)
    calendar_conditions: list[phase3.CalendarMeaning] = Field(default_factory=list)
    order_by: list[phase3.OrderBy] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    temporal_resolution_status: Literal["RESOLVED", "AMBIGUOUS", "UNSUPPORTED"] = "RESOLVED"
    ambiguities: list[str] = Field(default_factory=list)
    unsupported_reasons: list[str] = Field(default_factory=list)


def resolve_structured_temporal(value: SemanticUnderstandingV342) -> SemanticUnderstandingV342:
    """Mark unresolved temporal granularity ambiguous without reading question text."""
    if value.temporal_resolution_status == "AMBIGUOUS" and not value.unsupported_reasons:
        value.unsupported_reasons = []
        if "Temporal meaning is unresolved." not in value.ambiguities:
            value.ambiguities.append("Temporal meaning is unresolved.")
    elif value.temporal_resolution_status == "UNSUPPORTED" or value.unsupported_reasons:
        value.ambiguities = []
        value.temporal_resolution_status = "UNSUPPORTED"
        if "Temporal meaning is unsupported by the contract." not in value.unsupported_reasons:
            value.unsupported_reasons.append("Temporal meaning is unsupported by the contract.")
    elif value.unsupported_reasons:
        value.ambiguities = []
        value.temporal_resolution_status = "UNSUPPORTED"
    if value.temporal and value.temporal.relation == "PREVIOUS" and value.temporal.unit is None:
        if "Temporal unit is unresolved." not in value.ambiguities:
            value.ambiguities.append("Temporal unit is unresolved.")
        value.temporal.resolution_source = "UNRESOLVED"
    if value.temporal and value.temporal.unit in {"WEEK", "PAYROLL_PERIOD"}:
        value.temporal_resolution_status = "UNSUPPORTED"
        value.ambiguities = []
        if "Temporal unit is outside the current compiler contract." not in value.unsupported_reasons:
            value.unsupported_reasons.append("Temporal unit is outside the current compiler contract.")
    if value.comparison:
        left, right = value.comparison.left, value.comparison.right
        if right.relation == "PREVIOUS" and right.unit is None and left.unit is not None:
            right.unit = left.unit
            right.resolution_source = "STRUCTURED_CONTEXT" if left.resolution_source == "STRUCTURED_CONTEXT" else "ANTECEDENT"
            right.resolution_evidence = "The preceding comparison operand establishes the temporal unit."
    return value


def to_phase3_understanding(value: SemanticUnderstandingV342) -> phase3.SemanticUnderstanding:
    """Adapt valid Phase 3.4.2 meaning to the frozen Phase 3 compiler contract."""
    value = validate_for_pipeline(value)
    data = value.model_dump(exclude={"comparison"})
    data.pop("temporal_resolution_status", None)
    if value.ambiguities or value.unsupported_reasons:
        data["temporal"] = None
    elif value.temporal is not None:
        data["temporal"] = value.temporal.model_dump(exclude={"resolution_source", "resolution_evidence"})
    return phase3.SemanticUnderstanding.model_validate(data)


def validate_for_pipeline(value: SemanticUnderstandingV342) -> SemanticUnderstandingV342:
    """Apply structured safety invariants without inspecting natural language."""
    value = resolve_structured_temporal(value.model_copy(deep=True))
    if value.comparison is not None:
        value.unsupported_reasons.append("Temporal comparison requires a dedicated compiler contract.")
    relative = value.temporal and value.temporal.reference_frame != "EXPLICIT"
    if relative and value.temporal is not None:
        value.temporal.year = None
        value.temporal.month = None
        value.temporal.months = []
        value.temporal.start_date = None
        value.temporal.end_date = None
    for operand in (value.comparison.left, value.comparison.right) if value.comparison else ():
        if operand.reference_frame != "EXPLICIT":
            operand.year = None
            operand.month = None
            operand.months = []
            operand.start_date = None
            operand.end_date = None
    if value.ambiguities or value.unsupported_reasons:
        value.requested_fields = []
        value.measure = None
        value.temporal = None
        value.breakdowns = []
        value.calendar_conditions = []
        value.order_by = []
        value.limit = None
    return value

TEMPORAL_RESOLUTION_CONTRACT_V342 = """
PHASE 3.4.2 — STRUCTURED TEMPORAL RESOLUTION CONTRACT

Resolve a temporal expression only from explicit wording, an unambiguous
temporal antecedent, or the supplied structured temporal context.

The word period does not supply a unit. Previous period, prior period, and
equivalents remain NEEDS_CLARIFICATION unless an unambiguous antecedent or
structured context establishes the unit.

A structured context value such as temporal_unit=MONTH is authoritative for
this request only. It is not a language keyword rule and must not be inferred
from the question.

If a relative relation is clear but its unit is missing, return unit=null and
resolution_source=UNRESOLVED. Do not choose MONTH, YEAR, DAY, or a payroll unit.

You MUST set temporal_resolution_status:
- RESOLVED only when the unit is explicit, inherited from an unambiguous
  antecedent, or supplied by structured context.
- AMBIGUOUS when a temporal unit is missing or multiple units are plausible.
- UNSUPPORTED when one clear temporal unit is requested but the contract cannot
  represent it.

For a resolved temporal, set resolution_source to EXPLICIT, ANTECEDENT, or
STRUCTURED_CONTEXT and briefly record resolution_evidence. For an unresolved
temporal, use UNRESOLVED and leave unit null.

In a comparison, a repeated unit is EXPLICIT only when it is stated on that
operand. A pronoun or elliptical reference such as 'the previous one' inherits
the unit from the preceding operand and must use ANTECEDENT, with evidence that
the preceding operand supplied the unit. Do not label inherited meaning as
EXPLICIT merely because the inherited unit is known.

Examples:
- 'previous month' => RESOLVED, unit=MONTH.
- 'previous period' => AMBIGUOUS, unit=null, ambiguities non-empty.
- 'previous week' => UNSUPPORTED, unit=null, unsupported_reasons non-empty when
  WEEK is outside the current contract.
- For an unsupported but clear unit, use that unit (for example WEEK or
  PAYROLL_PERIOD) and set status=UNSUPPORTED; do not replace it with DAY or
  leave it unresolved.
- Never encode 'previous week' as PREVIOUS DAY with count=7. That is a
  different meaning and is not an acceptable substitute for an unsupported
  calendar week.
- 'previous year' => RESOLVED, unit=YEAR, when the current contract supports it.
- 'previous calendar year' => RESOLVED, CURRENT_YEAR + PREVIOUS + YEAR. Do not
  materialize it as EXPLICIT year=2025; the source date is for deterministic
  normalization, not for changing the semantic representation.
- Any PREVIOUS or LAST_N relation with a relative reference frame must keep
  the semantic relation and unit; never replace it with an explicit computed
  year or month.
- 'previous period' with temporal_unit=MONTH in structured context => RESOLVED,
  unit=MONTH, resolution_source=STRUCTURED_CONTEXT.
- 'previous period' with no context => AMBIGUOUS, unit=null.
- 'previous period' with structured temporal context temporal_unit=PAYROLL_PERIOD
  => UNSUPPORTED, unit=null, because the provider contract has no payroll-period
  temporal compiler in this experiment.

Do not use AMBIGUOUS when structured context supplies a clear but unsupported
unit. Use UNSUPPORTED instead.

If the temporal unit is WEEK or PAYROLL_PERIOD, status=UNSUPPORTED is mandatory
even if the rest of the request looks executable.

The three statuses are mutually exclusive: do not populate both ambiguities
and unsupported_reasons. If a clear unit is outside the contract, use only
UNSUPPORTED. If the unit cannot be resolved, use only AMBIGUOUS.

If a request compares two temporal periods, preserve both operands in the
comparison object. Do not collapse the request into one temporal value. The
existing compiler does not execute this experimental comparison object; the
runner must retain it for the independent comparison-contract work.
- 'Dame las horas extras del período anterior.' => AMBIGUOUS; do not convert
  período into month.
- 'Show me overtime for the previous period.' => AMBIGUOUS; do not convert
  period into month.
- 'Mostre as horas extras do período anterior.' => AMBIGUOUS; do not convert
  período into month.

When temporal_resolution_status is AMBIGUOUS, set temporal=null and do not
populate measure, breakdowns, calendar_conditions, order_by, or limit merely
from the guessed interpretation.

For comparisons, preserve both temporal meanings in comparison.left and
comparison.right. Do not collapse a comparison into one temporal value.

A clear but unsupported unit is UNSUPPORTED_QUERY, not NEEDS_CLARIFICATION.

Relative meaning must remain symbolic: do not add absolute year, month,
start_date, or end_date values when they are merely derivable from the source
date. Interpret; do not calculate.

When ambiguity or unsupported_reasons is present, do not preserve executable
semantic content. The deterministic canonicalizer will enforce that invariant.
"""

UNDERSTANDING_PROMPT_V342 = (
    phase341.UNDERSTANDING_PROMPT_V341
    + "\n"
    + TEMPORAL_RESOLUTION_CONTRACT_V342
)


def assert_phase342_contract() -> None:
    """Run deterministic safety checks without calling an LLM."""
    phase341.assert_non_executable_canonicalization()
    contract = TEMPORAL_RESOLUTION_CONTRACT_V342.lower()
    assert "previous period" in contract
    assert "structured temporal context" in contract
    unresolved = SemanticUnderstandingV342(
        goal="overtime",
        temporal=TemporalMeaningV342(reference_frame="CURRENT_MONTH", relation="PREVIOUS", unit=None),
    )
    resolved = resolve_structured_temporal(unresolved)
    assert resolved.ambiguities
    adapted = to_phase3_understanding(resolved)
    assert adapted.temporal is None
    assert adapted.ambiguities
    unsupported = SemanticUnderstandingV342(
        goal="overtime",
        temporal_resolution_status="UNSUPPORTED",
    )
    assert resolve_structured_temporal(unsupported).unsupported_reasons
    materialized = SemanticUnderstandingV342(
        goal="overtime",
        temporal=TemporalMeaningV342(
            reference_frame="CURRENT_MONTH",
            relation="PREVIOUS",
            unit="MONTH",
            year=2026,
            month=7,
        ),
    )
    validated = validate_for_pipeline(materialized)
    assert validated.temporal is not None
    assert validated.temporal.year is None
    assert validated.temporal.month is None
    conflict = SemanticUnderstandingV342(
        goal="overtime",
        temporal_resolution_status="AMBIGUOUS",
        ambiguities=["unit missing"],
        unsupported_reasons=["clear unit is outside contract"],
    )
    conflict = resolve_structured_temporal(conflict)
    assert conflict.ambiguities == []
    assert conflict.unsupported_reasons
    assert conflict.temporal_resolution_status == "UNSUPPORTED"
    unsupported_unit = SemanticUnderstandingV342(
        goal="overtime",
        temporal=TemporalMeaningV342(reference_frame="CURRENT_DATE", relation="PREVIOUS", unit="WEEK"),
    )
    unsupported_unit = resolve_structured_temporal(unsupported_unit)
    assert unsupported_unit.temporal_resolution_status == "UNSUPPORTED"
    assert unsupported_unit.ambiguities == []
    assert "UNSUPPORTED_QUERY" in TEMPORAL_RESOLUTION_CONTRACT_V342


def prompt_for_case(case: dict[str, object], *, disciplined: bool) -> str:
    prompt = UNDERSTANDING_PROMPT_V342 if disciplined else phase34.UNDERSTANDING_PROMPT_V34
    context = case.get("context")
    context_text = f"\nStructured temporal context: {json.dumps(context, ensure_ascii=False)}" if context else ""
    return (
        f"{prompt}\n\nQuestion:\n{case['question']}"
        f"\nSource date: 2026-08-30\nTimezone: UTC{context_text}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 3.4.2 temporal-resolution spike.")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--condition", choices=("baseline", "disciplined"), default="disciplined")
    parser.parse_args()
    assert_phase342_contract()
    # The dedicated runner owns execution so this module remains reusable for
    # prompt construction and deterministic preflight checks.
    raise SystemExit(
        "Use semantic_understanding_phase342_runner.py for execution; "
        "no LLM call was made."
    )


if __name__ == "__main__":
    main()
