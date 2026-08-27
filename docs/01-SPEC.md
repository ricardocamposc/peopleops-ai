# PeopleOps AI — System Specification (SPEC)

**Deriva de:** BRD + PDD + PRD

## 1. Propósito
PeopleOps AI es un **HR Intelligence Copilot agentic y policy-aware** que combina datos estructurados de RRHH, payroll, políticas/procedimientos, razonamiento dinámico, evidencia y Human-in-the-loop.

Debe demostrar independencia del schema físico del ERP/HRIS y funcionar sobre datos/documentos sintéticos en el MVP.

## 2. Objetivos
El sistema debe:
- aceptar preguntas HR en lenguaje natural;
- interpretar semánticamente sin reglas por idioma;
- descubrir capacidades del origen mediante MCP;
- construir consultas conceptuales dinámicas;
- combinar dominios HR;
- recuperar políticas mediante RAG;
- distinguir hechos, reglas e inferencias;
- producir evidencia;
- escalar a revisión humana;
- persistir cada análisis;
- soportar múltiples idiomas;
- demostrar schema independence.

## 3. Arquitectura funcional
```text
User
 ↓
PeopleOps Web
 ↓
PeopleOps API
 ↓
LangGraph
 ├────────→ Policy Knowledge / LlamaIndex
 └────────→ HRDataGateway
              ↓
           MCP Client
              ↓
      Reference MCP Server
              ↓
   Synthetic Reference HRIS
```

PeopleOps API mantiene su propia persistencia para conversaciones, análisis, Human Review y políticas.

## 4. Deployables
### peopleops-api
FastAPI, LangGraph, OpenAI, LlamaIndex, Policy RAG, AnalysisInteraction, Human Review, MCP Client.

### peopleops-web
Chat/análisis, evidencia, historial, administración de políticas, carga documental y Human Review.

### reference-mcp-server
Discovery, semantic catalog, query validation, translation, safe execution y evidence.

Backend-only para el MVP.

## 5. Fronteras
### PeopleOps
Responsable de lenguaje, planificación, workflow, Policy RAG, Human Review, auditoría y UX.

No debe:
- conocer tablas físicas del ERP;
- ejecutar SQL directamente sobre HRIS;
- usar keywords para routing;
- reemplazar el HRIS.

### Reference MCP Server
Debe:
- descubrir capabilities/schema/relationships;
- exponer semantic metadata;
- validar conceptual query;
- traducir al origen;
- ejecutar read-only;
- devolver evidence.

### Synthetic Reference HRIS
Sirve para desarrollo, tests, demo y ground truth. No define el contrato PeopleOps.

## 6. Interpretación semántica
Lenguaje natural → structured output tipado.

Ejemplo conceptual:
```json
{
  "goal": "explain_payroll_change",
  "subjects": [{"type":"employee","reference":"E-104"}],
  "required_capabilities": ["payroll","attendance","overtime"],
  "time_scope": {"type":"period_comparison"}
}
```

No debe existir routing por español/inglés/portugués.

## 7. Discovery
MCP debe poder exponer:
- capabilities;
- entities/tables;
- fields/columns;
- types;
- PK/FK/relationships cuando corresponda;
- temporal fields;
- semantic descriptions;
- metrics/dimensions;
- sensitivity;
- supported operations.

Schema físico no es suficiente: debe existir metadata semántica.

## 8. Conceptual Query
PeopleOps expresa qué necesita, no cómo consultarlo físicamente.

Ejemplo:
```json
{
  "entities": ["employee","overtime","payroll"],
  "metrics": ["recorded_overtime_hours","paid_overtime_hours"],
  "time_scope": {"type":"current_payroll_period"},
  "conditions": [{
    "left":"recorded_overtime_hours",
    "operator":">",
    "right":"paid_overtime_hours"
  }]
}
```

El MCP Server realiza:
conceptual query → semantic validation → mapping → DBMS/API translation → physical validation → execution → evidence.

## 9. Policy RAG
Reutilizar patrones probados en Enterprise RAG:
```text
PDF/DOCX
 ↓
Parsing
 ↓
Chunking
 ↓
Metadata
 ↓
Embeddings
 ↓
PostgreSQL/pgvector
 ↓
Retrieval
 ↓
Evidence Verification
 ↓
Grounded result
```

Metadata mínima:
- document_id;
- title;
- document_type;
- version;
- effective_from/effective_to;
- status;
- department;
- confidentiality;
- tags.

Obligatorio:
- metadata filtering;
- versionado;
- selección por vigencia;
- citas/evidence;
- abstention;
- conflicto documental;
- dataset reproducible;
- baseline determinista;
- LLM judge separado si se usa.

## 10. Agentic Workflow
LangGraph coordina:
- comprensión;
- planificación;
- selección de capacidades;
- iteración limitada;
- combinación data + policy;
- suficiencia;
- Human Review;
- síntesis.

Código determinístico:
- schemas;
- autorización;
- persistencia;
- cálculos;
- límites;
- guardrails.

No crear agentes por módulo HR.

## 11. Human-in-the-loop
Debe permitir:
```text
analysis
 ↓
pending_human_review
 ↓
persist
 ↓
human decision
 ↓
resume
 ↓
synthesis
```

Estados conceptuales:
SAFE_TO_ANSWER, RECOMMENDATION_READY, HUMAN_REVIEW_REQUIRED, INSUFFICIENT_DATA, POLICY_NOT_FOUND, POLICY_CONFLICT, PERMISSION_DENIED, FAILED.

## 12. AnalysisInteraction
Se crea antes de LangGraph.

Debe conservar al menos:
request_id, conversation_id, question, status, current_stage, stage_history, semantic_request, analysis_goal, query_plan, provider_catalog_version, validation, structured_result, policy_sources, policy_versions, evidence, human_review_status, response, warnings, model_name, latency_ms, error_type, error_detail.

No almacenar chain-of-thought.

## 13. Dominios del Synthetic HRIS
Employee, Department, Position, Contracts, Attendance, Overtime, Vacation, Leave, Payroll.

Payroll incluye análisis individual, conceptos, gross/net, deductions y reconciliación con attendance/overtime.

## 14. Escenarios insignia
- Vacation Policy Decision Support.
- Payroll Explanation.
- Attendance ↔ Payroll Reconciliation.
- Contract + Vacation.
- Historical Policy Version.

## 15. Seguridad
- synthetic data only;
- HRIS read-only;
- least privilege;
- payroll sensitivity;
- request correlation;
- row limits;
- timeouts;
- safe logging;
- secrets por entorno;
- prompt injection defense;
- Human Review.

## 16. Evaluación
Separar:
- Structured Data;
- MCP;
- Policy RAG;
- Workflow;
- Final Answer.

Debe incluir casos multilingües, negativos y schema independence.

## 17. Schema Independence
Ejecutar casos equivalentes contra:
```text
Schema A: Employee / EmployeePayroll / OvertimeRecord
Schema B: HR_PERSON / PAY_MOVEMENT / TIME_EVENT
```
sin modificar PeopleOps.

## 18. Prohibiciones
No:
- keyword routing;
- phrase lists;
- función por pregunta;
- `peopleops-api → synthetic_hris_db`;
- SQL físico como contrato principal de PeopleOps;
- fallback silencioso bypass MCP;
- decisiones laborales automáticas;
- writes en payroll/HRIS;
- frontend MCP separado en MVP.

## 19. Baseline production-oriented
Docker, `.env.example`, migrations, logging estructurado, request correlation, retries limitados, timeouts, error handling, tests, evaluation, observability y documentación.
