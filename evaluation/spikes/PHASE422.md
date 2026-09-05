# Phase 4.2.2 — Tool-Assisted Query Programmer

Phase 4.2.2 extends the isolated Phase 4.2 experiment with a bounded internal
self-validation cycle for the Query Programmer. It does not access the HRIS,
execute a database query, or move tools to the MCP server. The Senior Reviewer
contract now also records whether material issues from a previous review were
resolved, partially resolved, unresolved, or no longer applicable.

## Flow

```text
Functional Analyst
  -> Query Programmer
      -> validate_python_syntax
      -> build_sqlalchemy_query
      -> compile_sqlalchemy_query
      -> structured diagnostics and bounded self-repair
  -> independent deterministic validator
  -> Senior Reviewer
  -> semantic repair when requested
```

The internal tools reuse the existing closed namespace, AST safety checks,
SQLAlchemy construction, and PostgreSQL compilation primitives. They execute
in strict order: syntax, build, then compile. A syntax failure skips build and
compile; a build failure skips compile. A successfully built SQLAlchemy
statement is passed directly to compilation and is not reconstructed. No
Python, SQLAlchemy, or SQL is executed by the LLM.

Internal self-repair is limited by `MAX_INTERNAL_SELF_REPAIR_ATTEMPTS` (two by
default). Its counter is separate from external technical repair and semantic
repair counters. The external validator always runs after the internal cycle;
the Senior Reviewer is still gated on that external validation result.

Every internal iteration is persisted with its candidate, generation type,
repair input, tool calls, tool results, validation status, errors, candidate
change status, and final-iteration marker. Identical candidates are recorded
as unchanged and never counted as successful repairs. The cycle is bounded and
never reaches the Senior Reviewer with an invalid query.

## Observability and metrics

Each Query Programmer event records the candidate and internal tool results in
the audit trail. Runner metrics distinguish:

- internal tool calls and validation attempts;
- internal self-repair attempts and successful repairs;
- candidate validity before external validation;
- external validator passes after internal validation;
- external technical repair attempts and success;
- Senior review and final semantic approval;
- candidates changed or unchanged;
- syntax/build short-circuits, compilation attempts, and avoided tool calls;
- previous Senior issues resolved or unresolved.

The Phase 4.2 dataset remains unchanged. The 36-case baseline is intentionally
not run as part of this phase preparation; the approved smoke set is P42-001
through P42-005.

## Validation record

Deterministic validation completed successfully:

- Phase 4.2 self-test: passed;
- Phase 4.2 workflow and tool tests: 14 passed;
- runner contract: passed;
- Ruff and `git diff --check`: passed.

The real five-case AGENT_TEAM smoke was run from scratch using the Poetry
backend environment and the repository root `.env`. The report is stored in
`evaluation/runs/direct-sqlalchemy-phase42-tool-assisted-smoke-corrected-20260905`.
It produced 3 Senior approvals, 3 technically valid final cases, 12 syntax
short-circuits, 3 compilation attempts, and avoided 24 downstream tool calls.
P42-003 ended as `CANNOT_IMPLEMENT` and P42-005 as
`TECHNICAL_VALIDATION_FAILED`; therefore the 36-case baseline remains deferred.
