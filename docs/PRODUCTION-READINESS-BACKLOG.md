# PeopleOps AI — Production Readiness Backlog

## Purpose

This is the canonical backlog for the gap between a portfolio / controlled
demo / controlled pilot and a real client production deployment. Not every item
blocks a pilot, but applicable P0 and P1 items must be resolved before real
production. Every item records priority, risk, acceptance criteria and closure
evidence. This document does not mean that PeopleOps AI is production-ready.

## Current maturity

```text
Production-oriented portfolio MVP with reproducible evaluation evidence.
Policy RAG: Validated with known limitations.
Real client production: Not yet validated.
Controlled client pilot: Potentially achievable after applicable P0/P1 gate review.
```

## Status vocabulary

Only these statuses are valid: `OPEN`, `IN_PROGRESS`, `BLOCKED`, `VALIDATED`,
`DEFERRED`. `VALIDATED` requires implementation, executed tests, available
evidence and satisfied acceptance criteria. It must not be replaced by
`DONE`.

## Backlog items

### PRD-PROD-001 — Policy RAG retrieval precision / noise

ID: PRD-PROD-001
Title: Policy RAG retrieval precision / noise
Status: OPEN
Priority: P2 — Required for production hardening
Area: Policy RAG / Retrieval

Why it matters: First-stage retrieval has good recall but exposes substantial
irrelevant candidates, increasing cost, latency, and false-positive risk.

Current evidence: Regression v3: `document_precision=0.4222`,
`retrieval_noise_rate=0.5778`, `promoted_document_precision=1.0`. Holdout v2
final: `document_precision=0.4688`, `retrieval_noise_rate=0.5313`,
`promoted_document_precision=0.9615`.

Risk if unresolved: Unnecessary model calls and less predictable answers.

Required remediation: Evaluate retrieval tuning, hybrid retrieval, metadata
filtering, reranking, embedding quality, dynamic `top_k` and thresholds.

Acceptance criteria: Define and approve a client/production baseline; do not
invent a definitive percentage before that baseline exists.

Validation evidence: N/A — open.

Related files: `apps/peopleops-api/src/peopleops_api/policy_retrieval.py`,
`evaluation/baselines/policy-rag/regression-v3/metrics.json`.

Related evaluation cases: `v2-pt-unknown-fine`,
`holdout-compensation-distractors-es`.

Notes: Do not optimize for a single question or introduce hardcoded routing.

### PRD-PROD-002 — Semantic verifier false negatives

ID: PRD-PROD-002
Title: Semantic verifier false negatives
Status: OPEN
Priority: P1 — Required before client production
Area: Policy RAG / Evidence Verification

Why it matters: Correct documents and evidence can still be classified as
`INSUFFICIENT_DATA`, reducing usefulness.

Current evidence: Regression failures: `recruitment-purpose`,
`multi-policy-company`. Holdout examples: `v2-en-vacation-approval`,
`v2-es-typo-vacation`, `v2-es-conduct-discipline`,
`v2-en-termination-distinction`, `v2-en-recruitment-range`.

Risk if unresolved: Excessive abstention and poor user experience, even while
anti-hallucination behavior is preserved.

Required remediation: Evaluate verifier prompt/model, measure false-negative
rate, separate ambiguity from insufficient evidence, consider calibrated
confidence and clarification workflow.

Acceptance criteria: Dedicated validation set, measured false-negative rate,
no degradation in unsupported-claim/abstention tests, and a new unseen holdout
after tuning.

Validation evidence: Current public regression and holdout reports.

Related files: `apps/peopleops-api/src/peopleops_api/evidence_verifier.py`,
`evaluation/baselines/policy-rag/holdout-v2-final/report.md`.

Related evaluation cases: Listed current evidence above.

Notes: Never correct this with keyword routing or question-specific phrases.

### PRD-PROD-003 — Ambiguous questions / clarification state

ID: PRD-PROD-003
Title: Ambiguous questions / clarification state
Status: OPEN
Priority: P1 — Required before client production
Area: Agentic Workflow / UX

Why it matters: Ambiguous questions currently can end as `INSUFFICIENT_DATA`
when a clarification request would be more useful.

Current evidence: `What approval is required?` and `O que acontece quando uma
pessoa deixa a empresa?` are intentionally retained as ambiguity evidence.

Risk if unresolved: Users may not understand whether evidence is missing or
the question needs clarification.

Required remediation: Define `NEEDS_CLARIFICATION` semantics, add a LangGraph
branch, persist the state in `AnalysisInteraction`, implement frontend UX and
multilingual evaluation.

Acceptance criteria: Approved ADR, persisted state, clear UX, multilingual
tests and no degradation of valid abstentions.

Validation evidence: N/A — decision not approved.

Related files: `apps/peopleops-api/src/peopleops_api/analysis_workflow.py`,
`apps/peopleops-api/src/peopleops_api/models.py`.

Related evaluation cases: `v2-en-ambiguous-approval`,
`v2-pt-offboarding-ambiguous`.

Notes: Do not add this state without an approved architectural decision.

### PRD-PROD-004 — Separate answer fact coverage from evidence fact coverage

ID: PRD-PROD-004
Title: Separate answer fact coverage from evidence fact coverage
Status: OPEN
Priority: P2 — Required for production hardening
Area: Evaluation

Why it matters: Current `policy_fact_coverage` can use answer plus promoted
evidence, so a fact present in evidence may appear covered even when omitted
from the final answer.

Current evidence: Current evaluator reports one combined `policy_fact_coverage`
metric.

Risk if unresolved: Synthesis quality can be overstated.

Required remediation: Add `evidence_fact_coverage` for retrieval/verification
and `answer_fact_coverage` for synthesis; make `final_synthesis` diagnostics
depend primarily on answer coverage.

Acceptance criteria: Deterministic metrics are separately defined, N/A remains
N/A, tests cover evidence-only and answer-only facts, and reports expose both.

Validation evidence: N/A — open.

Related files: `apps/peopleops-api/src/peopleops_api/policy_evaluation.py`,
`ops/policy_rag_baseline.py`.

Related evaluation cases: Cases with `expected_policy_facts` in holdout v2.

Notes: Do not introduce business keyword lists.

### PRD-PROD-005 — LLM judge manifest traceability

ID: PRD-PROD-005
Title: LLM judge manifest traceability
Status: OPEN
Priority: P3 — Improvement / operational maturity
Area: Evaluation / Reproducibility

Why it matters: A manifest may retain `judge_model: null` even after judged
artifacts are produced.

Current evidence: Earlier curated runs exposed this mismatch; current runs
contain separate judge artifacts but the workflow remains vulnerable to it.

Risk if unresolved: Published evaluations are harder to reproduce and audit.

Required remediation: Add judge metadata with model, timestamp, prompt/version,
evaluator version and source predictions hash, without mixing it into
deterministic metrics.

Acceptance criteria: A judged run fails validation if judge metadata or source
hash is missing or inconsistent.

Validation evidence: N/A — open.

Related files: `ops/judge_policy_baseline.py`,
`ops/policy_rag_baseline.py`, `evaluation/baselines/policy-rag/`.

Related evaluation cases: N/A.

Notes: Preserve deterministic and LLM-judge artifacts separately.

### PRD-PROD-006 — Real client data privacy review

ID: PRD-PROD-006
Title: Real client data privacy review
Status: OPEN
Priority: P0 — Production blocker
Area: Security / Privacy

Why it matters: HR and payroll data can contain sensitive personal information.

Current evidence: Public evaluation uses synthetic data. Non-synthetic evidence
is not automatically sent to the external semantic verifier.

Risk if unresolved: Unauthorized disclosure, non-compliance and unacceptable
client risk.

Required remediation: Classify HR/PII, approve OpenAI data flows, define
retention, redact logs, prohibit chain-of-thought persistence, manage secrets,
define deletion/export, confidentiality and payroll controls.

Acceptance criteria: Written privacy/data-flow approval, retention policy,
redaction tests, deletion/export procedure and approved provider contracts.

Validation evidence: N/A — open.

Related files: `apps/peopleops-api/src/peopleops_api/evidence_verifier.py`,
`docs/enterprise-rag-alignment-audit.md`.

Related evaluation cases: N/A.

Notes: Keep non-synthetic verifier behavior fail-closed until approved.

### PRD-PROD-007 — Production authentication and authorization

ID: PRD-PROD-007
Title: Production authentication and authorization
Status: OPEN
Priority: P0 — Production blocker
Area: Security / Identity

Why it matters: Frontend visibility is not sufficient to protect HR, payroll,
policy and Human Review data.

Current evidence: Portfolio MVP operates in a local controlled environment.

Risk if unresolved: Unauthorized access, cross-user disclosure or unauthorized
employment actions.

Required remediation: Implement and verify authentication, RBAC/ABAC, payroll
authorization, policy confidentiality, Human Review permissions, conversation
access, tenant isolation, service authentication and audit identity.

Acceptance criteria: End-to-end authorization tests for every sensitive route,
negative access tests, tenant isolation evidence and audited user identity.

Validation evidence: N/A — open.

Related files: `apps/peopleops-api/src/peopleops_api/main.py`,
`apps/peopleops-web/`.

Related evaluation cases: N/A.

Notes: Never assume frontend authorization is sufficient.

### PRD-PROD-008 — Secrets and production configuration

ID: PRD-PROD-008
Title: Secrets and production configuration
Status: OPEN
Priority: P0 — Production blocker
Area: Infrastructure / Security

Why it matters: Local `.env` configuration is not a production secrets
management strategy.

Current evidence: Local workflows use environment configuration and synthetic
credentials.

Risk if unresolved: Credential leakage, unauthorized provider/database access
and weak rotation.

Required remediation: Use a secrets manager, eliminate manual production
`.env`, rotate API/database credentials, apply least privilege, separate
environments, enforce TLS and secure service configuration.

Acceptance criteria: Secret inventory, managed secret deployment, rotation
exercise, repository secret scan and TLS/network verification.

Validation evidence: N/A — open.

Related files: `.env.example`, `docker-compose.yml`, `apps/Makefile`.

Related evaluation cases: N/A.

Notes: Never commit secrets or production values.

### PRD-PROD-009 — Production database strategy

ID: PRD-PROD-009
Title: Production database strategy
Status: OPEN
Priority: P1 — Required before client production
Area: Database / Operations

Why it matters: Local PostgreSQL is not evidence of production durability.

Current evidence: PeopleOps uses PostgreSQL/pgvector locally and remains
separate from the synthetic HRIS database.

Risk if unresolved: Data loss, failed restore, migration downtime or vector
compatibility failures.

Required remediation: Define managed PostgreSQL, backups, PITR, pgvector
compatibility, migration strategy, restore test, pooling, timeouts, monitoring,
ownership and retention.

Acceptance criteria: Approved architecture, successful backup/restore drill,
tested migrations and documented operational ownership.

Validation evidence: N/A — open.

Related files: `docker-compose.yml`, `apps/peopleops-api/alembic/`,
`apps/peopleops-api/src/peopleops_api/db.py`.

Related evaluation cases: N/A.

Notes: Preserve `PeopleOps DB != HRIS DB`.

### PRD-PROD-010 — Client HRIS/MCP integration hardening

ID: PRD-PROD-010
Title: Client HRIS/MCP integration hardening
Status: OPEN
Priority: P0 — Production blocker
Area: MCP / Integration

Why it matters: The current MCP boundary is synthetic/reference-only and has
not been validated against a real client HRIS.

Current evidence: the reference implementation now uses the official MCP SDK
and Streamable HTTP with the synthetic HRIS. The final synthetic validation
also demonstrated provider-side SQL rejection, PostgreSQL transaction-level
read-only enforcement and unchanged data after attempted writes. Real client
integration, authentication, mTLS/OAuth, network policy and client-specific
mapping remain unvalidated.

Risk if unresolved: Unauthorized data access, schema mismatch, unsafe writes or
silent integration failures.

Required remediation: Real MCP implementation, authentication, scopes,
read-only enforcement, timeout/retry policy, failure handling, catalog/version
management, audit, semantic mappings and schema independence verification.

Acceptance criteria: Client-approved integration test, read-only proof,
authorization tests, outage tests, audit evidence and no direct PeopleOps to
HRIS fallback.

Validation evidence: `evaluation/baselines/mcp/regression-v2/` records the
synthetic boundary evidence. It does not close this production item; it must
still be reviewed after the ERP AI Analyst → PeopleOps architecture
remediation and against a real client source.

Related files: `apps/reference-mcp-server/`,
`apps/peopleops-api/src/peopleops_api/mcp_client.py`.

Related evaluation cases: `evaluation/cases/hris_mcp_mvp_v1.jsonl` is not a
real-client baseline.

Notes: Do not redesign this item in the Policy RAG remediation.

### PRD-PROD-011 — Observability and operational monitoring

ID: PRD-PROD-011
Title: Observability and operational monitoring
Status: OPEN
Priority: P1 — Required before client production
Area: Operations / Observability

Why it matters: Production operations require functional auditability and
actionable diagnostics, not only local logs.

Current evidence: `AnalysisInteraction`, structured logs and optional LangSmith
tracing exist. LangSmith credentials may be unavailable locally; Phoenix is not
enabled by default.

Risk if unresolved: Slow incident response, missing cost/latency visibility and
undetected RAG/MCP degradation.

Required remediation: Define metrics, error/latency/token/cost dashboards, MCP
and RAG health, LLM failure rate, Human Review queue, alerting, correlation IDs
and retention.

Acceptance criteria: Production dashboards, alerts tested with synthetic
failures, retention policy and correlation from request to persisted analysis.

Validation evidence: N/A — open.

Related files: `apps/peopleops-api/src/peopleops_api/observability.py`,
`apps/peopleops-api/src/peopleops_api/models.py`.

Related evaluation cases: N/A.

Notes: Do not add Phoenix by default.

### PRD-PROD-012 — Production evaluation dataset

ID: PRD-PROD-012
Title: Production evaluation dataset
Status: OPEN
Priority: P1 — Required before client production
Area: Evaluation

Why it matters: Public baselines use synthetic policies and cannot be the sole
acceptance evidence for a client.

Current evidence: Regression v3 and holdout v2 final are reproducible synthetic
baselines.

Risk if unresolved: Client-specific failures remain undetected.

Required remediation: Create a client acceptance dataset from synthetic,
authorized anonymized data or SME-validated ground truth; establish
pre-production and production regression baselines.

Acceptance criteria: Privacy-approved dataset, SME ground truth, accepted
thresholds, reproducible run and regression process before model changes.

Validation evidence: N/A — open.

Related files: `evaluation/cases/`, `evaluation/baselines/policy-rag/`.

Related evaluation cases: Public policy datasets are reference only.

Notes: Do not use the public holdout as the only client validation.

### PRD-PROD-013 — Model/version pinning and change management

ID: PRD-PROD-013
Title: Model/version pinning and change management
Status: OPEN
Priority: P1 — Required before client production
Area: LLM Operations

Why it matters: Model, embedding, prompt and schema changes can change answers
without application code changes.

Current evidence: Manifests record model and retrieval configuration for public
evaluation runs.

Risk if unresolved: Unplanned regressions, irreproducible results and no safe
rollback.

Required remediation: Pin model IDs, embedding model, prompt/schema/evaluator
versions; require change approval, regression evaluation and rollback.

Acceptance criteria: Versioned configuration, change record, mandatory
baseline gate and tested rollback for every model/configuration change.

Validation evidence: N/A — open.

Related files: `ops/policy_rag_baseline.py`, `ops/judge_policy_baseline.py`,
`evaluation/baselines/policy-rag/`.

Related evaluation cases: All applicable evaluation suites.

Notes: Judge metrics never replace deterministic evaluation.

### PRD-PROD-014 — Cost and latency budget

ID: PRD-PROD-014
Title: Cost and latency budget
Status: OPEN
Priority: P2 — Required for production hardening
Area: Operations / FinOps

Why it matters: A working analysis can still be commercially or operationally
unviable at client scale.

Current evidence: Baseline artifacts contain case results but not a formal
production SLO/load budget.

Risk if unresolved: Unbounded cost, poor response times and capacity failures.

Required remediation: Define analysis/Policy RAG/MCP latency, token and call
budgets, verifier cost, concurrency and judge exclusion from runtime; run load
tests.

Acceptance criteria: Approved SLOs, load test, cost model, alert thresholds and
capacity plan.

Validation evidence: N/A — open.

Related files: `apps/peopleops-api/src/peopleops_api/config.py`,
`evaluation/baselines/policy-rag/`.

Related evaluation cases: N/A.

Notes: Measure realistic client workloads.

### PRD-PROD-015 — Backup / disaster recovery / operational runbook

ID: PRD-PROD-015
Title: Backup / disaster recovery / operational runbook
Status: OPEN
Priority: P1 — Required before client production
Area: Operations

Why it matters: Production service needs recoverable data and a tested response
to failures across the API, database, providers and MCP.

Current evidence: Local startup, migration and evaluation commands are
documented; no production restore or incident exercise exists.

Risk if unresolved: Extended outage, unrecoverable audit/evidence data and
unsafe deployments.

Required remediation: Deployment/rollback runbook, DB backup/restore exercise,
incident procedure, degraded mode and outage procedures for providers, MCP and
policy ingestion.

Acceptance criteria: Approved runbook, successful restore drill, rollback drill,
incident simulation and named operational owners.

Validation evidence: N/A — open.

Related files: `README.md`, `Makefile`, `apps/Makefile`, `docs/`.

Related evaluation cases: N/A.

Notes: N/A.

## Production Gate

PeopleOps AI must not be described as production-ready until the applicable
gate is satisfied with recorded evidence.

- [ ] All P0 items `VALIDATED`
- [ ] Required P1 items `VALIDATED`
- [ ] Real MCP boundary validated
- [ ] Client HRIS integration validated
- [ ] Authentication/RBAC validated
- [ ] Payroll/PII authorization validated
- [ ] Privacy/data-flow review approved
- [ ] Client acceptance dataset executed
- [ ] Deterministic evaluation baseline accepted
- [ ] Known RAG limitations reviewed with client
- [ ] Backup/restore tested
- [ ] Monitoring/alerting enabled
- [ ] Secrets managed outside repository
- [ ] TLS/network controls verified
- [ ] Load/latency/cost budgets validated
- [ ] Deployment/rollback runbook tested

## Controlled Pilot Gate

A controlled pilot may accept applicable P2/P3 items that remain open, but it
must document known limitations and satisfy these conditions:

- [ ] No unresolved applicable P0
- [ ] MCP/data boundary safe
- [ ] Real client access controlled
- [ ] PII/data-flow policy approved
- [ ] Human Review available for sensitive decisions
- [ ] Client-specific acceptance tests executed
- [ ] Audit logging available
- [ ] Backup available
- [ ] Rollback path available
- [ ] Known limitations documented and accepted

A client pilot must be described as a `controlled client pilot`, not as proof
that the product is production-ready.

## Backlog History

| Date | Item | Change | Evidence |
|---|---|---|---|
| 2026-08-28 | Initial production-readiness backlog | Added 15 open items, Production Gate and Controlled Pilot Gate | Current repository evaluation evidence and architecture documentation |
## MCP temporal and execution audit evidence

The MVP now has provider-derived temporal context and a separate MCP audit
store for development/test evidence. Production rollout still requires a
managed audit schema with retention/redaction policy, provider authentication,
access control and operational review of SQL/parameter sensitivity. Relative
period resolution remains intentionally provider-authoritative and is not
derived from the PeopleOps application clock.
