# MCP Dynamic Query Compatibility

## Diagnostic scope

This note records the diagnostic comparison for the 32-case structured HR
regression. It is not a structured-analysis baseline and it does not alter
the ground-truth dataset.

The first live API run started in the `understanding` stage for every case
because the running container did not include the uncommitted PeopleOps
structured-analysis changes. It therefore could not be used to classify MCP
failures. The recorded `ConceptualQuery` plans from the previous diagnostic
run were replayed through the official MCP client against the live
Streamable HTTP server and the synthetic PostgreSQL source.

## Failure matrix

| Cases | Initial observation | Classification | Result |
| --- | --- | --- | --- |
| `hr-v2-002`, `hr-v2-021` | Valid queries executed and returned provider evidence | None | Preserved |
| `hr-v2-005`, `hr-v2-015`, `hr-v2-017`, `hr-v2-018`, `hr-v2-029` | Unqualified fields, plural/unknown entities, or an entity containing a value | `PEOPLEOPS_PLAN_DEFECT` | Not changed in MCP |
| `hr-v2-007` | Selected `department.id` was not included in `GROUP BY`; PostgreSQL rejected the generated SQL | `MCP_SQL_TRANSLATION_DEFECT` | Fixed generically |
| `hr-v2-008`, `hr-v2-009`, `hr-v2-032` | Valid conceptual aliases containing spaces were rejected as identifiers | `MCP_SQL_TRANSLATION_DEFECT` | Fixed generically |
| `hr-v2-007` | The same output alias appeared twice in the plan | `PEOPLEOPS_PLAN_DEFECT` / invalid projection shape | Provider now rejects duplicate labels before execution |
| `hr-v2-012` | `attendance_incident.worked_minutes` and `absence_minutes` do not exist in the catalog | `PEOPLEOPS_PLAN_DEFECT` | Not changed in MCP |

The provider replay after the fix executed the previously failing aggregate
shape (`hr-v2-007`) and the payroll shape (`hr-v2-032`) against PostgreSQL.
The latter correctly returned zero rows for its negative predicate with valid
provider evidence; zero rows are not treated as an execution failure.

## General fixes

- Grouped queries now include every selected non-metric field plus declared
  dimensions in `GROUP BY`.
- Model-provided output labels are safely quoted, including labels with spaces,
  without allowing them to become SQL syntax.
- Metric labels used by `order_by` are resolved consistently whether or not an
  explicit alias is present.
- Duplicate projection labels are rejected during conceptual validation to
  avoid ambiguous result columns.

No PeopleOps physical SQL, HRIS credentials, direct HRIS access, MCP transport,
Policy RAG logic, or evaluation ground truth was changed.

## Verification

- Reference MCP tests: 27 passed, 6 PostgreSQL integration tests skipped when
  the test database URL is not configured.
- PeopleOps tests: 92 passed.
- Full test suite: two consecutive runs passed.
- Lint: passed for API, MCP server, and frontend.
- MCP regression: all applicable metrics remained `1.0`; schema independence
  remains `N/A` because no second provider was deployed.
- Streamable HTTP replay: corrected aggregate and payroll queries executed
  successfully against the live synthetic PostgreSQL source.

## Explicit contract gap

`period_comparison` is represented by the shared conceptual contract, but a
single provider query cannot express a meaningful period-over-period result by
combining two independent period predicates with `AND`. This remains a
contract/workflow concern for the structured-analysis alignment task; this
remediation does not silently reinterpret or drop that comparison.
