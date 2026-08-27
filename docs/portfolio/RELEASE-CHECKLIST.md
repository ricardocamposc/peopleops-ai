# Slice 18 release checklist

## Reproducibility

- [x] Fresh clone follows the root README quickstart.
- [x] `make build`, `make up`, `make health`, `make lint`, and `make test` pass.
- [x] `make demo-setup` creates disposable demo data and `make smoke` passes.
- [x] `make evaluate` writes `evaluation/runs/slice18-portfolio.{json,md}`.

## Architecture and evidence

- [x] Five Compose services are healthy; no extra runtime service is required.
- [x] MCP catalog/query and payroll denial smoke checks pass.
- [x] Policy corpus, retrieval/abstention tests and versioned artifacts are
  identifiable.
- [x] Durable Human Review, payroll reconciliation and Schema A/B tests are
  demonstrated.
- [x] No customer data, secrets, direct HRIS access or semantic keyword
  routing is present.

## Portfolio/pilot communication

- [x] Demo script and capture manifest are complete.
- [x] Limitations are visible and “production-ready” is not claimed.
- [x] Customer MCP substitution guide is reviewed before a real pilot.
