# Phase 4.4 — Query Programmer and Conceptual Senior Reviewer

Phase 4.4 is an experimental correction of the Query Programmer architecture.
It does not modify Phase 4.2 or Phase 4.3.

## Objective

This phase contains two explicitly separated experiments:

- `QUERY_PROGRAMMER_SUBGRAPH_ONLY` and `SQLALCHEMY_AGENT_TEAM` preserve the
  earlier SQLAlchemy tool-calling experiment for comparison.
- `AGENT_TEAM` is the production-oriented path. It uses the same provider-
  neutral `ConceptualQuery` contract and semantic catalog consumed by
  PeopleOps/MCP, then sends only MCP-compatible validation to the Senior
  Reviewer.

The production-oriented path evaluates:

1. a Query Programmer proposing a `ConceptualQuery`;
2. an MCP-compatible provider-neutral validation boundary;
3. a Senior Reviewer checking functional fidelity;
4. one bounded semantic repair when requested;
5. mandatory revalidation before the second review.

## Flow

```text
ConceptualQuery Programmer → MCP validation → Senior Reviewer
                                      ↑              │
                                      └── bounded repair
```

The application owns validation, budgets, routing, and persistence. The
Senior Reviewer never translates or executes a query. The experimental
preflight stops before physical translation and database execution; production
uses `HRDataGateway.validate_query()` at the MCP boundary.

## Production-oriented contract

The `AGENT_TEAM` path uses the application contract classes:

- `ConceptualQuery`, `QueryMetric`, `QueryFilter`, `QueryPeriod`, and
  `QueryOrder` from `peopleops_api.query_contracts`;
- `DiscoveryCatalog` from `peopleops_api.mcp_contracts`;
- the same catalog-bound identifier preflight used by the production workflow;
- `HRDataGateway.validate_query()` as the production validation boundary.

The Senior prompt receives the functional requirement, ConceptualQuery output,
and MCP validation result. It does not receive SQLAlchemy, compiled SQL, or
physical schema.

The SQLAlchemy comparison path continues to use
`validate_sqlalchemy_candidate` and `SubmitQueryProgrammerResult`.

Every tool call emitted by an `AIMessage` receives a corresponding
`ToolMessage`, including calls after a budget has been exhausted. A submission
in the same model round as validation is rejected; submission is accepted only
when the candidate was validated in an earlier round.

## Limits

- Maximum candidate validations: 3.
- Maximum model tool rounds: 8.
- No unrestricted loop.
- Technical failures cannot be reclassified as `CANNOT_IMPLEMENT` unless the
  functional requirement explicitly declares a capability gap.

## Scope

The runner receives a pre-built Functional Analyst `query_task`, so this
experiment isolates the Query Programmer and Senior Reviewer. It does not
invoke the Functional Analyst or execute database queries. `AGENT_TEAM` does
use the production semantic contract and MCP validation boundary; it does not
yet make a live MCP/database call.

## Verification

The deterministic tests cover:

- prior validation before submission;
- repair after tool feedback;
- multiple tool calls in one model round;
- tool-budget termination;
- unknown-tool protocol closure;
- structured final output.
