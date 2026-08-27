# PeopleOps AI — System Context and Physical Architecture (CTX)

**Consolida:** SPEC, REQ, ADR, PROC, DATA y UI.

## 1. Referencias
- `01-SPEC.md`
- `02-REQ.md`
- `03-ADR.md`
- `04-PROC.md`
- `05-DATA.md`
- `06-UI.md`

## 2. System Context
```text
HR User
  ↓
PeopleOps Web
  ↓ HTTPS
PeopleOps API
  ├─ LangGraph / OpenAI
  ├─ LlamaIndex / Policy RAG
  ├─ AnalysisInteraction / HITL
  ├────────────→ PeopleOps Data
  └─ HRDataGateway
       ↓
     MCP Client
       ↓
================ MCP BOUNDARY ================
       ↓
Reference MCP Server
  ├─ Discovery
  ├─ Semantic Metadata
  ├─ Query Validation
  ├─ Translation
  ├─ Guardrails
  └─ Evidence
       ↓ read-only
Synthetic Reference HRIS
```

## 3. Deployables

### peopleops-web
Conecta solo con peopleops-api.

No conecta directamente con MCP, HRIS o DB.

### peopleops-api
Conecta con:
- PeopleOps DB;
- pgvector/knowledge store;
- file storage;
- OpenAI;
- Reference MCP Server;
- LangSmith opcional.

No conecta directamente con Synthetic HRIS.

### reference-mcp-server
Conecta con:
- Synthetic HRIS.

No necesita:
- PeopleOps DB;
- LlamaIndex;
- frontend PeopleOps.

## 4. Persistencia

### PeopleOps-owned
- conversations;
- AnalysisInteraction;
- HumanReviewRequest;
- PolicyDocument;
- PolicyVersion;
- chunks/embeddings;
- IngestionJob.

### HRIS-owned
- employees;
- contracts;
- attendance;
- overtime;
- vacation;
- leave;
- payroll.

## 5. Trust Boundaries
```text
Browser
 ↓ HTTPS
PeopleOps boundary
 ↓ authenticated MCP
Integration boundary
 ↓ least-privilege source connection
ERP/HRIS boundary
```

## 6. Monorepo recomendado
```text
peopleops-ai/
├── apps/
│   ├── peopleops-api/
│   ├── peopleops-web/
│   └── reference-mcp-server/
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
├── docs/
├── docker-compose.yml
├── .env.example
└── README.md
```

La estructura exacta puede variar si conserva boundaries y deployables.

## 7. Docker Topology
Servicios mínimos:
- peopleops-web;
- peopleops-api;
- reference-mcp-server;
- peopleops-db;
- synthetic-hris-db.

Redis no es obligatorio; solo incorporar si checkpointing/resilience lo justifica.

## 8. MCP Boundary
```text
PeopleOps
 ↓ conceptual request
MCP Server
 ↓ source-specific translation
ERP/HRIS
```

Sustitución futura:
```text
Reference MCP Server + Synthetic HRIS
                 ↓ replace
Customer MCP Server + Real ERP
```
PeopleOps no cambia.

## 9. Policy Boundary
```text
Policy Owner
 ↓
PeopleOps Web
 ↓
PeopleOps API
 ↓
LlamaIndex
 ↓
PeopleOps Knowledge Store
```

Policies no se obtienen del HRIS MCP como mecanismo principal del MVP.

## 10. Runtime Analysis
```text
Question
 ↓
AnalysisInteraction created
 ↓
LangGraph
 ├─ MCP discovery/query
 └─ Policy retrieval
 ↓
Evidence merge
 ↓
Risk/completeness
 ↓
Human Review if needed
 ↓
Final response
```

## 11. External Dependencies
Requeridos:
- OpenAI;
- PostgreSQL;
- pgvector;
- LlamaIndex;
- LangGraph;
- MCP libraries;
- FastAPI.

Opcional:
- LangSmith.

## 12. Architecture Invariants
Verificables en code review:
1. peopleops-api no tiene credenciales del Synthetic HRIS.
2. reference-mcp-server no necesita credenciales de PeopleOps DB.
3. PeopleOps domain code no importa tablas físicas HRIS.
4. prompts no contienen mappings físicos del HRIS.
5. no keyword routing.
6. policy ingestion no depende de MCP.
7. HITL no depende de memoria de proceso.
8. AnalysisInteraction no depende de LangSmith.
9. schema-independence usa el mismo build de PeopleOps.
10. MCP failure nunca activa acceso directo alternativo.

## 13. Future Integration
```text
PeopleOps
 ↓
MCP Client
 ↓
Customer MCP Server
 ↓
BIZAG / SAP / Workday / Custom ERP
```

Una futura Integration Console para discovery/mapping/config queda fuera del MVP.
