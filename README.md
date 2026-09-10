# PeopleOps AI — HR Intelligence Copilot

> **Flagship portfolio project for AI Solutions Architecture & Agentic Enterprise Systems.**  
> Policy-aware, agentic HR intelligence over structured HR data and internal policies, with evidence, schema-independent MCP integration, Human-in-the-loop governance, and low-level workflow observability.

PeopleOps AI is an enterprise AI reference implementation for Human Resources. It combines structured HR data, payroll, attendance, contracts, vacation/leave information, internal policies and procedures, and human review in one auditable agentic workflow.

It is intentionally **not** a document chatbot and **not** a fixed catalog of question-specific functions. Natural-language requests are interpreted into typed semantic requirements; the available HR model is discovered dynamically through MCP; provider-neutral conceptual queries are planned and validated without coupling the agent to physical tables or SQL dialects; policies are retrieved with evidence; and LangGraph coordinates the workflow.

> **Status:** portfolio/pilot MVP completed, with ongoing architecture and evaluation hardening.  
> **Positioning:** production-oriented, not production-ready.  
> **Data:** synthetic/fictitious only. HRIS access is read-only.

---

## PeopleOps in action

The web application exposes the production-oriented analysis workflow through a usable HR workspace. Users can ask questions in natural language, review the synthesized answer, inspect supporting structured-data evidence, and navigate recent analyses, policy evidence and Human Review from the same interface.

![PeopleOps AI analysis workspace](docs/portfolio/assets/peopleops-analysis-workspace.webp)

The following example asks PeopleOps to **list the last 5 employees who joined the company**. The returned evidence contains only **4 matching active employees**. Rather than inventing a fifth row to satisfy the requested cardinality, PeopleOps explicitly reports that only four are available and displays the underlying records.

![PeopleOps AI evidence-driven response](docs/portfolio/assets/peopleops-last-five-employees.webp)

This illustrates an important product behavior: the LLM-generated synthesis is not treated as the source of truth. The answer is grounded in the structured result returned through the MCP path, and the UI exposes that evidence so the user can verify the conclusion. When the available data cannot satisfy the requested cardinality, the system reports the limitation instead of fabricating a result.

---

## Architecture at a glance

```text
HR User / External MCP Client
        │
        ├──────────────────────────────────────────────┐
        │                                              │
        ▼                                              ▼
 PeopleOps Web                                  MCP-compatible client
 Next.js / React                               e.g. OpenAI Codex
        │                                              │
        ▼                                              │
 PeopleOps API                                         │
 FastAPI + LangGraph + OpenAI                          │
        │                                              │
        ├── Functional Analyst                         │
        ├── Query Programmer subgraph                  │
        ├── Senior Reviewer                            │
        ├── HR Assistant / synthesis                   │
        ├── Policy RAG / LlamaIndex                    │
        ├── Human Review                               │
        ├── AnalysisInteraction audit                  │
        └── HRDataGateway                              │
                    │                                  │
                    ▼                                  │
                 MCP Client                            │
                    │                                  │
==================== MCP BOUNDARY =====================│
                    │                                  │
                    └──────────────┬───────────────────┘
                                   ▼
                         Reference MCP Server
                         official Python SDK
                         Streamable HTTP /mcp
                                   │
                         ├── semantic discovery
                         ├── scoped catalog
                         ├── conceptual-query contract
                         ├── deterministic validation
                         ├── physical translation
                         ├── EXPLAIN / read-only execution
                         ├── limits / timeouts
                         ├── provider-neutral evidence
                         └── MCP audit
                                   │
                                   ▼
                         Synthetic Reference HRIS
                              PostgreSQL
```

> **PeopleOps expresses what information it needs; the MCP provider owns how that information maps to and is retrieved from the physical source.**

`peopleops-api` does not receive Synthetic HRIS database credentials and does not use a silent direct-database fallback.

---

## Production-oriented agent workflow

```text
Natural-language request
        ↓
Functional Analyst
        ↓
MCP capability / scoped catalog discovery
        ↓
typed Functional Requirement
        ↓
Query Programmer subgraph
        ↓
provider-neutral ConceptualQuery
        ↓
MCP validation
        ↓
Senior Reviewer
        ├── approve
        └── request one bounded semantic repair
                    ↓
               revalidate
                    ↓
MCP read-only execution
        ↓
Policy retrieval when required
        ↓
evidence-aware synthesis
        ↓
Human Review when required
        ↓
final answer
```

The **Functional Analyst**, **Query Programmer**, and **Senior Reviewer** have different responsibilities. The reviewer does not translate or execute SQL. The agentic layer reasons over semantic contracts; deterministic code owns validation, budgets, routing, persistence, authorization and execution guardrails.

See [`evaluation/spikes/PHASE43.md`](evaluation/spikes/PHASE43.md) and [`evaluation/spikes/PHASE44.md`](evaluation/spikes/PHASE44.md).

---

## Standalone MCP Server

`apps/reference-mcp-server` is a real MCP server built with the official Python SDK and **Streamable HTTP** at `http://127.0.0.1:8001/mcp`.

It exposes generic capabilities including semantic/catalog discovery, relationship discovery, temporal context, conceptual-query validation and scoped read-only execution. The MCP provider owns physical mappings, introspection, translation, PostgreSQL `EXPLAIN`, limits/timeouts, provider-neutral evidence and audit. Payroll entities/fields are restricted and no HRIS write operation is advertised.

See [`apps/reference-mcp-server/README.md`](apps/reference-mcp-server/README.md).

---

## Validated with OpenAI Codex as an external MCP client

The MCP boundary was manually validated from an **isolated OpenAI Codex CLI workspace outside the PeopleOps repository**.

```bash
codex mcp add local_mcp_8001 --url http://127.0.0.1:8001/mcp
```

In a fresh Codex session, natural-language requests caused Codex to invoke the registered MCP tools directly. Codex dynamically discovered the HR semantic model, composed scoped `hr:read` conceptual queries and used relationships exposed by the provider without depending on PeopleOps application code or the physical HRIS schema.

See [`docs/portfolio/MCP-CODEX-VALIDATION.md`](docs/portfolio/MCP-CODEX-VALIDATION.md).

---

## PeopleOps Semantic Run Viewer

A core engineering goal is to make agent behavior inspectable instead of treating a successful final answer as sufficient evidence.

```bash
cd apps/peopleops-api
PYTHONPATH=src poetry run python ../../evaluation/spikes/semantic_run_viewer.py
```

Then open `http://127.0.0.1:8765`.

![PeopleOps Semantic Run Viewer](docs/portfolio/assets/semantic-run-viewer-overview.jpg)

The viewer reconstructs evaluation cases as ordered executions grouped by LangGraph node and step. Depending on the run, it exposes node transitions, LLM model rounds, prompt template, rendered system prompt, exact model input, accumulated context, model response, tool calls, tool inputs/outputs, MCP discovery/validation/execution, Query Programmer output, Senior Reviewer decisions, bounded repair/revalidation paths and the final response.

It has been used during development to find and correct **duplicated/redundant calls**, inspect prompt behavior, verify model/tool interaction and isolate whether failures originate in semantic understanding, planning, tool selection, validation, review, MCP execution or synthesis.

LangSmith remains useful for generic tracing and evaluation support. The Semantic Run Viewer has a different purpose: a **human-readable, domain-aware replay of what the PeopleOps workflow actually did**.

> A green check means the workflow completed. The viewer is there to show what happened underneath.

Implementation: [`evaluation/spikes/semantic_run_viewer.py`](evaluation/spikes/semantic_run_viewer.py).

---

## What the MVP demonstrates

- natural-language and multilingual HR analysis without language-specific routing;
- dynamic MCP capability/schema/relationship/semantic discovery;
- provider-neutral conceptual queries;
- agentic Query Programmer with real tool calling;
- independent Senior Reviewer and bounded semantic repair;
- safe read-only structured-data execution;
- employee, contract, attendance, overtime, vacation, leave and payroll analysis;
- Attendance/Overtime ↔ Payroll reconciliation;
- version-aware Policy RAG;
- evidence verification, limitation reporting and abstention;
- combined structured-data + policy reasoning;
- durable Human-in-the-loop workflows;
- persistent functional audit through `AnalysisInteraction`;
- MCP contract and schema-independence testing;
- external MCP-client interoperability validation with OpenAI Codex;
- reproducible multi-layer evaluation;
- low-level agent/tool/LLM observability through the Semantic Run Viewer.

---

## Design principles

**No semantic hardcoding.** Natural-language meaning is not resolved with keyword lists or question-specific routing.

**Capabilities, not question-specific tools.** The model composes entities, fields, filters, metrics, periods and relationships dynamically.

**LLM for semantics; deterministic code for invariants.** LLMs may interpret, plan, choose tools, correlate evidence and synthesize. Deterministic code owns authorization, typed schemas, persistence, calculations, budgets, read-only enforcement, query validation and execution boundaries.

**Facts, policies and inference remain distinct.** Facts come from structured HR data through MCP; policies come from versioned documents through Policy RAG; inference is the model's interpretation based on those sources.

**Human governance is first-class.** Sensitive, ambiguous, conflicting or insufficiently supported situations can enter durable Human Review and resume after an audited decision.

**Evidence before confidence.** Missing or conflicting evidence is a valid result. The system should report limitations or abstain rather than invent support.

---

## Policy RAG

Policy knowledge belongs to PeopleOps, not to the HRIS MCP provider. The MVP uses **LlamaIndex + PostgreSQL/pgvector** with version/effective-date aware policy retrieval and evidence verification.

---

## Functional audit and schema independence

Every accepted analysis creates an `AnalysisInteraction` before LangGraph starts. A unique `request_id` identifies one execution and the durable audit stores observable outputs such as stages, semantic request, query plan, provider/catalog version, validations, structured results, policy sources, evidence, Human Review state, final response, warnings and safe error metadata.

Private model chain-of-thought is not persisted. The viewer exposes **observable prompts, messages, tool calls, tool results and application events**, not hidden reasoning.

Schema independence is tested rather than merely claimed. The same PeopleOps application logic is exercised against physically different HRIS schemas while only MCP-side source mapping and semantic metadata change.

---

## Evaluation

The Slice 18 portfolio baseline includes:

| Dataset | Cases |
|---|---:|
| `integrated_v1` | 7 |
| `multilingual_antihardcoding_v1` | 12 |
| `payroll_deep_analysis_v1` | 4 |
| `policy_rag_v1` | 5 |
| `schema_independence_v1` | 2 |

Recorded integrated pass rates are **100%** for `conceptual_mcp`, `final_answer`, `hitl`, `policy_rag`, `semantic`, `structured_data` and `workflow` in that release baseline. Later evaluation phases deliberately probe deeper Query Programmer/Senior Reviewer behavior and expose failures for diagnosis.

See [`evaluation/runs/slice18-portfolio.md`](evaluation/runs/slice18-portfolio.md).

---

## Technology stack

| Concern | Technology |
|---|---|
| Backend / API | Python 3.11 + FastAPI |
| Agentic workflow / HITL | LangGraph |
| LLM / structured outputs / tool calling | OpenAI |
| Policy RAG | LlamaIndex |
| Structured HR integration | MCP |
| Persistence / vectors | PostgreSQL + pgvector |
| Contracts | Pydantic v2 |
| Migrations | Alembic |
| Testing / lint | Pytest + Ruff |
| Frontend | Next.js + React + TypeScript |
| Generic tracing | LangSmith |
| Domain-aware inspection | PeopleOps Semantic Run Viewer |
| Local orchestration | Docker Compose + root Makefile |

The MVP is **single-tenant per instance**.

---

## Quickstart

```bash
cp .env.example .env
cp apps/peopleops-web/.env.example apps/peopleops-web/.env.local
make build
make infra
make migrate
make migrate-hris
make seed-hris
make generate-policy-pdfs

# Separate terminals
make api
make mcp
make web

# Verification
make smoke
make lint
make test
make evaluate
```

Live model-backed analysis requires `OPENAI_API_KEY`.

---

## Security and scope

The public repository uses synthetic HR data and synthetic policies only. Controls include least-privilege database ownership, environment-based secrets, restricted payroll fields, scoped MCP requests, read-only HRIS operations, result limits/timeouts, safe logging and request correlation, provider-side validation/`EXPLAIN`, evidence preservation, prompt-injection defenses and durable Human Review.

The MVP does **not** aim to replace an HRIS, automate dismissals/promotions/sanctions, mutate payroll/HRIS records, provide definitive legal advice, publish proprietary ERP adapters or become a generic BI platform. A real BIZAG/SAP/Workday/customer integration belongs behind the MCP boundary.

---

## Portfolio positioning

PeopleOps AI is the **flagship technical project** in this portfolio because it brings together the capabilities needed to defend an enterprise agentic architecture end to end:

**dynamic HR intelligence + semantic MCP integration + Policy RAG + bounded agentic workflows + Human-in-the-loop + evaluation + low-level observability**

Its central engineering claim is not that an LLM can answer HR questions. It is that an enterprise AI system can be designed so its **semantics, integrations, tool use, validation, evidence, governance and failures are inspectable and testable**.

---

## Release material

- [`docs/portfolio/MCP-CODEX-VALIDATION.md`](docs/portfolio/MCP-CODEX-VALIDATION.md)
- [`docs/portfolio/assets/README.md`](docs/portfolio/assets/README.md)
- [`evaluation/runs/slice18-portfolio.md`](evaluation/runs/slice18-portfolio.md)
- [`evaluation/spikes/semantic_run_viewer.py`](evaluation/spikes/semantic_run_viewer.py)

## License

A repository license will be selected before public release. Until a license file is committed, no license should be inferred from this README.
