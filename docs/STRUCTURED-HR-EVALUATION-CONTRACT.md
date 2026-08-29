# Structured HR evaluation contract

This document records the contract corrections applied before the next
Structured HR baseline. It is diagnostic documentation; it is not a baseline
and it contains no observed results.

## Canonical ground truth

The current Reference MCP catalog exposes this provider-neutral capability
matrix:

| Capability | Entities | Operations | Sensitivity |
| --- | --- | --- | --- |
| workforce | employee, department, position | read, aggregate | confidential |
| employment | contract | read, aggregate | confidential |
| attendance | attendance, attendance_incident | read, aggregate | confidential |
| overtime | overtime | read, aggregate | confidential |
| time_off | vacation_balance, vacation_request, leave_request | read, aggregate | confidential |
| payroll | payroll_period, payroll, payroll_concept, payroll_item | read, aggregate | restricted |

The audit corrected contract-related expectations from `contracts` to
`employment`, overtime-only questions from `attendance` to `overtime`, and
non-qualified department dimensions to `department.name`. These changes are
ground-truth corrections derived from the catalog, not adaptations to model
output.

`expected_metric_functions` identifies the aggregate (`count`, `sum`, `avg`,
`min`, or `max`). `expected_metric_fields` identifies the provider-neutral
field reference used by that aggregate, and `expected_dimensions` contains
canonical field references such as `department.name`. Output aliases are not
part of ground truth because they are model-generated presentation labels.

The evaluation datasets were migrated from the ambiguous metric representation
where it was safe to do so. No observed output was added to either dataset.
Capability and entity identifiers remain provider-catalog identifiers and are
not inferred from natural-language wording.

## Evaluator contract

The evaluator now reports separately:

- plan generation;
- conceptual-query validity, based on provider evidence rather than a
  truthy plan object;
- workflow execution success;
- provider-query execution success;
- entity, metric-function, metric-field, and dimension coverage;
- answerability and abstention accuracy.

`abstention_accuracy` uses only cases with `expected_answerable == false`.
Correct abstentions therefore do not become infrastructure failures or enter a
positive-case denominator. Unsupported/negative cases without a provider
execution are `N/A` for provider execution success.

The evaluator preserves expected and observed values in separate sections of
each prediction. Diagnostics include the first detectable failure layer and
provider validation/execution status. Metrics whose ground truth cannot be
compared deterministically remain `N/A`; they are not converted to zero.

## Time-scope integrity

An incomplete `date_range`, `payroll_period`, or `period_comparison` is no
longer removed during normalization. The typed contract rejects it, allowing
structured feedback and bounded replanning instead of silently broadening the
query.

A complete `period_comparison` is a logical analysis composition. Before MCP
execution, PeopleOps expands it into independent provider-neutral queries for
the current and previous periods. The provider therefore receives one period
per query and cannot accidentally translate a comparison into an intersection
of both predicates. Physical SQL generation and execution remain exclusively
inside the MCP provider.

## Provider correction

Projection collision validation uses the same metric-label function as SQL
translation. This catches collisions between a model-selected alias and an
automatically generated label such as `count_id`.

## Evaluation status

The 32-case v2 dataset may be run as a diagnostic after these changes. The
holdout dataset is not executed or used for optimization in this remediation,
and no official structured baseline is published here.
## Evaluation trace and metric contract

The structured HR evaluator is an observation layer over the real PeopleOps → MCP → HRIS workflow. Ground-truth datasets contain expectations only; runtime observations are written to run artifacts.

## Evaluation-only observability

When `evaluation_structured_hr` is enabled, the API persists an `evaluation_trace` containing provider-neutral planning attempts, conceptual queries, provider validation decisions, provider execution outcomes, authorization decision, replan count, and final validation status. It contains no physical SQL, credentials, secrets, or chain-of-thought. The public response omits this trace unless evaluation mode is explicitly requested.

Provider validation and execution are separate metrics. `conceptual_query_validity` measures provider acceptance of a generated ConceptualQuery. `provider_query_execution_success_rate` includes only queries for which execution was actually attempted. A validation rejection, intentional abstention, or authorization denial before execution is not an execution failure.

## Time-scope contract

`expected_time_scope` is structured ground truth. Supported forms are `relative_window` (optionally with `days`), `explicit_period` with `value`, and `period_comparison` with `expected_query_count`. A period comparison is valid only when the logical comparison expands to independent conceptual queries with distinct scopes and independent provider executions. Internal query type names are not compared literally.

## Authorization and replanning

Cases may declare `evaluation_security.scopes`; the runner transmits these through the existing security header mechanism. Cases that test security may declare `expected_authorization: "denied"`. Authorization accuracy has its own denominator and does not contaminate planning, validation, or execution metrics.

Replanning is evaluated only from recorded operational evidence: an initially rejected provider validation, a new planning attempt, a new ConceptualQuery, and an accepted final validation. No textual answer is used to infer replanning.

## First failure layer

The evaluator reports the first observable divergence using the public categories `UNDERSTANDING_DEFECT`, `PEOPLEOPS_PLAN_DEFECT`, `CONCEPTUAL_CONTRACT_DEFECT`, `AUTHORIZATION_DECISION`, `MCP_VALIDATION_DEFECT`, `MCP_SQL_TRANSLATION_DEFECT`, `MCP_RELATIONSHIP_PATH_DEFECT`, `PROVIDER_EXECUTION_DEFECT`, `RESULT_VERIFICATION_DEFECT`, `SYNTHESIS_DEFECT`, `INFRASTRUCTURE_DEFECT`, and `EVALUATOR_DEFECT`. A failed workflow with an existing semantic request is not automatically classified as generic execution failure.

## Metric shape and denominators

Every Structured HR metric is an object with `value`, `successes` and `eligible_cases`. Fractional recall metrics additionally use `score_sum` because their per-case score is not binary. `N/A` is used when there are no eligible cases and is never converted to zero. `abstention_accuracy` uses only cases with `expected_answerable == false`; `answerability_accuracy` uses all applicable cases.

## Offline attribution and zero-row evidence

Offline re-evaluation consumes captured `predictions.jsonl` and `evidence.jsonl`
artifacts and never calls PeopleOps, OpenAI, MCP, or HRIS. Provider feedback
identifying an unknown field, entity, relationship, unqualified reference,
invalid aggregation/filter/time scope, or duplicate alias is attributed to the
submitted plan (`PEOPLEOPS_PLAN_DEFECT`) when the query contains that invalid
reference. `MCP_VALIDATION_DEFECT` is reserved for evidence explicitly
establishing that a catalog-valid conceptual query was rejected by the
provider.

Zero-row accuracy is determined from the provider execution trace: validation
accepted, execution succeeded, `row_count == 0`, and
`result_verification_status == ZERO_ROWS`. The final workflow status is not
required to be `completed`. If an authorization trace conflicts with a
restricted capability requirement, the historical case is not evaluable rather
than being converted into a grant or denial.
