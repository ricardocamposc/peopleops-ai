# PeopleOps AI --- HR Intelligence Copilot

> **Policy-aware, agentic HR intelligence over structured HR data and
> internal policies, with evidence, schema-independent MCP integration,
> and Human-in-the-loop governance.**

PeopleOps AI is a portfolio-oriented enterprise AI application for Human
Resources. It is designed to answer and investigate HR questions by
combining structured HR data, payroll, attendance, contracts,
vacation/leave information, internal policies and procedures, and human
review when a situation is sensitive or insufficiently supported.

The project is intentionally more than a document chatbot and more than
a fixed catalog of HR functions. Natural-language requests are
interpreted into typed semantic structures, the available HR model is
discovered dynamically through MCP, conceptual queries are built without
depending on physical tables or SQL dialects, policies are retrieved
with evidence, and LangGraph coordinates the analysis workflow.

> **Project status:** Slice 00 foundation implemented; business slices remain pending.\
> This repository is **production-oriented**, not claimed to be
> production-ready.

## Why this project exists

HR teams commonly work with information distributed across HRIS/ERP
systems, payroll, attendance, contracts, vacation and leave records,
policies, procedures and documents. A useful answer often requires
combining several of these sources while preserving evidence and human
control.

PeopleOps AI explores an architecture in which an AI application can act
as an intelligence layer over those systems without replacing the HRIS
and without coupling the agentic layer to one proprietary schema.

Representative questions include:

-   Which contracts expire in the next 45 days?
-   Can this employee request 15 vacation days in November?
-   Why did this employee receive a lower net payroll amount this month?
-   Which employees have recorded overtime that is not correctly
    reflected in payroll?
-   Which employees have contracts close to expiration and pending
    vacation?
-   Which policy was applicable to this request in January?
-   Is the available evidence sufficient, or should a human review the
    case?

## Core architectural idea

``` text
HR User
   ↓
PeopleOps Web
   ↓ HTTPS
PeopleOps API
   ├── LangGraph / OpenAI
   ├── Policy RAG / LlamaIndex
   ├── AnalysisInteraction / Human Review
   ├── PeopleOps Data
   └── HRDataGateway
          ↓
       MCP Client
          ↓
================ MCP BOUNDARY ================
          ↓
Reference MCP Server
   ├── Capability & schema discovery
   ├── Semantic metadata
   ├── Conceptual-query validation
   ├── Source-specific translation
   ├── Read-only guardrails
   └── Evidence
          ↓
Synthetic Reference HRIS
```

The **MCP boundary is mandatory in the MVP**. `peopleops-api` must never
access the Synthetic Reference HRIS directly.

PeopleOps expresses **what information it needs** through typed
conceptual queries. The MCP Server knows **how the connected source
represents and retrieves that information**.

This separation is intended to make the following substitution possible
without rewriting the main agentic layer:

``` text
Reference MCP Server + Synthetic Reference HRIS
                    ↓ replace
Customer MCP Server + Real ERP / HRIS
```

Real BIZAG, SAP, Workday, Dynamics or customer-specific adapters are
future integrations and are not required for the public MVP.

## Slice 00 local setup

Slice 00 provides the three deployable scaffolds, two isolated PostgreSQL
services, explicit CORS, health endpoints and reproducible root commands.
It intentionally contains no HR models, migrations, MCP tools, analysis,
RAG, LangGraph, Human Review or functional business UI.

Requirements: Docker with Compose, Python 3.11, Poetry and Node.js. The
frontend uses npm, bundled with Node.js.

```bash
cp .env.example .env
make build
make up
make health
make lint
make test
make down
```

The default host ports are web `3000`, API `8000`, Reference MCP Server
`8001`, PeopleOps PostgreSQL `5436` and Synthetic HRIS PostgreSQL `5437`.
They can be overridden in `.env`. Containers use Compose service names
and internal PostgreSQL port `5432`.

Ownership is intentionally separate: `peopleops-api` receives only
PeopleOps database settings, `reference-mcp-server` receives only
Synthetic HRIS settings, and the web receives only the public API URL.
The databases are empty infrastructure in this slice; no migrations or
seeders are run.

## What the MVP demonstrates

The target MVP demonstrates these capabilities:

-   natural-language HR analysis;
-   multilingual semantic understanding without language-specific
    routing;
-   dynamic MCP capability/schema/relationship/semantic discovery;
-   provider-neutral conceptual queries;
-   safe read-only structured-data execution;
-   employee, contract, attendance, overtime, vacation, leave and
    payroll analysis;
-   individual payroll explanation and period comparison;
-   Attendance/Overtime ↔ Payroll reconciliation;
-   version-aware Policy RAG;
-   evidence verification and abstention;
-   combined structured-data + policy reasoning;
-   durable Human-in-the-loop workflows;
-   persistent functional audit through `AnalysisInteraction`;
-   MCP contract testing;
-   schema-independence testing;
-   reproducible multi-layer evaluation.

## Key design principles

### 1. No semantic hardcoding

Natural-language meaning must not be resolved with keyword lists,
language-specific phrase tables or `if/elif` routing.

``` python
# Not allowed
if "vacation" in question:
    ...
```

Language understanding must produce typed structured outputs. A new
wording must not require a new Python function unless it introduces a
genuinely new system capability.

### 2. Capabilities, not question-specific tools

Tools and interfaces represent general capabilities such as model
discovery, structured-data querying, policy retrieval and human review.
The concrete plan, filters, metrics, relationships and periods are
composed dynamically.

### 3. LLM for semantics; deterministic code for invariants

LLMs may interpret requests, plan, select capabilities, correlate
evidence and synthesize explanations.

Deterministic code owns authorization, schemas, persistence,
calculations, limits, read-only enforcement, security validation and
other reproducible invariants.

### 4. Facts, Policies and Inference remain distinct

A response must preserve provenance:

-   **Facts** come from structured HR data through MCP.
-   **Policies** come from versioned documents retrieved by PeopleOps
    Policy RAG.
-   **Inference** is the model's interpretation or recommendation based
    on that evidence.

These categories must not be silently merged.

### 5. Human governance is a first-class workflow

Sensitive, ambiguous, conflicting or insufficiently supported situations
may enter `pending_human_review`. Review is durable: the workflow can
pause, persist, receive an audited human decision and resume without
creating a new functional identity for the same analysis.

### 6. Evidence before confidence

Structured results and policy claims must remain traceable to their
sources. Missing or conflicting evidence is a valid outcome. The system
must abstain rather than invent support.

## Policy RAG

Policy knowledge belongs to PeopleOps rather than to the HRIS MCP
provider.

The MVP uses **LlamaIndex** with PostgreSQL/pgvector and follows
patterns already validated in the Enterprise RAG project:

``` text
PDF / DOCX
   ↓
Parsing
   ↓
Chunking
   ↓
Business metadata
   ↓
Embeddings
   ↓
PostgreSQL / pgvector
   ↓
Retrieval + metadata filtering
   ↓
Evidence verification
   ↓
Grounded result / abstention
```

Policies support versions and effective dates. Historical questions must
retrieve the policy version applicable to the relevant date.

The synthetic corpus is expected to include policies/procedures for
vacation, leave, attendance, overtime, payroll processing, contract
renewal, remote work, employee documentation, HR data privacy and
approval rules.

## Agentic workflow

The target LangGraph workflow coordinates:

``` text
Request
  ↓
Semantic understanding
  ↓
Requirements / sensitivity
  ↓
Analysis planning
  ↓
┌─────────────────────┬────────────────────┐
│ Structured HR data  │ Policy retrieval   │
│ via MCP             │ when required      │
└──────────┬──────────┴──────────┬─────────┘
           ↓
      Evidence merge
           ↓
   Policy-aware reasoning
           ↓
   Risk / completeness check
           ↓
      ┌────┴────┐
      │         │
 safe answer   Human Review
      │         ↓
      │       resume
      └────┬────┘
           ↓
        synthesis
```

Loops and replanning are deliberately bounded.

## Functional audit: AnalysisInteraction

Every accepted analysis creates an `AnalysisInteraction` **before
LangGraph starts**.

A unique `request_id` identifies one execution. Related follow-up
requests may share a `conversation_id`, but every follow-up receives a
new `request_id`.

The durable audit records observable structured outputs such as:

-   status and current stage;
-   append-only logical stage history;
-   semantic request and analysis goal;
-   query plan/candidate;
-   provider and catalog version;
-   validation and structured result;
-   policy sources and versions;
-   evidence;
-   Human Review state;
-   final response and warnings;
-   latency/model metadata;
-   safe error information.

Private model chain-of-thought is never stored. LangSmith may complement
technical observability, but it is not the functional store for analysis
history, evidence or Human Review.

## Synthetic Reference HRIS

The public project uses only fictitious/synthetic HR data.

The reference HRIS contains enough information to create deterministic
ground-truth scenarios around:

-   employees and organization;
-   contracts;
-   attendance and incidents;
-   overtime;
-   vacation balances and requests;
-   leave;
-   payroll periods;
-   employee payroll;
-   payroll concepts/items.

These physical entities are fixtures for development and testing. **They
are not the PeopleOps data contract.**

## Schema independence

A core architectural claim must be demonstrated, not merely documented.

A representative evaluation subset will run against two physically
different HRIS schemas, for example:

``` text
Schema A                  Schema B
Employee                  HR_PERSON
EmployeePayroll           PAY_MOVEMENT
OvertimeRecord            TIME_EVENT
```

The PeopleOps application and its agentic logic must remain unchanged.
Only the MCP-side source mapping/semantic metadata changes.

## Physical architecture and runtime services

The implementation baseline is deliberately explicit:

``` text
Browser
  │
  ▼
peopleops-web :3000
Next.js + TypeScript
  │ HTTP
  ▼
peopleops-api :8000
FastAPI + LangGraph + OpenAI + LlamaIndex
  │
  ├── peopleops-db
  │     PostgreSQL + pgvector
  │     host :5436 / container :5432
  │
  └── HRDataGateway
          │
          ▼
       MCP Client
          │
          ▼
reference-mcp-server :8001
Python + MCP
          │
          ▼
synthetic-hris-db
PostgreSQL
host :5437 / container :5432
```

The local Docker Compose baseline contains five core services:

``` text
peopleops-web
peopleops-api
reference-mcp-server
peopleops-db
synthetic-hris-db
```

`peopleops-api` never receives Synthetic HRIS database credentials.
`reference-mcp-server` never receives PeopleOps database credentials.
The web application receives neither.

## Confirmed technology stack

  Concern                                Technology
  -------------------------------------- -----------------------------------
  Backend runtime                        Python 3.11
  Python dependencies                    Poetry
  API                                    FastAPI
  Typed configuration/contracts          Pydantic v2 + `pydantic-settings`
  Agentic workflow / HITL                LangGraph
  LLM / structured outputs / tool use    OpenAI
  Policy RAG                             LlamaIndex
  Structured HR integration              MCP
  PeopleOps persistence                  PostgreSQL
  Vector persistence                     pgvector
  Reference HRIS                         PostgreSQL
  Migrations                             Alembic
  Python testing                         Pytest
  Python lint / format                   Ruff
  Frontend                               Next.js + React + TypeScript
  Frontend routing                       App Router
  Frontend package manager               npm
  Agentic tracing / evaluation support   LangSmith
  Local orchestration                    Docker Compose
  Developer workflow                     root Makefile

The MVP is **single-tenant per instance**. Multi-tenancy is
intentionally not introduced into the public MVP unless a later ADR
establishes a concrete requirement.

## Enterprise RAG as engineering reference

PeopleOps AI reuses **proven engineering patterns** from the public
Enterprise RAG implementation where they fit, especially:

-   Docker/Compose organization;
-   Makefile ergonomics;
-   environment/configuration conventions;
-   PostgreSQL/pgvector setup;
-   LlamaIndex ingestion and retrieval patterns;
-   evaluation structure;
-   testing and health-check patterns.

It does **not** copy Enterprise RAG's application architecture.

In particular:

-   LocalStack is not part of the PeopleOps baseline; in Enterprise RAG
    it supports local AWS/S3 emulation.
-   Phoenix is not part of the PeopleOps baseline.
-   PeopleOps uses LangSmith for agentic tracing/evaluation support,
    structured application logging for operational diagnostics, and
    `AnalysisInteraction` as durable functional audit.
-   Redis is not included unless a later slice demonstrates a concrete
    need.

The rule is:

> **Reuse proven engineering patterns, not application architecture.**

## Repository layout

The target monorepo structure is:

``` text
peopleops-ai/
├── apps/
│   ├── peopleops-api/
│   │   ├── src/
│   │   ├── tests/
│   │   ├── alembic/
│   │   ├── pyproject.toml
│   │   ├── poetry.lock
│   │   ├── Dockerfile
│   │   └── .env.example
│   │
│   ├── peopleops-web/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   ├── public/
│   │   ├── package.json
│   │   ├── package-lock.json
│   │   ├── Dockerfile
│   │   └── .env.example
│   │
│   └── reference-mcp-server/
│       ├── src/
│       ├── tests/
│       ├── pyproject.toml
│       ├── poetry.lock
│       ├── Dockerfile
│       └── .env.example
│
├── packages/
│   ├── contracts/
│   └── shared/
├── synthetic-hris/
│   ├── migrations/
│   ├── seeds/
│   └── alternate-schema/
├── policies/
│   └── synthetic/
├── evaluation/
│   ├── cases/
│   ├── runs/
│   └── README.md
├── ops/
├── docs/
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
├── AGENTS.md
└── README.md
```

Internal modules may evolve, but the three deployable boundaries and
database ownership rules are architectural invariants.

## Database ownership

PeopleOps application data:

``` text
service:  peopleops-db
database: peopleops
user:     peopleops_app
host port: 5436
```

Synthetic HRIS data:

``` text
service:  synthetic-hris-db
database: synthetic_hris
user:     synthetic_hris_app
host port: 5437
```

Containers use the Compose service names and PostgreSQL internal port
`5432`.

Passwords are local environment secrets and are never committed.

## Frontend baseline

`peopleops-web` uses:

``` text
Next.js
React
TypeScript
App Router
npm
```

Local frontend port:

``` text
http://localhost:3000
```

Frontend environment:

``` text
apps/peopleops-web/.env.example
apps/peopleops-web/.env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

The frontend communicates only with `peopleops-api`. It does not connect
directly to MCP or either database.

Slices 14 and 15 implement the functional analysis, evidence, policy and
Human Review interfaces. Slice 00 only establishes a runnable frontend
foundation.

## Local development

Docker Compose and the root Makefile are the canonical developer
workflow.

Initial setup:

``` bash
cp .env.example .env
cp apps/peopleops-web/.env.example apps/peopleops-web/.env.local
```

The expected operational interface is:

``` bash
make help
make install
make build
make up
make ps
make health
make lint
make test
make down
```

Additional baseline targets:

``` text
make restart
make logs
make format
make test-unit
make test-integration
make clean
```

Default local endpoints:

``` text
PeopleOps Web:        http://localhost:3000
PeopleOps API health: http://localhost:8000/api/v1/health
Reference MCP health: http://localhost:8001/health
PeopleOps PostgreSQL: localhost:5436
Synthetic HRIS DB:    localhost:5437
```

The Makefile should delegate to Poetry, npm and Docker Compose rather
than duplicate complex logic in shell.

Do not add LocalStack, Phoenix, Redis or another runtime service to the
baseline without an approved requirement/ADR.

## Evaluation strategy

Evaluation is a product capability, not a final demo-only step. The
suite is expected to separate failures by layer:

-   semantic understanding;
-   conceptual query correctness;
-   MCP discovery/contract/execution;
-   Policy RAG retrieval and version correctness;
-   evidence/citation validity;
-   abstention;
-   workflow routing and bounded recovery;
-   Human Review routing;
-   multilingual consistency;
-   unsupported claims;
-   final-answer fact/rule/inference coverage;
-   schema independence.

Where objective ground truth exists, deterministic metrics take
precedence. LLM-as-judge may complement those metrics but must not
replace the deterministic baseline.

Evaluation cases and expected ground truth are separate from real
`AnalysisInteraction` execution records.

## Security and privacy

The public repository must use synthetic data and synthetic policies
only.

The MVP is read-only with respect to the HRIS. Security controls include
least privilege, environment-based secrets, payroll sensitivity/scoping,
result limits, timeouts, safe logging, request correlation,
untrusted-document handling, prompt-injection defenses and Human Review.

The repository must never contain customer data, proprietary customer
schemas, private ERP code or credentials.

## Local development

The implementation is designed to be reproducible through
Docker/Compose. As the repository is implemented, the canonical
quickstart will be maintained here.

Expected high-level flow:

``` bash
cp .env.example .env

# Build/start the required services.
docker compose up --build

# Run the repository test suite.
# The exact canonical command will be documented once Slice 00 establishes it.
```

Do not infer missing commands from this README. Until the foundation
slice defines them, use the commands committed in the repository.

## Implementation roadmap

Development is organized into incremental slices:

``` text
00  Repository Foundation & Guardrails
01  PeopleOps Application Persistence
02  Synthetic Reference HRIS
03  Reference MCP Server: Discovery
04  MCP Client & HRDataGateway
05  Conceptual Query Contract & MCP Execution
06  Structured HR Analysis Baseline
07  Policy Knowledge Ingestion
08  Policy RAG Retrieval & Evaluation Baseline
09  Combined Data + Policy Workflow
10  Human-in-the-loop
11  Payroll Deep Analysis & Reconciliation
12  Multilingual & Anti-Hardcoding Regression
13  MCP Contract & Schema Independence
14  PeopleOps Web: Analysis & Evidence
15  PeopleOps Web: Policies & Human Review
16  Integrated Evaluation & Observability
17  Security & Failure Hardening
18  Portfolio / Pilot Release
```

Each slice has its own specification and Definition of Done.
Implementation should not pull features from later slices forward unless
neutral infrastructure is strictly necessary.

## Documentation

The repository documentation has an explicit precedence:

``` text
BRD
 ↓
PDD
 ↓
PRD
 ↓
SPEC
 ↓
REQ
 ↓
ADR / PROC / DATA / UI
 ↓
CTX
 ↓
SLICES
```

A lower-level document cannot weaken a mandatory requirement from a
higher-level source.

Codex CLI must start with `AGENTS.md` and the documentation map before
modifying the project.

## MVP non-compliance conditions

The MVP is **not compliant** if it:

-   answers correctly by bypassing MCP;
-   uses keyword/phrase routing;
-   creates functions solely for individual question wordings;
-   lets PeopleOps depend on physical HRIS tables or SQL dialects;
-   uses a silent direct-DB fallback after MCP failure;
-   stores Human Review only in process memory;
-   uses LangSmith as the only functional audit;
-   cites unverified policy evidence;
-   writes to payroll/HRIS;
-   fails to demonstrate schema independence.

## Scope boundaries

The MVP does **not** aim to replace an HRIS, automate
dismissals/promotions/sanctions, write payroll, implement full
recruiting/performance management, provide definitive legal advice,
publish proprietary ERP adapters, or become a generic BI platform.

A real BIZAG/SAP/Workday/customer integration belongs after the
reference MVP and should live behind the MCP boundary.

## Portfolio intent

PeopleOps AI demonstrates **domain-specific enterprise AI architecture
in a sensitive HR domain**:

**dynamic structured HR data + policy knowledge + reasoning + human
governance**

The project is intended to provide public, defensible evidence of AI
Solutions Architecture, Agentic AI, LangGraph, LlamaIndex, OpenAI
structured outputs/tool use, MCP integration, RAG evaluation,
Human-in-the-loop, auditability, security boundaries and
production-oriented engineering.

## License

A repository license will be selected before public release. Until a
license file is committed, no license should be inferred from this
README.
