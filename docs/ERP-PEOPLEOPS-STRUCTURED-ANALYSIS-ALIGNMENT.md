# ERP AI Analyst → PeopleOps Structured Analysis Alignment

This document records the capability comparison required before changing the
structured-data analysis path. ERP AI Analyst is a behavioral reference; its
direct database responsibilities are not copied into PeopleOps, where the MCP
provider boundary owns physical source access.

| Capability | ERP AI Analyst implementation | PeopleOps implementation | Classification | Action |
|---|---|---|---|---|
| Semantic interpretation | LLM gateway plus legacy keyword/rule routing in the compatibility gateway | Typed `SemanticRequest` produced by structured output; provider-neutral capability/entity selection | SUPERIOR_IN_PEOPLEOPS | Preserve PeopleOps; do not port business-language routing |
| Dynamic planning | Typed SQL proposals and multi-step agent graph | Typed `AnalysisPlan` with bounded multiple `ConceptualQuery` objects | EQUIVALENT | Add live evaluation coverage |
| Query contract | Physical SQL proposal with table/column fields | Provider-neutral `ConceptualQuery` covering entities, projections, metrics, filters, relationships, periods, comparisons, dimensions and limits | SUPERIOR_IN_PEOPLEOPS | Preserve |
| Validation before execution | Deterministic SQL/metadata guardrails and semantic review | Conceptual validation in API plus physical validation in MCP server | SUPERIOR_IN_PEOPLEOPS | Preserve responsibility split |
| Replanning | Bounded proposal/review loop | Bounded provider-feedback replan (`max_replans`) | EQUIVALENT | Add evaluation diagnostics |
| Post-result verification | Semantic review of returned structured result | Numeric grounding and explicit structured-result classification; valid zero rows must remain distinguishable from missing evidence | PARTIAL | Implement result verification and zero-row regression tests |
| Temporal reasoning | Broad relative/latest/explicit period guidance | Typed date, payroll-period and period-comparison contract; interpretation delegated to the model | PARTIAL | Add multilingual regression and holdout cases |
| Evidence grounding | Query result/evidence attached to final answer | Provider-neutral `QueryEvidence` persisted in `AnalysisInteraction` and attached to synthesis | SUPERIOR_IN_PEOPLEOPS | Preserve; extend evaluation evidence |
| Audit trail | Agent messages, tool results and evaluation artifacts | Durable `AnalysisInteraction` stage snapshots, evidence and latency | SUPERIOR_IN_PEOPLEOPS | Preserve |
| Physical execution | Direct ERP provider/database in backend | MCP Server discovery, mapping, validation, EXPLAIN and read-only execution | SUPERIOR_IN_PEOPLEOPS | Do not move physical SQL or credentials |
| Evaluation | Real agentic evaluation with per-case tool/model accounting | Existing contract baselines; no dedicated real structured-analysis dataset/runner | REGRESSION | Add ground-truth-only regression and holdout runners |
| Zero-row semantics | Explicitly tested as a valid query result | Previously conflated empty rows with absent evidence | REGRESSION | Correct synthesis gate and test |
| Silent query mutation | Validator feedback preserves proposal meaning | Plan completion filtered unknown fields/filters before provider validation | REGRESSION | Preserve invalid references and let validation/replan handle them |

## Scope decisions

- MCP transport, official SDK, provider boundary, read-only guarantees and
  Policy RAG remain unchanged.
- ERP's Spanish/English keyword routing is not considered a capability to port.
- Structured evaluation datasets contain expected ground truth only. Observed
  results belong exclusively in run artifacts.
