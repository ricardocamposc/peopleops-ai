"""Phase 3.4.1 — temporal semantic discipline over the frozen Phase 3.4 pipeline.

This experiment does not change compiler, canonicalizer, capability closure,
normalization, entity derivation, or provider boundaries. It adds only focused
Semantic Understanding guidance for temporal vocabulary, antecedent resolution,
and abstention, then runs through the existing deterministic Phase 3.2 pipeline.

Important architectural invariant already present in Phase 3.1:
- ambiguities or unsupported_reasons make the canonical understanding
  non-executable by removing measure, temporal, breakdowns, calendar conditions,
  order, requested fields, and limit.

No MCP, SQL, provider execution, or executable Eloquent.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import semantic_understanding_phase31 as phase31
import semantic_understanding_phase32 as phase32
import semantic_understanding_phase34 as phase34
import semantic_understanding_phase3 as phase3

ROOT = Path(__file__).resolve().parents[2]

TEMPORAL_SEMANTIC_DISCIPLINE_V341 = """
PHASE 3.4.1 — TEMPORAL SEMANTIC DISCIPLINE

GENERAL PRINCIPLE
A glossary explains terminology; it MUST NOT supply semantic information that is
missing from the request. Interpret what is established; do not guess what is
merely common in ERP, HR, payroll, or accounting.

EXPLICIT TEMPORAL MEANING
- 'current month' means CURRENT_MONTH + EXACT + MONTH.
- 'previous month' means CURRENT_MONTH + PREVIOUS + MONTH.
- 'current calendar year' means the current calendar-year concept.
- 'previous calendar year' means the calendar year immediately preceding the
  current calendar year when that concept is supported by the contract.
- Explicit values such as January 2026 remain EXPLICIT + EXACT and retain the
  explicit year/month needed to identify that period.

GENERIC PERIOD IS NOT A MONTH
- 'period', 'previous period', 'prior period', 'período anterior', and equivalent
  generic expressions do NOT establish MONTH, YEAR, WEEK, payroll-period, or
  accounting-period granularity by themselves.
- Do not convert a generic period into a month merely because monthly periods are
  common in enterprise systems.
- Accounting, payroll, fiscal, or exercise terminology does not silently define a
  calendar granularity unless the current semantic contract or explicit request
  establishes it.

ANTECEDENT RESOLUTION
A missing temporal unit may be inherited only from an unambiguous antecedent in
context. Resolve an antecedent only when the referenced temporal concept is clear.
For example, 'compare the current month with the previous month' is explicitly
monthly. A generic 'previous period' without a clearly established unit remains
ambiguous.

AMBIGUITY DISCIPLINE
If two or more materially different temporal interpretations remain plausible,
record an ambiguity instead of selecting the most common interpretation.
Do not use business convention as a tie-breaker for missing meaning.

SYMBOLIC RELATIVE MEANING
For relative time, express the semantic relationship and let deterministic
compilation/normalization calculate concrete dates.
- Do not add year/month/months/start_date/end_date merely because source_current_date
  makes those values calculable.
- The source date anchors relative meaning; it does not make Semantic Understanding
  responsible for date arithmetic.
Interpret; do not calculate.

NON-EXECUTABLE STATES
When ambiguities or unsupported_reasons are present, the existing deterministic
canonicalizer will remove executable query content. Do not rely on speculative
measure, temporal, breakdown, calendar, order, requested-field, or limit content
for answering the request.
"""

UNDERSTANDING_PROMPT_V341 = (
    phase34.UNDERSTANDING_PROMPT_V34
    + "\n"
    + TEMPORAL_SEMANTIC_DISCIPLINE_V341
)


def assert_non_executable_canonicalization() -> None:
    """Prove the existing deterministic abstention invariant before live evaluation."""
    ambiguous = phase3.SemanticUnderstanding(
        goal="overtime",
        requested_fields=["overtime.work_date"],
        measure=phase3.SemanticMeasure(
            field="overtime.approved_minutes",
            aggregation="SUM",
        ),
        temporal=phase3.TemporalMeaning(
            reference_frame="CURRENT_MONTH",
            relation="PREVIOUS",
            unit="MONTH",
        ),
        breakdowns=[
            phase3.BreakdownMeaning(
                kind="TIME_GRAIN",
                field="overtime.work_date",
                grain="YEAR_MONTH",
            )
        ],
        calendar_conditions=[
            phase3.CalendarMeaning(
                kind="WEEKDAY",
                field="overtime.work_date",
                value="MONDAY",
            )
        ],
        order_by=[],
        limit=5,
        ambiguities=["Temporal granularity is not established."],
    )
    canonical = phase31.canonicalize_understanding(ambiguous)
    assert canonical.ambiguities
    assert canonical.requested_fields == []
    assert canonical.measure is None
    assert canonical.temporal is None
    assert canonical.breakdowns == []
    assert canonical.calendar_conditions == []
    assert canonical.order_by == []
    assert canonical.limit is None

    unsupported = ambiguous.model_copy(deep=True)
    unsupported.ambiguities = []
    unsupported.unsupported_reasons = ["Temporal concept is outside the current contract."]
    canonical_unsupported = phase31.canonicalize_understanding(unsupported)
    assert canonical_unsupported.unsupported_reasons
    assert canonical_unsupported.requested_fields == []
    assert canonical_unsupported.measure is None
    assert canonical_unsupported.temporal is None
    assert canonical_unsupported.breakdowns == []
    assert canonical_unsupported.calendar_conditions == []
    assert canonical_unsupported.order_by == []
    assert canonical_unsupported.limit is None

    compiled = phase3.compile_understanding(canonical)
    assert compiled.ambiguities
    assert compiled.result_fields == []
    assert compiled.measures == []
    assert compiled.time_scope is None
    assert compiled.group_by == []


def run(case_path: Path, output_dir: Path, model: str) -> None:
    """Run the frozen Phase 3.2 pipeline with only the V3.4.1 understanding prompt."""
    assert_non_executable_canonicalization()
    original_prompt = phase32.UNDERSTANDING_PROMPT_V32
    try:
        phase32.UNDERSTANDING_PROMPT_V32 = UNDERSTANDING_PROMPT_V341
        phase32.run(case_path, output_dir, model)
    finally:
        phase32.UNDERSTANDING_PROMPT_V32 = original_prompt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    run(Path(args.cases), Path(args.output_dir), args.model)


if __name__ == "__main__":
    main()
