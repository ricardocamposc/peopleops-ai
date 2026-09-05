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

## Tool-call protocol integrity

One assistant message may contain several tool calls. OpenAI requires every `tool_call_id` emitted by that assistant message to receive a corresponding tool response before the conversation can continue.

Phase 4.3 therefore processes the complete set of tool calls in the current model round before returning from the Query Programmer runtime. Successful submission and validation-budget early termination are deferred until every tool call from that `AIMessage` has received its matching `ToolMessage`.

This matters when the model emits several validation calls in one round. The first three may consume the deterministic validation budget and any additional validation call in the same already-emitted assistant message may receive a `TOOL_BUDGET` response. That same-round response is intentional protocol completion; it does not trigger another model round. The runtime then performs the pending early termination.

The same rule applies when an accepted final submission shares a model response with another tool call: all calls are answered before the accepted result is returned.

## Deterministic validation tool

`validate_sqlalchemy_candidate` remains ordinary application code, not an LLM agent. Internally it executes the existing short-circuit pipeline:

syntax → build → compile

- syntax failure skips build and compile;
- build failure skips compile;
- a built SQLAlchemy statement is reused for compilation;
- no database query is executed.

The independent external validator still runs after the Query Programmer submits a candidate. The Senior Reviewer remains gated behind successful external validation.

## Bounded behavior and early termination

The agent conversation is bounded by:

- `MAX_CANDIDATE_VALIDATIONS`: three candidate validations per outer Query Programmer attempt;
- `MAX_AGENT_TOOL_ROUNDS`: eight model tool rounds per outer attempt;
- existing outer technical repair limit from Phase 4.2;
- existing semantic revision limit from Phase 4.2.

The runtime stops a Query Programmer invocation when all three deterministic candidate validations have been consumed, the most recent validation failed, and no previously validated candidate exists. Continuing model rounds after that point cannot produce an admissible `QUERY`, because no further candidate can pass the mandatory validation gate.

Early termination is evaluated only after all tool calls already emitted in the current assistant message have received their matching tool responses. This preserves the OpenAI tool-calling protocol while still preventing any additional model round after the validation budget is exhausted.

The early stop is recorded as:

`VALIDATION_BUDGET_EXHAUSTED_WITHOUT_VALID_CANDIDATE`

If the general eight-round interaction budget is exhausted for another reason, the termination reason is:

`AGENT_TOOL_ROUND_BUDGET_EXHAUSTED`

The intentionally invalid fallback candidate still exists only so the mandatory external validator can independently confirm the technical failure. The outer workflow ultimately terminates as `TECHNICAL_GENERATION_FAILED`, not `CANNOT_IMPLEMENT`.

## OpenAI transport retries

Phase 4.3 configures the LangChain/OpenAI clients with bounded transport retries. The default is six retries and can be changed through:

`PHASE43_OPENAI_MAX_RETRIES`

This retry policy applies to transient API failures such as rate limits at the individual model-call level. It does not change prompts, model semantics, tool budgets, or the workflow contract.

## Resumable evaluation runner

The Phase 4.3 runner is designed so a long baseline does not lose all completed work after a transient failure.

The runner now:

- writes `manifest.json` before the first case;
- appends each completed case immediately to `raw_responses.jsonl`;
- refreshes `metrics.json` and progress metadata after every completed case;
- marks interrupted runs as `INTERRUPTED` and preserves completed rows;
- supports `--resume`, which skips case IDs already checkpointed;
- validates dataset hash, model configuration, and selected case IDs before resuming;
- applies an optional delay between cases to reduce sustained TPM pressure.

The default inter-case delay is five seconds and can be configured through:

`PHASE43_INTER_CASE_DELAY_SECONDS`

or the CLI option:

`--inter-case-delay-seconds`

If a model call still fails after transport retries, the current incomplete case has no checkpoint row and may be retried on resume; already completed cases are never rerun.

## Observability

The Phase 4.3 audit trail records:

- every model-initiated validation tool call;
- candidate text;
- candidate changes;
- deterministic tool diagnostics;
- final submission attempts;
- rejected submissions and reasons;
- actual model tool rounds;
- validation attempts;
- self-repair attempts/success;
- termination reason;
- external validation;
- Senior reviews.

The runner adds Phase 4.3-specific metrics for tool rounds, submission attempts/rejections, self-repair and technical generation failure while retaining the Phase 4.2 metrics for comparison.

Candidate metrics are derived only from `VALIDATION_TOOL_CALL` events:

- `candidate_validation_requests` / `candidates_generated`: every model validation-tool request carrying a candidate;
- `candidates_initial`: the first candidate in each Query Programmer invocation;
- `candidates_changed`: a validation request whose candidate differs from the previous request in the same invocation;
- `candidates_unchanged`: a validation request whose candidate is identical to the previous request in the same invocation;
- `candidate_validations_executed`: requests that actually reached deterministic syntax/build/compile validation;
- `candidate_validation_budget_rejections`: requests rejected because the per-invocation validation budget was already exhausted.

Therefore:

`candidates_initial + candidates_changed + candidates_unchanged = candidates_generated`

After the early-termination correction, budget-rejected validation requests should not cause additional model rounds in the no-valid-candidate path. A budget rejection can still occur for an additional validation call that was already emitted in the same `AIMessage` that exhausted the budget; this is required to answer every tool call and preserve protocol validity.

Tool rounds represent actual model turns. They are not the number of individual tool/interactions: one model turn may emit more than one tool call.

## Context and token usage

Within one Query Programmer invocation, tool calling is conversational: the model receives the prior `AIMessage` and `ToolMessage` history so it can inspect deterministic diagnostics and repair its candidate. That history grows during the invocation and therefore increases token usage in later rounds.

The application audit trail and LangGraph state remain separate from the model context. The current Phase 4.3 baseline deliberately keeps the existing conversation semantics so the early-termination and runner-resilience changes do not alter the model's reasoning inputs.

Context compaction or a rolling repair window is a possible later optimization, but it is intentionally deferred until a clean baseline establishes whether it is needed. Persisting full audit history does not imply that a future production implementation must resend all of it to the LLM.

## Architectural boundary

This remains an evaluation spike. The SQLAlchemy catalog is still local to the experiment and PostgreSQL compilation is still performed locally.

The final PeopleOps architecture must preserve the PRD boundary: provider-specific schema discovery, mapping, physical compilation/preparation, and HRIS execution belong behind MCP. Phase 4.3 evaluates the agent interaction pattern before moving provider-aware capabilities to the Reference MCP Server.

## Files

- `evaluation/spikes/direct_sqlalchemy_phase43.py`
- `evaluation/spikes/direct_sqlalchemy_phase43_runner.py`
- `apps/peopleops-api/tests/test_phase43_tool_calling.py`
- `evaluation/spikes/PHASE43.md`

The Phase 4.2 dataset is reused unchanged so the new interaction can be compared against the previous experiments.
