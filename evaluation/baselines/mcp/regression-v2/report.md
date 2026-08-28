# MCP boundary evaluation

Run: `mcp-regression-v2-final`
Cases: 12

## Metric definitions

- `handshake_success_rate`: 11 eligible cases; 11 successful. The intentionally unavailable-provider case is excluded from this denominator.
- `expected_failure_handling_accuracy`: the unavailable-provider case remains evaluated separately.
- `read_only_enforcement`: provider-side SQL validation plus PostgreSQL read-only transaction probe.

## Metrics

- `handshake_success_rate`: 1.0
- `capability_discovery_success_rate`: 1.0
- `query_validation_accuracy`: 1.0
- `execution_success_rate`: 1.0
- `error_normalization_accuracy`: 1.0
- `schema_independence_accuracy`: N/A
- `provider_evidence_validity`: 1.0
- `read_only_enforcement`: 1.0
- `expected_failure_handling_accuracy`: 1.0

## Failed cases

