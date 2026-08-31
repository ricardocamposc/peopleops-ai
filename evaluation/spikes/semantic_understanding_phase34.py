"""Phase 3.4 — focused semantic-discipline remediation over Phase 3.2.

This experiment changes only Semantic Understanding guidance/contract plus the
provider-neutral FIRST_DAY_OF_MONTH semantic primitive added to Phase 3.
Deterministic canonicalization, capability closure, compiler architecture,
normalization, entity derivation, and Eloquent-like inspection remain unchanged.

Official calendar decision for this phase:
- FIRST_DAY_OF_MONTH: supported semantic concept; deterministically compiles to
  DAY_OF_MONTH = 1 in the existing provider-neutral Query Intent.
- FIRST_DAY_OF_WEEK: understood but unsupported until an explicit week-start
  convention/calendar context exists. Never assume Monday or Sunday.

No MCP, SQL, provider execution, or executable Eloquent.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import semantic_understanding_phase32 as phase32

ROOT = Path(__file__).resolve().parents[2]

SEMANTIC_CAPABILITY_CONTRACT_V34 = """
SEMANTIC CAPABILITY CONTRACT
The current semantic contract supports:
- Temporal units: DAY, MONTH, YEAR.
- Explicit containing periods: explicit date range, explicit month, explicit year.
- Relative meanings already defined by the Semantic Understanding schema for current month,
  previous month, last N months, current-year-to-date, and last N years through today.
- Calendar conditions: WEEKDAY, DAY_OF_MONTH, FIRST_DAY_OF_MONTH, LAST_DAY_OF_MONTH.
- Time breakdowns: DAY, MONTH, YEAR, YEAR_MONTH.
- Field breakdowns when the requested conceptual field exists in the scoped catalog.

Contract decisions:
- FIRST_DAY_OF_MONTH is SUPPORTED. Represent it as calendar kind FIRST_DAY_OF_MONTH.
  Do not rewrite it as a temporal period and do not add grouping unless grouping is requested.
- FIRST_DAY_OF_WEEK is UNDERSTOOD BUT UNSUPPORTED because this contract has no week-start
  convention. Do not assume Monday, Sunday, locale, ISO week, or business-calendar semantics.
- A request can be semantically clear yet unsupported. Unsupported is not ambiguity.
"""

SEMANTIC_DISCIPLINE_V34 = """
PHASE 3.4 — EXACTLY THREE SEMANTIC RULES

RULE 1 — MINIMAL OPERATIONS
Represent only operations explicitly requested or strictly necessary to satisfy the request.
- A FILTER does not imply GROUP BY.
- A CALENDAR CONDITION does not imply GROUP BY.
- ORDER BY does not imply GROUP BY.
- A MEASURE does not imply requested_fields.
- A filter/group/order/time field does not imply requested_fields.
- Words such as 'each', 'every', 'cada', or recurrence language do not by themselves request grouping.
- If the user explicitly requests grouping/breakdown, represent exactly that grouping.
- If the user explicitly says not to group, breakdowns MUST be empty.
Do not add a helpful/default grouping, ordering, or projection that the user did not request.

RULE 2 — CONTAINING TIME + CALENDAR CONDITION COMPOSE INDEPENDENTLY
The containing temporal domain answers WHEN records are eligible. Calendar conditions answer WHICH
calendar positions inside that domain are eligible. Preserve both independently.
Examples of the semantic rule, not case-specific mappings:
- 'day 15 ... during 2026' => containing temporal = EXPLICIT EXACT YEAR 2026; calendar = DAY_OF_MONTH 15.
- 'last day ... during 2026' => containing temporal = EXPLICIT EXACT YEAR 2026; calendar = LAST_DAY_OF_MONTH.
- 'first day of each month ... during 2026' => containing temporal = EXPLICIT EXACT YEAR 2026;
  calendar = FIRST_DAY_OF_MONTH.
Never transform a recurring calendar condition into LAST_N months, an enumerated month list, or a
replacement temporal scope. Never discard an explicitly stated containing year/month/range because a
calendar condition is present.

RULE 3 — ANSWERABILITY DISCIPLINE
Classify in this conceptual order:
1. If material meaning is unresolved, use ambiguities => NEEDS_CLARIFICATION. Do not guess.
2. If meaning is sufficiently resolved but the Semantic Capability Contract cannot represent it, use
   unsupported_reasons => UNSUPPORTED_QUERY.
3. Only if meaning is resolved AND supported should executable semantic content remain.
Examples of the distinction:
- 'previous period' with no established unit: ambiguous => NEEDS_CLARIFICATION.
- 'previous month': resolved and supported => executable.
- 'first day of the week': resolved concept but unsupported without week-start convention => UNSUPPORTED_QUERY.
When ambiguities or unsupported_reasons are present, do not retain measure, temporal, breakdown,
calendar, order, requested fields, or limit as executable query content.
"""

UNDERSTANDING_PROMPT_V34 = (
    phase32.UNDERSTANDING_PROMPT_V32
    + "\n"
    + SEMANTIC_CAPABILITY_CONTRACT_V34
    + "\n"
    + SEMANTIC_DISCIPLINE_V34
)


def run(case_path: Path, output_dir: Path, model: str) -> None:
    """Reuse the frozen Phase 3.2 instrumentation with only the V3.4 understanding prompt."""
    original_prompt = phase32.UNDERSTANDING_PROMPT_V32
    try:
        phase32.UNDERSTANDING_PROMPT_V32 = UNDERSTANDING_PROMPT_V34
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
