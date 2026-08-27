# PeopleOps AI — Architectural Decision Records (ADR)

# ADR-001 — MCP as Mandatory Structured Data Boundary
**Status:** Accepted

## Context
Los ERP/HRIS difieren en schemas, DBMS, customizaciones y APIs.

## Decision
Todo acceso estructurado integrado atraviesa:
`PeopleOps API → MCP Client → Reference MCP Server → Synthetic Reference HRIS`.

## Rejected
- DB directa desde PeopleOps.
- LocalProvider paralelo productivo.
- MCP solo como futura mejora.

## Consequences
+ desacoplamiento y adapters sustituibles.
- mayor complejidad inicial.

---

# ADR-002 — Conceptual Query Contract instead of Physical SQL
**Status:** Accepted

PeopleOps produce query conceptual tipado. MCP valida, mapea, traduce, valida físicamente y ejecuta.

Motivo: SQL PostgreSQL desde PeopleOps trasladaría el acoplamiento al cliente.

---

# ADR-003 — Discovery + Semantic Metadata
**Status:** Accepted

MCP debe exponer schema físico, relaciones, capabilities, semantic metadata, sensibilidad y operaciones.

Motivo: nombres legacy como `RH_MOVI` o `FLGEST` no son semánticamente suficientes.

---

# ADR-004 — No Semantic Keyword Routing
**Status:** Accepted

Interpretación con LLM + structured outputs.

Prohibido:
- keywords;
- phrase lists;
- condicionales por idioma;
- función por pregunta.

---

# ADR-005 — Reuse Enterprise RAG proven patterns
**Status:** Accepted

PeopleOps reutiliza conceptualmente:
- ingestion;
- parsing/chunking;
- metadata;
- PostgreSQL/pgvector;
- retrieval filters;
- evidence verifier;
- abstention;
- evaluation dataset;
- deterministic baseline;
- optional LLM judge.

Se adapta a versionado/vigencia HR y policy-aware reasoning.

---

# ADR-006 — Separate PeopleOps and HRIS Data Ownership
**Status:** Accepted

HRIS owns:
employees, contracts, attendance, overtime, vacations, payroll.

PeopleOps owns:
conversations, AnalysisInteraction, policies, vectors, ingestion jobs, Human Review.

---

# ADR-007 — Durable AnalysisInteraction
**Status:** Accepted

Crear antes del workflow y actualizar current_stage, stage_history, snapshots, evidence, errors y response.

LangSmith complementa; no sustituye.

---

# ADR-008 — Human Review as Durable Workflow State
**Status:** Accepted

Persistir Human Review y permitir pause/resume.

---

# ADR-009 — Three Deployables in One Monorepo
**Status:** Accepted

```text
apps/
  peopleops-api/
  peopleops-web/
  reference-mcp-server/
```

Un repo, procesos/despliegues separados.

---

# ADR-010 — No MCP Admin Frontend in MVP
**Status:** Accepted

Reference MCP Server es backend-only. Configuración mediante entorno/config/metadata fixtures y herramientas técnicas.

Una futura Integration Console queda fuera.

---

# ADR-011 — Synthetic HRIS is Fixture, Not Product Contract
**Status:** Accepted

El contrato real se basa en:
capabilities + metadata + relationships + conceptual query + evidence.

---

# ADR-012 — Deterministic Guardrails around Agentic Reasoning
**Status:** Accepted

LLM:
- entiende;
- planifica;
- propone;
- sintetiza.

Código:
- valida;
- autoriza;
- limita;
- calcula;
- persiste;
- ejecuta guardrails.
