# PeopleOps AI — HR Intelligence Copilot

> **Flagship portfolio project for AI Solutions Architecture & Agentic Enterprise Systems.**  
> Policy-aware, agentic HR intelligence over structured HR data and internal policies, with evidence, schema-independent MCP integration, Human-in-the-loop governance, and low-level workflow observability.

PeopleOps AI is an enterprise AI reference implementation for Human Resources. It combines structured HR data, payroll, attendance, contracts, vacation/leave information, internal policies and procedures, and human review in one auditable agentic workflow.

It is intentionally **not** a document chatbot and **not** a fixed catalog of question-specific functions. Natural-language requests are interpreted into typed semantic requirements; the available HR model is discovered dynamically through MCP; provider-neutral conceptual queries are planned and validated without coupling the agent to physical tables or SQL dialects; policies are retrieved with evidence; and LangGraph coordinates the workflow.

> **Status:** portfolio/pilot MVP completed, with ongoing architecture and evaluation hardening.  
> **Positioning:** production-oriented, not production-ready.  
> **Data:** synthetic/fictitious only. HRIS access is read-only.

---

## Why this project matters

Enterprise AI becomes difficult when an answer must cross several boundaries at once: natural-language interpretation, structured operational data, policy knowledge, authorization, tool execution, deterministic validation, human review, evidence, provider independence and evaluation of probabilistic behavior.

PeopleOps makes those boundaries explicit and inspectable instead of hiding them behind a single "agent".

Representative questions include:

- Which contracts expire in the next 45 days?
- Why did this employee receive a lower net payroll amount this month?
- Which employees have recorded overtime that is not reflected in payroll?
- Can this employee request 15 vacation days in November under the applicable policy?
- Which policy version applied to this request in January?
- Is the available evidence sufficient, or should a human review the case?

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

Implementation/evaluation notes:

- [`evaluation/spikes/PHASE43.md`](evaluation/spikes/PHASE43.md) — model tool-calling for Query Programmer validation/submission, bounded rounds and protocol-complete tool handling.
- [`evaluation/spikes/PHASE44.md`](evaluation/spikes/PHASE44.md) — provider-neutral ConceptualQuery Programmer + MCP-compatible validation boundary + independent Senior Reviewer.

---

## Standalone MCP Server

`apps/reference-mcp-server` is a real MCP server built with the official Python SDK and **Streamable HTTP**. Its functional endpoint is `http://127.0.0.1:8001/mcp`.

It exposes generic tools rather than question-specific endpoints:

- `describe_conceptual_query_contract`
- `discover_catalog`
- `discover_scoped_catalog`
- `discover_capabilities`
- `discover_entities`
- `describe_entity`
- `discover_relationships`
- `temporal_context`
- `validate_conceptual_query`
- `execute_conceptual_query`

The server owns provider semantic mappings, physical introspection, scoped discovery, conceptual-query validation, source-specific translation, PostgreSQL `EXPLAIN`, bounded read-only execution, limits/timeouts, provider-neutral evidence and MCP audit. Payroll entities/fields are restricted and no HRIS write operation is advertised.

See [`apps/reference-mcp-server/README.md`](apps/reference-mcp-server/README.md).

---

## PeopleOps in action

The web application exposes the production-oriented analysis workflow through a usable HR workspace. Users can ask questions in natural language, review the synthesized answer, inspect supporting structured-data evidence, and navigate recent analyses, policy evidence and Human Review from the same interface.

![PeopleOps AI analysis workspace](docs/portfolio/assets/peopleops-analysis-workspace.webp)

The following example asks PeopleOps to **list the last 5 employees who joined the company**. The returned evidence contains only **4 matching active employees**. Rather than inventing a fifth row to satisfy the requested cardinality, PeopleOps explicitly reports that only four are available and displays the underlying records.

![PeopleOps AI evidence-driven response](docs/portfolio/assets/peopleops-last-five-employees.webp)

This illustrates an important product behavior: the LLM-generated synthesis is not treated as the source of truth. The answer is grounded in the structured result returned through the MCP path, and the UI exposes that evidence so the user can verify the conclusion. When the available data cannot satisfy the requested cardinality, the system reports the limitation instead of fabricating a result.

---

## Validated with OpenAI Codex as an external MCP client

The MCP boundary was manually validated from an **isolated OpenAI Codex CLI workspace outside the PeopleOps repository**.

The server was registered with Codex as an external MCP server:

```bash
codex mcp add local_mcp_8001 --url http://127.0.0.1:8001/mcp
```

In a fresh Codex session, natural-language requests caused Codex to invoke the registered MCP tools directly. The observed flow included:

```text
local_mcp_8001.discover_catalog
        ↓
local_mcp_8001.describe_conceptual_query_contract
        ↓
dynamic provider-neutral ConceptualQuery
        ↓
local_mcp_8001.execute_conceptual_query
```

Codex dynamically discovered the HR semantic model, composed scoped `hr:read` conceptual queries and used relationships exposed by the provider without depending on PeopleOps application code or the physical HRIS schema.

See [`docs/portfolio/MCP-CODEX-VALIDATION.md`](docs/portfolio/MCP-CODEX-VALIDATION.md).

---

## PeopleOps Semantic Run Viewer

A core engineering goal is to make agent behavior inspectable instead of treating a successful final answer as sufficient evidence.

Run the local viewer with:

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
- individual payroll explanation and period comparison;
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

### No semantic hardcoding
Natural-language meaning is not resolved with keyword lists, language-specific phrase tables or question-specific `if/elif` routing. A new wording should not require a new Python function unless it introduces a genuinely new capability.

### Capabilities, not question-specific tools
Tools represent general capabilities: discovery, conceptual querying, policy retrieval, validation and human review. The model composes entities, fields, filters, metrics, periods and relationships dynamically.

### LLM for semantics; deterministic code for invariants
LLMs may interpret, plan, choose tools, correlate evidence and synthesize. Deterministic code owns authorization/scopes, typed schemas, persistence, calculations, budgets, read-only enforcement, query validation, execution boundaries and reproducible tests.

### Facts, policies and inference remain distinct
**Facts** come from structured HR data through MCP. **Policies** come from versioned documents through Policy RAG. **Inference** is the model's interpretation based on those sources.

### Human governance is first-class
Sensitive, ambiguous, conflicting or insufficiently supported situations can enter durable `pending_human_review`, persist, receive an audited human decision and resume.

### Evidence before confidence
Missing or conflicting evidence is a valid result. The system should report limitations or abstain rather than invent support.

---

## Policy RAG

Policy knowledge belongs to PeopleOps, not to the HRIS MCP provider. The MVP uses **LlamaIndex + PostgreSQL/pgvector** and reuses engineering patterns validated in the public Enterprise RAG project.

```text
PDF / DOCX → parsing → chunking → metadata → embeddings
          → PostgreSQL / pgvector
          → retrieval + metadata filtering
          → evidence verification
          → grounded result / abstention
```

Policies support versions and effective dates so historical questions can retrieve the version applicable to the relevant date.

---

## Functional audit and schema independence

Every accepted analysis creates an `AnalysisInteraction` before LangGraph starts. A unique `request_id` identifies one execution and the durable audit stores observable outputs such as stages, semantic request, query plan, provider/catalog version, validations, structured results, policy sources, evidence, Human Review state, final response, warnings and safe error metadata.

Private model chain-of-thought is not persisted. The viewer exposes **observable prompts, messages, tool calls, tool results and application events**, not hidden reasoning.

Schema independence is tested rather than merely claimed. The same PeopleOps application logic is exercised against physically different HRIS schemas while only MCP-side source mapping and semantic metadata change.

```text
Schema A                  Schema B
Employee                  HR_PERSON
EmployeePayroll           PAY_MOVEMENT
OvertimeRecord            TIME_EVENT
```

---

## Evaluation

Evaluation is a product capability, not a final demo step.

The Slice 18 portfolio baseline includes:

| Dataset | Cases |
|---|---:|
| `integrated_v1` | 7 |
| `multilingual_antihardcoding_v1` | 12 |
| `payroll_deep_analysis_v1` | 4 |
| `policy_rag_v1` | 5 |
| `schema_independence_v1` | 2 |

Recorded integrated pass rates:

| Layer | Pass rate |
|---|---:|
| conceptual_mcp | 100% |
| final_answer | 100% |
| hitl | 100% |
| policy_rag | 100% |
| semantic | 100% |
| structured_data | 100% |
| workflow | 100% |

See [`evaluation/runs/slice18-portfolio.md`](evaluation/runs/slice18-portfolio.md).

Later evaluation phases investigate the Query Programmer and Senior Reviewer more deeply with real tool-calling, bounded retries/repair, protocol-complete tool handling, resumable runs and production-graph node-level inspection. Where objective ground truth exists, deterministic metrics take precedence; LLM-as-judge can complement but does not replace the deterministic baseline.

---

## Runtime and technology stack

The release contains three deployables and two isolated PostgreSQL services:

```text
peopleops-web            :3000
peopleops-api            :8000
reference-mcp-server     :8001
peopleops-db             :5436
synthetic-hris-db        :5437
```

| Concern | Technology |
|---|---|
| Backend / API | Python 3.11 + FastAPI |
| Contracts/configuration | Pydantic v2 + pydantic-settings |
| Agentic workflow / HITL | LangGraph |
| LLM / structured outputs / tool calling | OpenAI |
| Policy RAG | LlamaIndex |
| Structured HR integration | MCP |
| Persistence / vectors | PostgreSQL + pgvector |
| Migrations | Alembic |
| Testing / lint | Pytest + Ruff |
| Frontend | Next.js + React + TypeScript |
| Generic tracing/evaluation support | LangSmith |
| Domain-aware run inspection | PeopleOps Semantic Run Viewer |
| Local orchestration | Docker Compose + root Makefile |

`peopleops-api` receives PeopleOps DB settings, not HRIS credentials; `reference-mcp-server` receives HRIS settings, not PeopleOps DB credentials; the web receives neither credential set. The MVP is **single-tenant per instance**.

---

## Quickstart

Requirements: Docker with Compose, Python 3.11, Poetry and Node.js.

```bash
cp .env.example .env
cp apps/peopleops-web/.env.example apps/peopleops-web/.env.local

make build
make infra
make migrate
make migrate-hris
make seed-hris
make generate-policy-pdfs

# Run locally in separate terminals
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

## Security and scope boundaries

The public repository uses synthetic HR data and synthetic policies only. Controls include least-privilege database ownership, environment-based secrets, restricted payroll fields, scoped MCP requests, read-only HRIS operations, result limits/timeouts, safe logging and request correlation, provider-side validation/`EXPLAIN`, evidence preservation, prompt-injection defenses and durable Human Review.

The MVP does **not** aim to replace an HRIS, automate dismissals/promotions/sanctions, mutate payroll/HRIS records, provide definitive legal advice, publish proprietary ERP adapters or become a generic BI platform. A real BIZAG/SAP/Workday/customer integration belongs behind the MCP boundary.

---

## Portfolio positioning

PeopleOps AI is the **flagship technical project** in this portfolio because it brings together the capabilities needed to defend an enterprise agentic architecture end to end:

**dynamic HR intelligence + semantic MCP integration + Policy RAG + bounded agentic workflows + Human-in-the-loop + evaluation + low-level observability**

It is intended as public, defensible evidence for roles such as **AI Solutions Architect, Agentic AI Engineer, Generative AI Engineer, AI Technical Lead, and Solution / Software Architect**.

Its central engineering claim is not that an LLM can answer HR questions. It is that an enterprise AI system can be designed so its **semantics, integrations, tool use, validation, evidence, governance and failures are inspectable and testable**.

---

## Release material

- [`docs/portfolio/DEMO-SCRIPT.md`](docs/portfolio/DEMO-SCRIPT.md)
- [`docs/portfolio/PILOT-GUIDE.md`](docs/portfolio/PILOT-GUIDE.md)
- [`docs/portfolio/RELEASE-CHECKLIST.md`](docs/portfolio/RELEASE-CHECKLIST.md)
- [`docs/portfolio/MCP-CODEX-VALIDATION.md`](docs/portfolio/MCP-CODEX-VALIDATION.md)
- [`docs/portfolio/assets/README.md`](docs/portfolio/assets/README.md)
- [`evaluation/runs/slice18-portfolio.md`](evaluation/runs/slice18-portfolio.md)
- [`evaluation/spikes/semantic_run_viewer.py`](evaluation/spikes/semantic_run_viewer.py)

## License

A repository license will be selected before public release. Until a license file is committed, no license should be inferred from this README.
