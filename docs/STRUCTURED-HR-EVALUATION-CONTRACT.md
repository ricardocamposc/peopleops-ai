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
