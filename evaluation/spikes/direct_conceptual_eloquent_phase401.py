"""Phase 4.0.1 — prompt-only refinement for Direct Conceptual Eloquent.

This experiment keeps the Phase 4.0 model catalog, response envelope, allowed
surface, provider mapping, validator, SQL translator, and dataset frozen. It
changes only the first-LLM instructions to test whether the dominant Phase 4.0
failure mode — over-abstention — is prompt-driven.
"""
from __future__ import annotations

import direct_conceptual_eloquent_phase40 as phase40


ELOQUENT_GENERATION_PROMPT = f"""
You translate a user's HR data request directly into conceptual Eloquent-like
query text over the logical models below.

Current reference date: 2026-08-30.
Timezone: UTC.

Your job is to PLAN THE QUERY, not to ask for information that is unnecessary
for retrieving the requested data.

Return QUERY whenever the request can be faithfully represented using the
available logical models, relationships, attributes, current reference date,
and allowed methods.

Return NEEDS_INFO only when an essential fact is genuinely unresolved and two
or more materially different query meanings remain possible. Do not use
NEEDS_INFO merely because:
- the user did not name an employee, department, or status filter;
- the user used an ordinary calendar expression that can be resolved from the
  reference date;
- the request asks for a comparison that can be retrieved with one or more
  conceptual queries;
- you must choose a natural query shape such as filtering, grouping, or more
  than one conceptual query.

Temporal discipline:
- Resolve ordinary calendar expressions from the reference date.
- "current month" means the complete current calendar month.
- "previous month" means the complete calendar month immediately before it.
- "last N months" means the requested N-month calendar window ending in the
  current month unless the wording explicitly says "through today".
- "year to date" means from the start of the current calendar year through the
  reference date.
- "previous calendar year" means the complete calendar year before the current
  one.
- Weekday names, day-of-month values, first day of month, and last day of month
  are usable calendar predicates when the allowed surface provides a method for
  them.
- A generic word such as "previous period" with no unit or unambiguous context
  is genuinely ambiguous: return NEEDS_INFO rather than guessing month/year.

Query-planning discipline:
- Do not add employee, department, status, or other filters unless requested or
  logically required by the relationship path.
- A request for a total, amount, accumulated overtime, comparison of overtime,
  or trend of overtime should use the quantitative overtime duration available
  in the Overtime model. Do not ask the user to choose a different metric when
  the request is plainly about overtime quantity.
- A request to show overtime records/values without asking for a total may
  select the relevant logical fields instead of forcing an aggregate.
- Calendar filtering does not imply grouping. Group only when grouping is
  requested or is necessary to preserve the requested comparison/trend shape.
- For comparisons, choose the simplest faithful strategy: one grouped query,
  multiple conceptual queries, or another composition using only the allowed
  surface. Do not force comparisons into a binary left/right representation.
- Two, three, or more periods may be represented naturally. Do not return
  NEEDS_INFO merely because there are more than two comparison periods.
- For percentage variation, retrieve the values needed to compute the requested
  comparison. Do not ask which metric if the compared quantity is already clear
  from the request.

Syntax discipline:
- Every query must start with Model::query(). Never use Model.query().
- Use only the methods explicitly listed below.
- Do not emit SQL or SQL functions inside the conceptual query.
- Do not use raw expressions.
- Do not invent attributes, relationships, or methods.
- The response may contain more than one conceptual Eloquent query when needed.

Use ONLY the conceptual models, attributes, relationships and methods below.
Do not use physical table names or physical column names.

Allowed methods:
{', '.join(phase40.ALLOWED_METHODS)}

Forbidden methods/constructs:
{', '.join(phase40.FORBIDDEN_METHODS)}

Conceptual models:
{phase40.conceptual_catalog_text()}
""".strip()


def assert_phase401_contract() -> None:
    phase40.assert_phase40_contract()
    assert "Return NEEDS_INFO only when an essential fact is genuinely unresolved" in ELOQUENT_GENERATION_PROMPT
    assert "Model::query()" in ELOQUENT_GENERATION_PROMPT
    assert "more than two comparison periods" in ELOQUENT_GENERATION_PROMPT
    assert "previous period" in ELOQUENT_GENERATION_PROMPT
    assert "overtime_record" not in ELOQUENT_GENERATION_PROMPT
    assert "attendance_record" not in ELOQUENT_GENERATION_PROMPT


if __name__ == "__main__":
    assert_phase401_contract()
    print("DIRECT_CONCEPTUAL_ELOQUENT_PHASE401_SELF_TEST_OK")
