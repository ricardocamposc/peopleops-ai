# Phase 4.3 — Agentic Query Programmer with Tool Calling

Phase 4.3 replaces the Phase 4.2.2 application-triggered generate/validate/repair loop with a genuine LangChain tool-calling interaction for the Query Programmer.

The experiment preserves the validated outer architecture:

Functional Analyst → Query Programmer → independent deterministic validator → Senior Reviewer → semantic repair when required.

Only the Query Programmer interaction changes.

## Why this phase exists

Phase 4.2.2 proved that deterministic syntax/build/compile validation was reliable, but its self-repair loop was weak: the application automatically validated a completed structured response and then invoked the model again with diagnostics. In the smoke evidence the model repeatedly reproduced SQL-like pseudocode and could incorrectly reclassify a technical generation failure as `CANNOT_IMPLEMENT`.

Phase 4.3 tests a different mechanism rather than adding benchmark-specific prompt rules.

## Query Programmer interaction

The model is bound to two tools:

- `validate_sqlalchemy_candidate(candidate)`
- `SubmitQueryProgrammerResult(...)`

For an implementable query, the model must validate a candidate through the first tool, receive the deterministic result in the conversation, repair when necessary, and only then submit the final structured result.

A `QUERY` submission is accepted only when it contains the exact candidate that passed validation in a prior tool round. A validation and final submission emitted speculatively in the same model message are not accepted as evidence that the model inspected the tool result.

`CANNOT_IMPLEMENT` is reserved for genuine data-model capability gaps. After a technical validation failure, the model cannot use `CANNOT_IMPLEMENT` merely because it failed to repair its Python/SQLAlchemy implementation, unless the Functional Requirement already records an unsupported requirement.

## Deterministic validation tool

`validate_sqlalchemy_candidate` remains ordinary application code, not an LLM agent. Internally it executes the existing short-circuit pipeline:

syntax → build → compile

- syntax failure skips build and compile;
- build failure skips compile;
- a built SQLAlchemy statement is reused for compilation;
- no database query is executed.

The independent external validator still runs after the Query Programmer submits a candidate. The Senior Reviewer remains gated behind successful external validation.

## Bounded behavior

The agent conversation is bounded by:

- `MAX_CANDIDATE_VALIDATIONS`: three candidate validations per outer Query Programmer attempt;
- `MAX_AGENT_TOOL_ROUNDS`: eight model tool rounds per outer attempt;
- existing outer technical repair limit from Phase 4.2;
- existing semantic revision limit from Phase 4.2.

If the agent cannot complete a validated structured submission within the tool budget, the runtime emits an intentionally invalid fallback candidate only so the mandatory external validator can independently confirm the technical failure. The outer workflow ultimately terminates as `TECHNICAL_GENERATION_FAILED`, not `CANNOT_IMPLEMENT`.

## Observability

The Phase 4.3 audit trail records:

- every model-initiated validation tool call;
- candidate text;
- candidate changes;
- deterministic tool diagnostics;
- final submission attempts;
- rejected submissions and reasons;
- tool rounds;
- validation attempts;
- self-repair attempts/success;
- external validation;
- Senior reviews.

The runner adds Phase 4.3-specific metrics for tool rounds, submission attempts/rejections, self-repair and technical generation failure while retaining the Phase 4.2 metrics for comparison.

Candidate metrics are derived only from `VALIDATION_TOOL_CALL` events. They intentionally distinguish generated validation requests from deterministic validator executions because the model can continue requesting validation after the bounded validation budget has been exhausted:

- `candidate_validation_requests` / `candidates_generated`: every model validation-tool request carrying a candidate;
- `candidates_initial`: the first candidate in each Query Programmer invocation;
- `candidates_changed`: a validation request whose candidate differs from the previous request in the same invocation;
- `candidates_unchanged`: a validation request whose candidate is identical to the previous request in the same invocation;
- `candidate_validations_executed`: requests that actually reached deterministic syntax/build/compile validation;
- `candidate_validation_budget_rejections`: requests rejected because the per-invocation validation budget was already exhausted.

Therefore `candidates_initial + candidates_changed + candidates_unchanged = candidates_generated`. `candidate_validations_executed` may be lower than `candidates_generated` when the model keeps requesting validation after the deterministic budget is exhausted.

Tool rounds represent actual model turns. They are not the number of individual tool/interactions: one model turn may emit more than one tool call.

## Architectural boundary

This remains an evaluation spike. The SQLAlchemy catalog is still local to the experiment and PostgreSQL compilation is still performed locally.

The final PeopleOps architecture must preserve the PRD boundary: provider-specific schema discovery, mapping, physical compilation/preparation, and HRIS execution belong behind MCP. Phase 4.3 evaluates the agent interaction pattern before moving provider-aware capabilities to the Reference MCP Server.

## Files

- `evaluation/spikes/direct_sqlalchemy_phase43.py`
- `evaluation/spikes/direct_sqlalchemy_phase43_runner.py`
- `apps/peopleops-api/tests/test_phase43_tool_calling.py`
- `evaluation/spikes/PHASE43.md`

The Phase 4.2 dataset is reused unchanged so the new interaction can be compared against the previous experiments.
