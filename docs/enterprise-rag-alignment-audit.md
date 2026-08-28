# Enterprise RAG → PeopleOps AI alignment audit

## Scope

This matrix is the mandatory decision record before implementation. It reuses
engineering and evaluation patterns demonstrated in Enterprise RAG without
copying its application architecture or replacing PeopleOps-owned agentic,
MCP, HRIS, payroll or human-review components.

Reference implementation: `ricardocamposc/enterprise-rag`.

Target implementation: `ricardocamposc/peopleops-ai`.

Audit baseline: PeopleOps commit `0a12bef` on `main`.

No PeopleOps production code was changed while preparing this matrix.

## Decision matrix

| Enterprise RAG component/pattern | PeopleOps current equivalent | Status | Rationale and required action |
|---|---|---|---|
| PDF/document ingestion | `policy_ingestion.py`, `PolicyIngestionService`, `IngestionJob` | ADAPT | Preserve `PolicyDocument`/`PolicyVersion`, checksum idempotency, storage and ingestion audit. Add/verify explicit corpus validation; baseline must never ingest silently. |
| PDF parsing and page provenance | `_pdf_documents`, `SentenceSplitter`, `PolicyChunk.page` | REUSE/ADAPT | Keep LlamaIndex parsing/chunking and page provenance. Add section provenance where available and tests for malformed/low-text PDFs. |
| LlamaIndex embedding boundary | `build_embedding_model`, `get_embedding_model` | REUSE | LlamaIndex has a real embedding responsibility. Keep OpenAI/MockEmbedding configuration and document model/dimension in the run manifest. |
| Durable vector persistence | `PolicyChunk.embedding` with PostgreSQL/pgvector | KEEP PEOPLEOPS | Policy chunks and versions are already PeopleOps-owned persistence. Do not import SEC document models or Enterprise RAG tables. |
| LlamaIndex `PGVectorStore` | No current `PGVectorStore`; SQLAlchemy query uses pgvector distance | KEEP PEOPLEOPS + DOCUMENT | Do not rewrite automatically. The current design has a legitimate PeopleOps policy schema and LlamaIndex embedding/query role. Document the decision and prove retrieval equivalence through integration tests. Revisit only if the current adapter cannot meet requirements. |
| Metadata model | `PolicyDocument`, `PolicyVersion.metadata_`, department/confidentiality/status | KEEP PEOPLEOPS | Preserve HR policy metadata and add evaluation filters without flattening policy version semantics. |
| Effective-date/version selection | `_select_versions(as_of, filters)` | REUSE/ADAPT | Keep historical selection and conflict detection. Add explicit expected policy version(s) and version accuracy to observations/metrics. |
| Retrieval filters | `PolicyRetrievalFilters` | ADAPT | Preserve document key/type/department/confidentiality/JSON metadata filters. Extend case schema and metrics for filter precision without hardcoded language rules. |
| Structural evidence verification | `_verify_chunk` and `PolicyEvidence` | ADAPT | Extract into a named structural verifier with checks for document/version/date/chunk/provenance/score. Return structured reasons and evidence IDs. |
| Semantic evidence verification | No independent verifier found | REPLACE/ADD | Add a provider-neutral, language-independent verifier that checks whether cited fragments support the central claim. It must return `answerable`, `insufficient_evidence`, citation/evidence indexes, reason and abstention data. |
| Evidence-aware abstention | Retrieval statuses plus workflow handling | ADAPT | Map verifier outcomes to PeopleOps statuses without losing `POLICY_NOT_FOUND`, `POLICY_CONFLICT` or `INSUFFICIENT_DATA`. Do not use phrase lists or Spanish/English/Portuguese comparisons. |
| Final answer synthesis | `AnalysisWorkflow` and structured model | KEEP PEOPLEOPS + INTEGRATE | Preserve LangGraph/AnalysisWorkflow. Integrate verified policy evidence before synthesis and persist the decision in `AnalysisInteraction`. |
| Separation ingestion/retrieval/verification/answer | Services exist, but evaluator bypasses application boundary | ADAPT | Keep four explicit phases in runtime and expose their outcomes in traceability. Evaluation must invoke the real application path, not call the provider directly as its only observation. |
| Dataset with expected values | `evaluation/cases/policy_rag_v1.jsonl` with 5 cases | ADAPT | Expand/version the dataset with positive, negative, historical, conflict, filters, multi-document and EN/ES/PT cases. Keep only expected values; never store observed results in cases. |
| Real prediction runner | `evaluation_runner.py` evaluates provider/cases directly | REPLACE/ADD | Add a PeopleOps Policy RAG runner that calls the real API/application, records request ID, selected/retrieved policies, versions, pages/sections, chunks, scores, verifier decision, answer, errors and latency. Checkpoint every case. |
| Deterministic evaluator | `policy_evaluation.py` | ADAPT | Separate dataset and predictions inputs. Add document hit/recall, version accuracy, filter precision, page/section recall, answerability, abstention, citation validity and evidence-verification accuracy with applicability-aware denominators. |
| LLM judge | No Policy RAG judge found | ADD OPTIONAL | Add a separate opt-in command and artifacts after deterministic baseline. Never use it as ground truth or overwrite deterministic output. |
| Versioned run artifacts | `evaluation/runs/` plus static baselines | ADAPT | Use `evaluation/runs/baseline-v1-YYYYMMDD-HHMMSS/` with manifest, predictions, metrics and report; include commit, dataset, model, embedding model, top-k, threshold and configuration. |
| Failure diagnosis | Current evaluator returns limited case records | ADAPT | Report failed case and likely layer: corpus/ingestion, retrieval, filters, version selection, structural verification, semantic verification, abstention or synthesis. |
| Regression tests | Policy ingestion/retrieval/workflow tests exist | ADAPT | Preserve existing tests and add independent suites for verifier, dataset/prediction loaders, runner, artifact contract and real PostgreSQL/pgvector integration. |
| API contract tests | PeopleOps API tests and workflow tests | ADAPT | Add contracts for policy upload, ingestion status, policy retrieval and real evaluation execution while preserving existing AnalysisInteraction/MCP/Human Review contracts. |
| Makefile workflow | Root Makefile has `evaluate`, no dedicated Policy RAG baseline/judge | ADAPT | Add consistent `baseline-policy`, `baseline-policy-judge` or equivalent targets. Do not make Docker/LocalStack/Phoenix mandatory for this workflow. |
| Docker/Make/configuration | Docker Compose includes PeopleOps API, MCP, HRIS and DB | KEEP PEOPLEOPS | Preserve PeopleOps deployables. Use Docker only when needed for infrastructure; the evaluation runner must also support direct API execution and explicit DB readiness checks. |
| LocalStack/S3/Phoenix | Not required by current PeopleOps policy design | NOT APPLICABLE | Do not introduce these services just to match Enterprise RAG. Keep optional observability boundaries already owned by PeopleOps. |
| Traceability | `AnalysisInteraction`, stage history, evidence, response, latency | REUSE/ADAPT | Preserve durable interaction traceability and add verifier/evaluation metadata without mixing interactive response generation with post-hoc judging. |
| Multilingual behavior | Existing multilingual anti-hardcoding evaluation | KEEP PEOPLEOPS + EXTEND | Reuse the language-independent testing philosophy. Add real Policy RAG cases in English, Spanish and Portuguese without literal answer detection. |
| Security and untrusted documents | Upload validation and `untrusted_content` metadata | REUSE/ADAPT | Preserve fail-closed validation, bounded metadata and untrusted-content handling. Ensure logs/artifacts do not expose sensitive HR data. |

## Decisions before implementation

1. Keep PeopleOps policy tables and SQLAlchemy/pgvector persistence.
2. Keep LlamaIndex for parsing, chunking and embeddings; do not introduce
   `PGVectorStore` unless a measured gap justifies the migration.
3. Add structural and semantic evidence verification as an explicit boundary.
4. Add a real application execution runner and keep expected/observed data
   separate.
5. Expand the versioned Policy RAG dataset before the first new baseline.
6. Add applicability-aware deterministic metrics and a separate optional
   LLM-judge workflow.
7. Preserve LangGraph, MCP, HRIS, payroll, AnalysisInteraction and Human
   Review architecture.

## Current audit findings

- Ingestion and policy versioning are present and materially aligned with the
  reference pattern.
- Retrieval applies policy metadata and effective-date selection, but the
  current `_verify_chunk` is structural rather than semantic verification.
- LlamaIndex is used for documents, splitting and embeddings; vector search is
  a deliberate SQLAlchemy/pgvector adapter, not merely a nominal dependency.
- The current five-case evaluator calls `PolicyKnowledgeProvider` directly and
  therefore is not yet a real end-to-end application baseline.
- The current dataset does not yet cover the required multilingual,
  multi-document, filter, conflict and evidence-related scenarios.
- No code changes are authorized from this matrix alone; implementation starts
  after this decision record is reviewed.
