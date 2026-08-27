# AGENTS.md --- PeopleOps AI Codex CLI Instructions

This file defines repository-level instructions for **Codex CLI** and
other coding agents working on PeopleOps AI.

These instructions are mandatory unless a more specific nested
`AGENTS.md` intentionally adds stricter local guidance. A nested file
must not weaken the architectural invariants defined here.

## 1. Mission

Implement **PeopleOps AI --- HR Intelligence Copilot** incrementally
according to the approved project documentation and slice
specifications.

The goal is not to maximize features. The goal is to produce a coherent,
testable, reproducible and defensible enterprise AI system that
demonstrates:

-   dynamic HR analysis;
-   MCP-based structured-data integration;
-   schema independence;
-   Policy RAG;
-   LangGraph orchestration;
-   Human-in-the-loop;
-   persistent evidence/audit;
-   reproducible evaluation;
-   production-oriented engineering.

Do not turn the project into a generic chatbot, generic BI system, full
HRIS, rules engine or collection of question-specific tools.

## 2. Mandatory reading order

Before implementing or materially modifying a slice, read the relevant
repository documentation in this order:

1.  `docs/proyecto-03-peopleops-ai-BRD.md`
2.  `docs/proyecto-03-peopleops-ai-PDD.md`
3.  `docs/proyecto-03-peopleops-ai-PRD.md`
4.  `docs/00-documentation-map.md`
5.  `docs/01-SPEC.md`
6.  `docs/02-REQ.md`
7.  `docs/03-ADR.md`
8.  `docs/04-PROC.md`
9.  `docs/05-DATA.md`
10. `docs/06-UI.md`
11. `docs/07-CTX.md`
12. `docs/08-SLICES-PLAN.md`
13. the detailed specification for the slice being implemented.

If the repository places these files at a different path, locate the
exact committed files rather than inventing replacements.

### Documentation precedence

When documents appear to conflict, use:

``` text
BRD → PDD → PRD → SPEC → REQ → ADR/PROC/DATA/UI → CTX → SLICES
```

A lower-level document must not reduce a mandatory requirement from a
higher-level document.

If a real contradiction cannot be resolved from the repository, **stop
and report it**. Do not silently choose the easier interpretation.

## 3. Work one slice at a time

The implementation roadmap is intentionally incremental.

When asked to implement Slice N:

1.  read the baseline documentation;
2.  read the detailed Slice N specification;
3.  inspect the current repository state;
4.  identify what previous slices already provide;
5.  implement only Slice N plus strictly necessary neutral
    infrastructure;
6.  add/update tests;
7.  run the relevant verification commands;
8.  report what changed, tests executed, results and any unresolved
    issue.

Do not proactively implement later slices.

Do not refactor unrelated code merely because a different design looks
cleaner.

Do not add frameworks, services or infrastructure for hypothetical
future needs.

## 4. Non-negotiable architecture invariants

The following are repository-level invariants.

### 4.1 MCP is the only integrated HRIS path

Required runtime path:

``` text
PeopleOps API
    ↓
HRDataGateway
    ↓
MCP Client
    ↓
Reference MCP Server
    ↓
Synthetic Reference HRIS
```

`peopleops-api` MUST NOT connect directly to the Synthetic Reference
HRIS.

There must be:

-   no direct HRIS DB credentials in `peopleops-api`;
-   no ORM models imported from the Synthetic HRIS into PeopleOps domain
    code;
-   no direct SQL execution from PeopleOps against the HRIS;
-   no silent fallback to direct DB access when MCP fails.

A correct answer produced through an MCP bypass is an architectural
failure.

### 4.2 The Synthetic Reference HRIS is not the PeopleOps contract

The synthetic HRIS is a fixture for development, tests, demo and ground
truth.

PeopleOps must not assume that a real HRIS has tables named `Employee`,
`EmployeePayroll`, `OvertimeRecord`, or any other physical fixture name.

Physical schema knowledge belongs on the MCP Server/source-adapter side.

### 4.3 Conceptual query, not physical SQL, is the PeopleOps contract

PeopleOps expresses **what it needs** through typed provider-neutral
structures.

The Reference MCP Server owns:

``` text
conceptual query
→ semantic validation
→ source mapping
→ PostgreSQL translation
→ physical validation
→ safe read-only execution
→ provider-neutral evidence
```

Never add raw-SQL escape hatches to make a test pass.

Never put physical table/column mappings in PeopleOps prompts.

### 4.4 Policy RAG belongs to PeopleOps

Policies are PeopleOps-owned knowledge.

The primary MVP path is:

``` text
Policy upload
→ PeopleOps API
→ LlamaIndex
→ PeopleOps knowledge store / pgvector
```

Do not route policy ingestion/retrieval through the HRIS MCP Server
merely for architectural symmetry.

### 4.5 Human Review must be durable

Human Review is not an in-memory callback.

A workflow may remain pending for minutes, hours or longer. Review
state, evidence snapshot and human decision must be persisted, and the
same analysis must be resumable.

### 4.6 AnalysisInteraction is functional persistence

Create `AnalysisInteraction` before LangGraph starts.

It is not equivalent to logging or tracing.

LangSmith may complement observability but must never become the only
store for:

-   analysis history;
-   evidence;
-   Human Review;
-   resume state;
-   user-visible execution status.

### 4.7 Facts, Policies and Inference are separate

Preserve provenance throughout state, persistence and API responses.

Do not silently transform:

-   model inference into a fact;
-   retrieved policy text into structured HR data;
-   structured HR data into a policy rule.

### 4.8 No automatic sensitive employment decisions

The MVP must not autonomously execute dismissal, promotion, hiring,
sanction, payroll modification or other material employment actions.

When governance requires Human Review, implement the review path rather
than an automatic effect.

## 5. Anti-hardcoding rules

These rules are especially important.

### Forbidden

Do not interpret natural language with keyword or phrase routing:

``` python
if "vacaciones" in question:
    route = "vacation"

if "payroll" in question or "nómina" in question:
    ...
```

Do not maintain per-language phrase lists.

Do not add a function/tool solely because a new wording appeared in a
test.

Do not create one agent per HR module.

Do not encode evaluation questions or expected answers into prompts,
routers, fixtures used by runtime logic, or special-case branches.

### Required approach

Natural-language understanding must use typed/structured model outputs.

Tools represent reusable capabilities.

The LLM may:

-   interpret;
-   plan;
-   select capabilities;
-   propose conceptual queries;
-   correlate evidence;
-   synthesize explanations.

Deterministic code must own:

-   schema validation;
-   authorization;
-   security;
-   persistence;
-   calculations;
-   row/result limits;
-   read-only enforcement;
-   objective invariants;
-   reproducible transformations.

### Legitimate constants are not semantic routing

Enums, API paths, DB field mappings inside the source-specific MCP
adapter, status codes, documented semantic metadata and deterministic
business fixtures may be constants.

The distinction is: constants may describe a contract or source; they
must not be used as a hidden phrase-to-intent engine.

If uncertain, prefer a typed contract and document the decision.

## 6. Confirmed implementation baseline and repository boundaries

Slice 00 closes the implementation baseline. Codex MUST use this stack
unless a later approved ADR explicitly changes it.

### 6.1 Confirmed stack

  Concern                                Confirmed technology
  -------------------------------------- -----------------------------------
  Backend runtime                        Python 3.11
  Python dependency management           Poetry
  API                                    FastAPI
  Configuration / typed contracts        Pydantic v2 + `pydantic-settings`
  Agentic orchestration / HITL           LangGraph
  LLM / structured outputs / tool use    OpenAI
  Policy RAG                             LlamaIndex
  Structured HR integration              MCP
  PeopleOps persistence                  PostgreSQL
  Vector persistence                     pgvector
  Reference HRIS persistence             PostgreSQL
  Database migrations                    Alembic
  Python tests                           Pytest
  Python lint / format                   Ruff
  Frontend                               Next.js + React + TypeScript
  Frontend routing                       Next.js App Router
  Frontend package manager               npm
  Agentic tracing / evaluation support   LangSmith
  Local orchestration                    Docker Compose
  Developer command interface            root Makefile

Do not substitute Vue, Vite, Laravel, Django, Node backend, CrewAI,
another RAG framework or another agent framework without an approved
architectural change.

### 6.2 Enterprise RAG as implementation reference

The public `enterprise-rag` project is a **reference implementation for
proven engineering patterns**, not an application architecture to copy.

Before implementing an equivalent capability, inspect and adapt proven
patterns where useful, especially for:

-   Docker/Compose organization;
-   root Makefile ergonomics and reproducible developer commands;
-   environment/configuration conventions;
-   PostgreSQL/pgvector setup;
-   LlamaIndex ingestion/retrieval/evaluation patterns;
-   testing conventions;
-   health checks and operational workflow.

Rule:

> Reuse proven engineering patterns, not application architecture.

Do not copy services only because Enterprise RAG uses them.

Specifically:

-   **LocalStack is not part of the PeopleOps baseline.** Enterprise RAG
    uses it to emulate AWS/S3 locally. Add S3/LocalStack only if a later
    approved requirement needs S3-compatible storage.
-   **Phoenix is not part of the PeopleOps baseline.** PeopleOps uses
    LangSmith for agentic tracing/evaluation support plus structured
    application logging and durable `AnalysisInteraction` for functional
    audit.
-   Do not add Redis unless a later slice proves it is needed for
    durability/resilience.

### 6.3 Physical architecture

Required local topology:

``` text
Browser
  │
  ▼
peopleops-web :3000
  │ HTTP
  ▼
peopleops-api :8000
  │
  ├── peopleops-db :5432 internal / :5436 host
  │
  └── HRDataGateway
          │
          ▼
       MCP Client
          │
          ▼
reference-mcp-server :8001
          │
          ▼
synthetic-hris-db :5432 internal / :5437 host
```

The `HRDataGateway → MCP Client` path becomes functional in its assigned
slices. Slice 00 must establish boundaries without implementing
later-slice behavior.

### 6.4 Docker Compose services

The baseline Compose project contains exactly these core services:

``` text
peopleops-web
peopleops-api
reference-mcp-server
peopleops-db
synthetic-hris-db
```

Default host ports:

  Service                    Host   Container
  ------------------------ ------ -----------
  `peopleops-web`            3000        3000
  `peopleops-api`            8000        8000
  `reference-mcp-server`     8001        8001
  `peopleops-db`             5436        5432
  `synthetic-hris-db`        5437        5432

Ports MUST remain configurable through environment variables.

Containers communicate through Compose service names and internal ports,
never through host `localhost`.

Use a Compose project name such as:

``` text
COMPOSE_PROJECT_NAME=peopleops-ai
```

### 6.5 Database ownership

PeopleOps application database:

``` text
service:  peopleops-db
database: peopleops
user:     peopleops_app
```

Only `peopleops-api` receives its credentials.

Synthetic HRIS database:

``` text
service:  synthetic-hris-db
database: synthetic_hris
user:     synthetic_hris_app
```

Only `reference-mcp-server` receives its credentials.

There MUST NOT be one application user with access to both databases.

For persistence tests use PostgreSQL, never SQLite as a convenience
replacement. Test databases/credentials must be isolated from
development data.

The MVP is **single-tenant per instance**. Do not add `tenant_id`,
schema-per-tenant, database switching or a multitenancy package without
a later ADR.

### 6.6 Canonical repository structure

Target structure:

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
│
├── synthetic-hris/
│   ├── migrations/
│   ├── seeds/
│   └── alternate-schema/
│
├── policies/
│   └── synthetic/
│
├── evaluation/
│   ├── cases/
│   ├── runs/
│   └── README.md
│
├── ops/
├── docs/
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
├── AGENTS.md
└── README.md
```

The exact internal Python module names may evolve as code is
implemented. The deployable boundaries and ownership rules may not.

Do not create a fourth administrative application in the MVP.

### 6.7 `peopleops-web`

Confirmed frontend:

-   Next.js;
-   React;
-   TypeScript;
-   App Router;
-   npm.

Environment:

``` text
apps/peopleops-web/.env.example
apps/peopleops-web/.env.local   # local only, gitignored
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

`peopleops-web` may communicate only with `peopleops-api`.

It MUST NOT communicate directly with:

-   Reference MCP Server;
-   Synthetic HRIS;
-   PeopleOps DB.

Do not put authoritative authorization/security rules only in frontend
code.

Slice 00 creates only the minimal runnable Next.js scaffold. Functional
UI belongs to Slices 14 and 15.

### 6.8 `peopleops-api`

Owns, as slices introduce them:

-   FastAPI API;
-   LangGraph;
-   OpenAI integration;
-   semantic interpretation/planning;
-   Policy RAG / LlamaIndex;
-   `AnalysisInteraction`;
-   Human Review;
-   HRDataGateway / MCP Client;
-   PeopleOps application persistence.

May access:

-   PeopleOps DB;
-   pgvector/knowledge store;
-   policy storage;
-   OpenAI;
-   Reference MCP Server;
-   LangSmith when enabled.

MUST NOT access Synthetic HRIS directly.

Local API health endpoint:

``` text
GET /api/v1/health
```

### 6.9 `reference-mcp-server`

Python 3.11 + Poetry deployable.

Owns, as slices introduce them:

-   source discovery;
-   semantic catalog;
-   conceptual-query validation;
-   source mapping;
-   PostgreSQL translation for the reference source;
-   physical-query validation;
-   read-only execution;
-   source-side authorization/scope;
-   provider-neutral evidence;
-   error normalization.

It connects only to `synthetic-hris-db`.

It does not need PeopleOps DB, LlamaIndex or a frontend.

For local orchestration it exposes a minimal HTTP health endpoint:

``` text
GET /health
```

The functional MCP transport/tools are introduced in their assigned
slices; health support does not authorize implementing discovery early.

### 6.10 CORS

Because the frontend and API are separate deployables, FastAPI must use
explicit CORS configuration.

Baseline local origin:

``` text
FRONTEND_URL=http://localhost:3000
```

Support `FRONTEND_URLS` if multiple explicit origins are required.

Do not use wildcard origins with credentials.

Verify OPTIONS/preflight as part of the relevant foundation/integration
tests.

### 6.11 Root Makefile

The root `Makefile` is the canonical developer interface. Codex should
prefer it over documenting long ad-hoc Poetry/npm/Docker commands.

Minimum targets:

``` text
make help
make install
make build
make up
make down
make restart
make ps
make logs
make lint
make format
make test
make test-unit
make test-integration
make health
make clean
```

Targets should delegate to Poetry, npm and Docker Compose. Keep shell
logic small and transparent.

Do not add targets for LocalStack, Phoenix, Redis or other services that
are not part of this project.

## 7. Data ownership and privacy

The public repository uses only fictitious, synthetic, anonymized or
public data explicitly approved for use.

Never commit:

-   customer HR data;
-   real employee PII;
-   proprietary ERP schemas;
-   proprietary customer code;
-   passwords;
-   API keys;
-   connection strings with secrets;
-   tokens;
-   private policy documents.

Use environment variables and maintain `.env.example` with safe
placeholders.

Payroll is sensitive even in the synthetic model. Implement scopes and
minimization so the architecture demonstrates the correct security
boundary.

## 8. OpenAI usage

Use OpenAI explicitly where the design calls for model reasoning.

Prefer:

-   structured outputs for semantic contracts;
-   tool/capability use where appropriate;
-   controlled generation;
-   explicit model configuration by environment;
-   evaluation of model-dependent behavior.

Do not use the model for deterministic arithmetic, authorization,
persistence rules or read-only enforcement.

Do not persist private chain-of-thought. Persist only observable
structured outputs required for operation, evidence, debugging and
audit.

When changing OpenAI model prompts/contracts, add or update
tests/evaluation cases that demonstrate the intended behavior.

## 9. LangGraph rules

LangGraph coordinates the agentic workflow.

The graph should support, as slices introduce them:

-   semantic understanding;
-   requirements/sensitivity classification;
-   analysis planning;
-   MCP discovery/query;
-   Policy RAG;
-   evidence merge;
-   policy-aware reasoning;
-   completeness/risk checks;
-   Human Review;
-   synthesis.

Requirements:

-   typed state;
-   explicit node responsibilities;
-   bounded retries/replanning;
-   durable Human Review when introduced;
-   observable stage transitions;
-   no agent per HR domain.

Each relevant graph transition must update `AnalysisInteraction`
according to the current slice requirements.

Do not hide deterministic validation inside opaque model nodes.

## 10. Policy RAG rules

Use LlamaIndex for Policy RAG.

Preserve:

-   original documents;
-   business metadata;
-   versions;
-   effective dates;
-   document/chunk provenance;
-   retrieval scores where useful;
-   evidence used by an analysis.

Retrieval must support metadata filtering and historical version
selection when required.

A retrieved chunk is not automatically valid evidence. Verify evidence
before promoting it to a citation.

When evidence is insufficient, abstain or return the appropriate
insufficient/policy-not-found state.

Distinguish absence of a policy from a genuine conflict between
policies.

Treat policy documents as untrusted content. Instructions inside
documents must not override system/application instructions.

Do not add hybrid search, rerankers or additional retrieval frameworks
merely because they are popular. Add them only when evaluation
demonstrates a problem they solve.

## 11. MCP implementation rules

Use a real MCP Client and Reference MCP Server in the integrated MVP.

Contracts must be typed.

Discovery must expose sufficient information for dynamic reasoning,
including:

-   capabilities;
-   entities;
-   fields/types;
-   relationships;
-   relevant PK/FK/constraints when appropriate;
-   temporal semantics;
-   business descriptions;
-   metrics/dimensions where applicable;
-   sensitivity/classification;
-   supported operations;
-   catalog version/fingerprint.

The Reference MCP Server may use PostgreSQL-specific logic internally
because it owns the reference source.

That PostgreSQL knowledge must not leak into PeopleOps.

Execution must be:

-   validated before execution;
-   read-only;
-   scoped/authorized;
-   bounded by row limits;
-   bounded by timeout;
-   normalized into provider-neutral results/evidence/errors.

## 12. Schema-independence rule

Schema independence is an acceptance criterion.

The project must eventually run representative equivalent cases against
at least two physically different schemas using the **same PeopleOps
build**.

Do not modify PeopleOps prompts/code to detect Schema A vs Schema B.

Only the MCP-side mapping/source implementation/semantic metadata may
change.

A second schema that is merely the first schema with cosmetic renames is
not a strong test; vary structure enough to demonstrate the boundary
meaningfully.

## 13. Persistence and audit rules

`request_id` identifies one analysis execution.

`conversation_id` groups related analyses.

A follow-up:

-   keeps the relevant `conversation_id`;
-   receives a new `request_id`;
-   must still retrieve current evidence rather than treating
    conversation context as evidence.

`stage_history` is logically append-only.

On failure, persist safe information including the current stage, error
type and safe detail.

Do not store chain-of-thought.

Do not mix Evaluation Dataset tables/files with `AnalysisInteraction`.

## 14. Evaluation rules

Evaluation must be reproducible and versioned.

Separate evaluation by layer:

-   semantic understanding;
-   conceptual query;
-   MCP;
-   Policy RAG;
-   workflow;
-   final answer.

Include:

-   deterministic ground truth;
-   multilingual cases;
-   negative cases;
-   insufficient-data cases;
-   policy-not-found/conflict cases;
-   authorization failures;
-   prompt-injection cases;
-   Human Review routing;
-   schema independence;
-   unsupported-claim checks.

Where deterministic ground truth is possible, use it as the primary
metric.

LLM-as-judge may complement deterministic metrics. It must not replace
them.

Do not silently change expected results to make a regression disappear.
If the expected result is wrong, document why before changing it.

Evaluation code must not auto-fix ingestion or runtime state in ways
that hide failures.

## 15. Testing requirements

Every slice must add the smallest useful set of tests proving its
Definition of Done.

Prefer:

-   unit tests for contracts, validators, calculations and security
    invariants;
-   integration tests across real boundaries introduced by the slice;
-   agentic/evaluation tests for model-dependent behavior;
-   MCP contract tests for compatible servers;
-   end-to-end tests only where they provide additional evidence.

Tests must test behavior, not implementation trivia.

Do not mock away the boundary that the slice is intended to prove. For
example, an MCP integration slice must include a real integration path
in addition to unit tests.

When fixing a bug, add a regression test when practical.

## 16. Failure handling

Expected external failures include:

-   OpenAI errors/timeouts;
-   MCP unavailable/timeout;
-   invalid conceptual query;
-   source validation failure;
-   database timeout;
-   Policy RAG failure;
-   invalid document upload;
-   Human Review resume failure.

Use bounded retries only for failures that are plausibly transient.

Never use infinite loops.

Never degrade an MCP failure into direct HRIS access.

Never turn missing evidence into an unsupported confident answer.

Errors exposed through APIs/logs must be useful but safe.

## 17. Dependency discipline

Avoid technology salad.

Before adding a dependency, ask:

1.  Which current slice requirement requires it?
2.  What professional capability or system behavior does it demonstrate?
3.  Can existing project dependencies solve the problem?
4.  Does it create another runtime service or operational burden?
5.  Is it required now, or only hypothetically later?

Do not add a dependency if the benefit is only speculative.

Examples:

-   Redis is not part of the baseline; add it only if a later approved
    slice proves durable checkpointing/resilience needs it.
-   LangSmith is the selected agentic tracing/evaluation support, but it
    is never functional persistence.
-   Structured application logs remain required independently of
    LangSmith.
-   `AnalysisInteraction` remains the durable functional audit.
-   Phoenix is not part of this project baseline.
-   LocalStack is not part of this project baseline.
-   Do not add another RAG framework alongside LlamaIndex.
-   Do not add another agent framework alongside LangGraph for the core
    workflow.

## 18. Code quality

Prefer clear, typed, boring code around the agentic core.

Use the confirmed baseline: Ruff for Python lint/format, Pytest for
Python tests, and the Next.js/npm scripts committed by `peopleops-web`
for frontend lint/build/test checks. Slice 00 must make these commands
reproducible through the root Makefile.

General rules:

-   small cohesive modules;
-   explicit types/contracts;
-   dependency injection at external boundaries where useful;
-   no duplicated domain constants across services without reason;
-   no dead code or speculative abstractions;
-   no broad exception swallowing;
-   safe structured logging;
-   configuration by environment;
-   comments explain decisions, not obvious syntax.

Do not introduce compatibility layers for code that does not exist yet.

## 19. Database and migration rules

Schema changes must be represented through the repository's migration
mechanism.

Seeds for the Synthetic Reference HRIS must be deterministic.

Synthetic scenarios should be coherent enough to support known ground
truth.

Do not make production runtime behavior depend on evaluation-only rows
or IDs unless those rows are explicitly part of the synthetic demo
dataset.

PeopleOps-owned data and HRIS-owned data must remain logically separated
even if local Docker uses the same PostgreSQL engine technology.

## 20. Documentation rules

Update documentation when implementation changes a documented contract
or when a slice requires documenting a new command/behavior.

Do not rewrite BRD/PDD/PRD to match an implementation shortcut.

If implementation reveals a genuine architectural inconsistency:

1.  stop the affected change;
2.  describe the inconsistency;
3.  identify impacted requirements/ADRs;
4.  propose the smallest documentation decision needed;
5.  wait for approval when the decision materially changes scope or
    architecture.

Record significant architectural exceptions as ADRs.

Keep `README.md` accurate. Do not document commands that have not been
implemented and tested.

## 21. Git and change discipline

Before editing:

-   inspect `git status`;
-   inspect the relevant files;
-   understand existing patterns.

During work:

-   keep changes scoped to the current slice;
-   do not overwrite unrelated user changes;
-   do not delete files merely to simplify implementation;
-   do not rewrite history;
-   do not expose secrets.

After work:

-   run the relevant tests/checks;
-   inspect `git diff`;
-   verify no accidental files/secrets were added.

Do not commit or push unless explicitly instructed to do so.

If asked to commit, use a concise commit message that names the
slice/capability.

## 22. Codex execution protocol

For each requested implementation slice, follow this protocol.

### Step 1 --- Orient

Report briefly:

-   current branch/status;
-   slice being implemented;
-   dependencies already present;
-   relevant requirements;
-   tests/verification you expect to run.

Do not produce a long speculative plan if the slice specification
already defines the work.

### Step 2 --- Inspect

Read the implementation and tests that the slice depends on.

Reuse existing patterns where they are sound.

Do not assume a file exists because a design document mentions it.

### Step 3 --- Implement

Make the smallest coherent implementation that satisfies the slice.

Keep architecture boundaries explicit.

If a decision is reversible and local, choose the simplest option
consistent with the docs.

If a decision changes architecture, scope, security or public contracts,
stop and report it rather than silently deciding.

### Step 4 --- Verify

Run the relevant:

-   formatter/linter;
-   unit tests;
-   integration tests;
-   evaluation subset;
-   build/health checks.

If a check cannot run, state exactly why. Do not claim success without
execution evidence.

### Step 5 --- Review

Inspect the diff for:

-   MCP bypass;
-   semantic hardcoding;
-   physical-schema leakage;
-   secrets;
-   unbounded retries;
-   missing audit updates;
-   missing tests;
-   scope creep.

### Step 6 --- Report

End with a compact implementation report:

``` text
Slice:
Status:

Implemented:
- ...

Tests/checks:
- command → result

Evaluation:
- artifact/metrics, if applicable

Architecture checks:
- MCP boundary: OK / N/A
- semantic hardcoding: none found
- physical schema leakage into PeopleOps: none found
- secrets: none found

Remaining:
- ...
```

Do not mark the slice complete if its Definition of Done is not
satisfied.

## 23. Stop conditions --- ask before proceeding

Stop and request clarification/approval when a requested change would:

-   bypass MCP;
-   add direct PeopleOps→HRIS access;
-   introduce language keyword routing;
-   require a new question-specific function;
-   weaken read-only behavior;
-   automate a sensitive employment decision;
-   introduce real/customer data or proprietary code;
-   change a MUST requirement;
-   contradict an approved ADR;
-   materially change a public API/contract outside the current slice;
-   add a major framework/runtime service not justified by the current
    slice;
-   require destructive migration/data loss;
-   require committing/pushing when that was not requested.

For ordinary local implementation details that are already constrained
by the docs, proceed without unnecessary questions.

## 24. Definition of repository-level non-compliance

Treat the implementation as non-compliant if any of these are true:

-   it answers correctly but bypasses MCP;
-   it uses keyword/phrase routing;
-   it creates a function per wording/question;
-   PeopleOps knows physical HRIS tables/dialects;
-   MCP failure activates direct DB fallback;
-   Human Review exists only in process memory;
-   LangSmith is the sole functional audit;
-   unverified policy chunks are presented as evidence;
-   payroll/HRIS writes are enabled in the MVP;
-   schema independence cannot be demonstrated.

## 25. Current implementation order

Follow the approved slice sequence:

``` text
00 Repository Foundation & Guardrails
01 PeopleOps Application Persistence
02 Synthetic Reference HRIS
03 Reference MCP Server: Discovery
04 MCP Client & HRDataGateway
05 Conceptual Query Contract & MCP Execution
06 Structured HR Analysis Baseline
07 Policy Knowledge Ingestion
08 Policy RAG Retrieval & Evaluation Baseline
09 Combined Data + Policy Workflow
10 Human-in-the-loop
11 Payroll Deep Analysis & Reconciliation
12 Multilingual & Anti-Hardcoding Regression
13 MCP Contract & Schema Independence
14 PeopleOps Web: Analysis & Evidence
15 PeopleOps Web: Policies & Human Review
16 Integrated Evaluation & Observability
17 Security & Failure Hardening
18 Portfolio / Pilot Release
```

Do not treat the existence of a later slice as permission to implement
it early.

## 26. Final rule

When in doubt, optimize for:

**architectural evidence, correctness, testability, reproducibility and
completion --- not feature count.**

A smaller implementation that clearly proves the intended enterprise AI
architecture is preferable to a larger implementation that weakens the
boundaries or cannot be evaluated.
