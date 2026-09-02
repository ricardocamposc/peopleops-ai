"""Phase 3.6 experimental Semantic Understanding comparison discipline.

This phase changes only the LLM instruction contract. It reuses the Phase 3.4.3
schema, the validated Phase 3.4.5 canonicalizer/compiler, and the evaluator v3.
No deterministic code reads the natural-language question.
"""
from __future__ import annotations

import semantic_understanding_phase343 as phase343

COMPARISON_DISCIPLINE_V36 = """
PHASE 3.6 — COMPARISON UNDERSTANDING DISCIPLINE

Treat comparison as its own semantic structure, not as a simple temporal query
with an extra comparison attached.

OUTPUT INVARIANTS FOR A RESOLVED COMPARISON
1. comparison MUST contain exactly two semantic operands: left and right.
2. top-level temporal MUST be null. The operands own all comparison temporal
   meaning. Do not duplicate comparison.left into top-level temporal.
3. The analytical measure, requested fields, breakdowns, calendar conditions,
   order, and limit remain top-level analytical intent and apply to the
   comparison as requested. Do not invent any of them.
4. A comparison operand contains temporal meaning only. Do not place grouping,
   measure, projection, or ordering inside an operand.
5. Do not convert a comparison into one simple temporal period.

ANCHOR DISCIPLINE
- CURRENT period versus PREVIOUS period of the same explicit unit: the previous
  operand is relative_to=SOURCE_DATE when both periods are defined from the
  source-date frame.
- An explicit period versus "the previous <unit>": the right operand is
  relative_to=LEFT_OPERAND. Example: January 2026 versus the previous month
  means January 2026 versus December 2025.
- Never use LEFT_OPERAND merely because a left operand exists. Use it only when
  the right expression is semantically relative to that operand.
- Never use SOURCE_DATE for a right operand whose meaning is explicitly
  relative to the left operand.
- STRUCTURED_CONTEXT is used only when structured context supplied the anchor.

ALIGNMENT DISCIPLINE
- SAME_PERIOD means comparing two complete periods as periods: current month vs
  previous month, January 2026 vs December 2025, current year vs previous year.
- SAME_MONTH means pairing the same month identities across different years,
  including explicit multi-month year-over-year comparisons.
- Do not choose SAME_MONTH merely because both operands use MONTH.

OPERATION DISCIPLINE
- SIDE_BY_SIDE is the default comparison operation.
- DELTA only when the request explicitly asks for a difference/change amount.
- PERCENT_CHANGE only when the request explicitly asks for percentage change.
- Do not infer DELTA or PERCENT_CHANGE from the verb "compare" alone.

MULTI-PERIOD DISCIPLINE
- Preserve all explicitly requested month identities. Do not collapse several
  named months into one month or into a full-year comparison.
- For the same set of months across years, each operand uses YEAR with the
  corresponding months=[...] and alignment=SAME_MONTH.

AMBIGUITY DISCIPLINE
- A generic period/prior period without an explicit unit or an unambiguous
  structured antecedent is ambiguous. Do not guess MONTH, YEAR, DAY, WEEK, or
  PAYROLL_PERIOD.
- When either comparison operand is unresolved, set the overall status to
  AMBIGUOUS, populate ambiguities, set comparison=null and temporal=null, and
  emit no executable semantic content.
- Unsupported and ambiguous are different. Missing granularity is AMBIGUOUS;
  a clear unit outside the contract is UNSUPPORTED.

MINIMAL-OPERATION DISCIPLINE
- A temporal/calendar filter never implies GROUP BY.
- "each Monday", "day 15", "first day of month", and "last day of month"
  describe calendar filtering unless grouping is explicitly requested.
- Do not add requested_fields, grouping, ordering, or measures beyond what the
  request semantically asks for.

SELF-CHECK BEFORE RETURNING A RESOLVED COMPARISON
- comparison is non-null;
- temporal is null;
- left and right preserve distinct temporal meanings;
- relative_to matches the semantic anchor;
- alignment matches period-vs-period or same-month-across-years semantics;
- operation is not stronger than explicitly requested;
- no inferred grouping or projection was added.
"""

UNDERSTANDING_PROMPT_V36 = (
    phase343.UNDERSTANDING_PROMPT_V343 + "\n" + COMPARISON_DISCIPLINE_V36
)


def assert_phase36_contract() -> None:
    phase343.assert_phase343_contract()
    contract = COMPARISON_DISCIPLINE_V36
    assert "top-level temporal MUST be null" in contract
    assert "relative_to=LEFT_OPERAND" in contract
    assert "relative_to=SOURCE_DATE" in contract
    assert "SAME_PERIOD" in contract
    assert "SAME_MONTH" in contract
    assert "SIDE_BY_SIDE" in contract
    assert "PERCENT_CHANGE" in contract
    assert "comparison=null" in contract
    assert "never implies GROUP BY" in contract


if __name__ == "__main__":
    assert_phase36_contract()
    print("SEMANTIC_UNDERSTANDING_PHASE36_SELF_TEST_OK")
