# Phase 4.2 — Agent Team Query Retrieval Baseline

Phase 4.2 is the isolated evaluation laboratory for the structured-data agent team used by PeopleOps AI.

It is intentionally independent from Phase 4.1 / 4.1.2 implementation code and owns its evaluation dataset, contracts, LangGraph routing, deterministic validator, prompts, audit artifacts, and metrics.

## Purpose

The phase evaluates the workflow:

```text
User request
  -> Functional Analyst
  -> Functional Requirement
  -> Query Programmer
  -> Deterministic Validator
      -> technical repair when invalid
      -> Senior Query Reviewer only when technically valid
          -> semantic repair when required
```

Phase 4.2 does not execute HRIS data and does not replace the MCP architecture. The local SQLAlchemy model is an evaluation fixture used to measure query-programming behavior.

## Architectural invariants

1. `NEEDS_CLARIFICATION` stops before Query Programmer.
2. Query Programmer `NEEDS_INFO` and `CANNOT_IMPLEMENT` stop before deterministic query validation.
3. A technically invalid query never reaches Senior Query Reviewer.
4. Technical repair and semantic repair have independent counters and limits.
5. Every semantic repair is revalidated deterministically before Senior re-review.
6. Senior Query Reviewer reviews correctness, not implementation preference.
7. `data_model` and temporal execution context appear once in each system prompt and are not duplicated in the human artifact message.
8. The external deterministic validator remains authoritative even when a future Query Programmer gains self-validation tools.
9. Phase 4.2 does not execute database queries.
10. Physical/provider-specific validation and execution remain future MCP Server responsibilities.

## Files

```text
evaluation/spikes/direct_sqlalchemy_phase42.py
evaluation/spikes/direct_sqlalchemy_phase42_runner.py
evaluation/spikes/direct_sqlalchemy_phase42_cases.jsonl
apps/peopleops-api/src/peopleops_api/resources/prompts/phase42/
apps/peopleops-api/tests/test_phase42_workflow.py
```

## Dataset

`direct_sqlalchemy_phase42_cases.jsonl` is the Phase 4.2 owned dataset.

The first version contains Spanish, English, and Portuguese cases covering:

- projection and listing;
- filters;
- temporal interpretation;
- aggregation;
- grouping and ordering;
- comparisons;
- Employee / Department / Overtime / Attendance relationships;
- genuine ambiguity;
- unsupported capabilities such as payroll, contracts, vacation, and policy data that are intentionally absent from the Phase 4.2 fixture model.

The dataset records semantic expectations instead of an exact SQLAlchemy string because several implementations can be equally correct.

## Runner

Example:

```bash
cd apps/peopleops-api
PYTHONPATH=src poetry run python ../../evaluation/spikes/direct_sqlalchemy_phase42_runner.py \
  --mode team \
  --output-dir ../../evaluation/runs/direct-sqlalchemy-phase42-baseline
```

`--cases` defaults to the dedicated Phase 4.2 dataset.

Useful modes:

- `analyst`: Functional Analyst only;
- `developer`: Functional Analyst + Query Programmer + deterministic validation, no Senior Reviewer;
- `team`: full Phase 4.2 agent team;
- `both`: developer baseline plus full team.

The runner also supports resuming from an analyst-only artifact so the Query Programmer can be evaluated without paying for or varying Functional Analyst calls again.

## Metrics

Phase 4.2 separates different quality layers rather than combining them into a single score:

- query generation rate;
- first-pass technical validity;
- technical repair attempts and success;
- Senior review coverage;
- Senior first-pass approval;
- semantic revision requests;
- semantic repair success;
- final technical validity;
- final semantic approval;
- `NEEDS_CLARIFICATION`;
- `NEEDS_INFO`;
- `CANNOT_IMPLEMENT`;
- technical validation exhaustion;
- semantic revision exhaustion;
- normalized validation error codes.

The prior `team_approval_uplift_vs_first_pass` metric is intentionally removed because it compared semantic approval with technical validity, which are different dimensions.

## Reproducibility

Every run manifest records:

- runner version;
- dataset version and SHA-256;
- selected cases;
- Git commit SHA when available;
- model by role;
- prompt SHA-256 by role;
- source date and timezone;
- LLM retry configuration;
- technical and semantic repair limits;
- whether MCP or database execution was enabled.

This allows a run to be tied to a specific code/dataset/prompt configuration.

## Next experiment — Tool-Assisted Query Programmer

The next phase should add an internal Query Programmer subgraph with controlled deterministic tools, initially:

```text
validate_python_syntax
build_sqlalchemy_query
compile_sqlalchemy_query
```

The LLM may decide when to call these tools, but application code executes them. After the Query Programmer finishes its internal self-validation loop, the independent platform validator must still run.

The same Phase 4.2 dataset should be used for an A/B comparison:

```text
Baseline Query Programmer
vs
Tool-Assisted Query Programmer
```

Key additional metrics will be tool calls per case, self-repair rate, externally detected failures after agent self-validation, latency, and token/call cost.

## MCP boundary

The SQLAlchemy fixture is not the final PeopleOps integration contract.

In the product architecture:

```text
PeopleOps
  -> HRDataGateway
  -> MCP Client
  -> MCP Server
  -> HRIS / ERP
```

PeopleOps may validate its own structural artifact, but provider-specific model discovery, relationship discovery, physical mapping, provider validation, translation/compilation, read-only execution, evidence, and normalized provider errors belong behind the MCP boundary.

The future tool-assisted Query Programmer experiment must preserve that separation so the spike can evolve toward schema independence rather than becoming direct HRIS access code.
