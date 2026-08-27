# Proyecto 03 — PeopleOps AI — HR Intelligence Copilot
## Product Requirements Document (PRD)

**Estado:** Diseño activo  
**Versión:** 3.0  
**Producto:** Policy-Aware HR Intelligence Copilot  
**Framework principal:** LangGraph + LlamaIndex + OpenAI

## 1. Product Vision

PeopleOps AI será una aplicación agentic para Recursos Humanos capaz de responder preguntas, analizar situaciones y asistir workflows HR combinando datos estructurados, payroll, documentos/políticas, razonamiento dinámico y Human-in-the-loop.

La aplicación **no accederá directamente al HRIS/ERP**, ni siquiera en la implementación sintética.

El MVP incluirá obligatoriamente:

```text
PeopleOps AI
    ↓
HRDataGateway
    ↓
MCP Client
    ↓
Reference MCP Server
    ↓
Synthetic Reference HRIS
```

El Reference MCP Server permitirá descubrir capacidades, esquema físico, relaciones y metadata semántica; validará consultas conceptuales, las traducirá al mecanismo del sistema origen, las ejecutará bajo guardrails y devolverá resultados con evidencia.

El Synthetic Reference HRIS sirve para desarrollo, pruebas y ground truth. No define el esquema que PeopleOps espera encontrar en un ERP real.

## 2. Objetivos

1. Permitir consultas HR en lenguaje natural.
2. Soportar múltiples idiomas sin hardcoding lingüístico.
3. Construir consultas conceptuales dinámicas.
4. Evitar una función por pregunta.
5. Descubrir capacidades y metadata del origen mediante MCP.
6. Mantener PeopleOps independiente de tablas y DBMS específicos.
7. Recuperar políticas relevantes.
8. Combinar facts + policies.
9. Analizar payroll a nivel individual y agregado.
10. Gestionar vacaciones, permisos, asistencia y contratos.
11. Escalar situaciones sensibles a revisión humana.
12. Proporcionar evidencia.
13. Implementar MCP Client y Reference MCP Server dentro del MVP.
14. Traducir/validar/ejecutar queries en el MCP Server.
15. Evaluar schema independence.
16. Evaluar comportamiento de forma reproducible.

## 3. No objetivos

El MVP no pretende:

- reemplazar un HRIS;
- ejecutar despidos/promociones;
- automatizar sanciones;
- modificar payroll automáticamente;
- cubrir recruiting completo;
- construir performance management;
- sustituir asesoría legal/laboral;
- implementar conectores productivos para todos los ERP/HRIS;
- publicar un BIZAG adapter real;
- resolver particularidades propietarias de clientes.

El **Reference MCP Server local sí forma parte obligatoria del MVP**. Lo que queda fuera son los servidores/adapters para ERPs reales específicos.

## 4. Usuarios

- RRHH;
- People Operations;
- Payroll;
- responsables de asistencia;
- responsables de contratos;
- responsables de vacaciones;
- jefaturas autorizadas;
- analistas HR.

## 5. Alcance MVP

### Employee
- identidad sintética;
- estado;
- departamento;
- posición;
- fecha de ingreso.

### Contracts
- tipo;
- vigencia;
- estado;
- expiración;
- documentación.

### Attendance
- presencia;
- tardanzas;
- ausencias;
- incidencias;
- overtime.

### Vacation / Leave
- balance;
- solicitudes;
- fechas;
- estados;
- permisos/licencias.

### Payroll
- payroll periods;
- employee payroll;
- payroll items;
- concepts;
- gross;
- deductions;
- net;
- overtime amount;
- bonuses/allowances;
- cost center.

### HR Policies
- vacaciones;
- permisos;
- asistencia;
- horas extra;
- payroll procedure;
- contract renewal;
- remote work;
- privacy;
- approval matrix.

### Human Review
- review requests;
- status;
- reviewer;
- comments;
- evidence snapshot.

## 6. Escenarios MVP

### Scenario A — Vacation request
Pregunta: **“¿Puede este empleado solicitar 15 días de vacaciones en noviembre?”**

Debe identificar empleado, consultar saldo, solicitud/período, recuperar política vigente, extraer restricciones, identificar datos faltantes, emitir recomendación y escalar si corresponde.

### Scenario B — Payroll explanation
Pregunta: **“¿Por qué este empleado recibió menos neto este mes?”**

Debe consultar payroll actual, período comparable, conceptos, asistencia, overtime, leave, identificar diferencias, recuperar procedimiento/política si aplica y explicar con evidencia.

### Scenario C — Reconciliation
Pregunta: **“¿Qué empleados tienen horas extra registradas que no aparecen correctamente en nómina?”**

Debe construir la consulta dinámicamente y no depender de una función específica para ese wording.

### Scenario D — Contract + vacation
Pregunta: **“¿Qué empleados tienen contrato próximo a vencer y vacaciones pendientes?”**

Debe combinar dominios.

### Scenario E — Policy version
Pregunta: **“¿Qué política se aplicaba a esta solicitud en enero?”**

Debe recuperar la versión vigente en la fecha relevante.

## 7. Principio obligatorio — No semantic hardcoding

### RF-ARCH-001
La aplicación no debe detectar intent, dominio, período o acción mediante keywords/frases hardcodeadas.

Prohibido:

```python
if "vacaciones" in question:
    ...
```

La semántica debe resolverse mediante LLM + structured outputs.

### RF-ARCH-002
Una pregunta nueva no debe requerir una nueva función salvo que introduzca una **capacidad nueva**, no una formulación nueva.

## 8. Semantic Interpretation Contract

El sistema debe producir una representación estructurada de la intención.

Ejemplo conceptual:

```json
{
  "goal": "evaluate_vacation_request",
  "entities": [{"type": "employee", "reference": "E-104"}],
  "domains": ["vacation", "contract", "policy"],
  "time_scope": {
    "type": "explicit",
    "from": "2026-11-01",
    "to": "2026-11-15"
  },
  "requires_policy": true,
  "sensitivity": "medium"
}
```

Los enums/campos definitivos se cerrarán durante diseño técnico.

## 9. Structured HR Query Layer

El query layer deberá aceptar consultas declarativas dinámicas.

Ejemplo:

```json
{
  "entity": "attendance",
  "metrics": ["overtime_hours"],
  "dimensions": ["employee"],
  "filters": [
    {"field": "department_id", "operator": "eq", "value": "OPS"}
  ],
  "time_scope": {
    "type": "relative",
    "unit": "month",
    "offset": 0
  }
}
```

No se obliga a utilizar este formato exacto; define el comportamiento requerido.

## 10. Query execution strategy

La estrategia objetivo del MVP será **conceptual query + MCP translation**.

```text
question
→ semantic understanding
→ MCP capability/schema/semantic discovery
→ typed conceptual query
→ MCP semantic validation
→ source-specific mapping
→ DBMS/API translation
→ security validation
→ read-only execution
→ structured result + evidence
```

PeopleOps AI no deberá construir SQL físico dependiente de PostgreSQL, Oracle, SQL Server u otro DBMS como contrato principal.

El Reference MCP Server podrá utilizar SQL dinámico internamente porque conoce el sistema origen y el dialecto PostgreSQL del Synthetic Reference HRIS.

Los servidores MCP futuros podrán traducir el mismo tipo de intención conceptual a:

- PostgreSQL SQL;
- SQL Server SQL;
- Oracle SQL;
- APIs;
- stored procedures read-only autorizados;
- otros mecanismos.

### Requisitos

- no mappings de frases;
- no funciones por pregunta;
- no acceso directo de PeopleOps a la DB;
- query conceptual tipado;
- validación antes de ejecutar;
- read-only por defecto;
- evidencia de ejecución;
- límites/timeouts;
- correlación por `request_id`.

## 11. HRDataGateway

PeopleOps dispondrá de un `HRDataGateway` interno.

El gateway:

- expone capacidades estables a LangGraph;
- encapsula el cliente MCP;
- normaliza errores;
- mantiene correlación;
- convierte respuestas MCP a contratos internos;
- no contiene mappings específicos de tablas ERP.

Capacidades conceptuales:

```text
discover_capabilities()
discover_entities()
describe_entity(...)
discover_relationships(...)
discover_semantics(...)
validate_query(...)
execute_query(...)
get_evidence(...)
```

Estas capacidades pueden materializarse como tools MCP o wrappers internos, pero no como funciones específicas para cada pregunta de negocio.

## 12. MCP Client — obligatorio

El MVP debe implementar un MCP Client real utilizado por `HRDataGateway`.

Requisitos:

- conexión al Reference MCP Server;
- discovery de tools/capabilities;
- typed input/output;
- timeout;
- retries controlados;
- normalización de errores;
- request correlation;
- propagación de security context cuando corresponda;
- evidencia provider-neutral.

La aplicación integrada no tendrá un fallback silencioso de acceso directo a PostgreSQL.

## 13. Reference MCP Server — obligatorio

El MVP debe incluir un servidor MCP funcional conectado al Synthetic Reference HRIS.

El componente podrá residir inicialmente en el mismo repositorio/monorepo, pero constituye una frontera arquitectónica independiente.

Responsabilidades obligatorias:

1. capability discovery;
2. physical schema discovery;
3. entity/field metadata;
4. relationship discovery;
5. semantic metadata;
6. conceptual query validation;
7. source-specific query translation;
8. DBMS-level validation;
9. safe read-only execution;
10. evidence generation;
11. error normalization;
12. request correlation;
13. data classification/scoping.

El servidor será la única puerta de acceso a datos HR estructurados utilizada por el MVP integrado.

## 14. MCP Server contract y adapters

El Reference MCP Server define el contrato que posteriormente deberán respetar servidores/adapters reales.

Arquitectura:

```text
PeopleOps AI
    ↓
MCP Client
    ↓
MCP Server Contract
    ├── Reference Synthetic HRIS Server
    ├── BIZAG HR Server / Adapter
    ├── SAP HR Server / Adapter
    ├── Workday Server / Adapter
    ├── Dynamics Server / Adapter
    └── Custom ERP Server / Adapter
```

Los adapters reales no forman parte del MVP inicial.

El **Reference Synthetic HRIS Server sí**.

Cada servidor puede mapear un modelo físico diferente y utilizar un DBMS o API diferente sin modificar la lógica agentic de PeopleOps.

## 15. MCP contract tests y schema-independence tests

Debe existir una suite de contrato para cualquier MCP Server compatible.

Validaciones mínimas:

```text
capabilities
entity discovery
field discovery
relationships
semantic metadata
supported operations
query validation
read-only execution
evidence
errors
limits
security/scoping
request correlation
```

### Schema independence

Debe existir una validación específica que demuestre que PeopleOps no depende del esquema sintético original.

El proyecto debe ejecutar un subconjunto representativo del evaluation dataset contra:

```text
Schema A
Employee
EmployeePayroll
OvertimeRecord
```

y contra un esquema alternativo físicamente distinto, por ejemplo:

```text
Schema B
HR_PERSON
PAY_MOVEMENT
TIME_EVENT
```

La aplicación PeopleOps no debe modificarse para soportar el segundo esquema.

Solo cambia la implementación/mapping/semantic metadata del MCP Server de prueba.

## 16. PolicyKnowledgeProvider

La lógica de RAG debe quedar encapsulada.

Capacidades:

```text
search_policy
get_policy_version
get_policy_fragment
get_policy_metadata
```

La implementación MVP utiliza LlamaIndex.

## 17. Requisitos de Policy RAG derivados de Enterprise RAG

La implementación de Policy RAG debe reutilizar los patrones que ya demostraron buen comportamiento en Enterprise RAG.

### RF-RAG-01 — Metadata empresarial
Cada documento/política debe conservar metadata de negocio suficiente para filtrado y trazabilidad.

### RF-RAG-02 — Versionado y vigencia
El sistema debe poder seleccionar la política vigente para una fecha relevante.

### RF-RAG-03 — Retrieval con filtros
La recuperación debe soportar filtros de metadata cuando el caso lo requiera.

### RF-RAG-04 — Evidence verification
Una cita no debe promoverse como evidencia sin haber sido recuperada y verificada.

### RF-RAG-05 — Abstention
Cuando la evidencia sea insuficiente, el sistema debe abstenerse o señalar insuficiencia.

### RF-RAG-06 — Persistencia de evidencia
La ejecución debe conservar documentos, versiones, fragmentos/páginas y scores relevantes.

### RF-RAG-07 — Evaluación reproducible
Debe existir un dataset versionado y un baseline reproducible.

### RF-RAG-08 — Métricas deterministas
Como mínimo deben contemplarse métricas equivalentes a:

```text
document_hit_rate
document_recall
filter_precision
page/source recall cuando aplique
citation_validity
answerability_accuracy
abstention_accuracy
```

### RF-RAG-09 — Métricas semánticas opcionales
Groundedness/relevance mediante LLM judge podrán ejecutarse de forma separada y autorizada.

### RF-RAG-10 — Separación ingestión/evaluación
La suite de evaluación no debe ocultar fallos de ingestión cargando automáticamente el corpus sin control.

## 18. Corpus documental

MVP: aproximadamente 8–12 documentos ficticios:

1. Vacation Policy.
2. Leave and Absence Policy.
3. Attendance Policy.
4. Overtime Policy.
5. Payroll Processing Procedure.
6. Contract Renewal Procedure.
7. Remote Work Policy.
8. Employee Documentation Procedure.
9. HR Data Privacy Policy.
10. Approval Matrix.

Los documentos deben contener versiones, effective dates, secciones, cross references, excepciones y casos ambiguos deliberados.

## 19. Policy retrieval requirements

- **RF-POL-01:** recuperar política relevante.
- **RF-POL-02:** seleccionar versión vigente en fecha relevante.
- **RF-POL-03:** mostrar documento/sección/evidencia.
- **RF-POL-04:** reconocer política inexistente.
- **RF-POL-05:** detectar conflicto aparente cuando no pueda resolverse por metadata.
- **RF-POL-06:** no inventar reglas no presentes en documentos.

## 20. LangGraph workflow

Arquitectura base:

```text
START
  ↓
Understand Request
  ↓
Classify Sensitivity / Requirements
  ↓
Build Analysis Plan
  ↓
┌───────────────┬────────────────┐
│               │                │
Structured HR   Policy Retrieval │
Data Query      (if required)    │
│               │                │
└───────┬───────┴────────────────┘
        ↓
Merge Evidence
        ↓
Policy-aware Reasoning
        ↓
Risk / Completeness Check
        ↓
     Decision
     /      safe       review
 |           |
 ↓           ↓
Synthesize  Human Review
              ↓
           Resume
              ↓
          Synthesize
              ↓
             END
```

El grafo exacto se definirá durante diseño técnico.

## 21. Human Review requirements

- **RF-HITL-01:** LangGraph debe poder suspender/continuar el workflow para revisión humana cuando la tecnología elegida lo permita.
- **RF-HITL-02:** el review request debe incluir request ID, question, employee/context, facts, policies, evidence, recommendation y reason for escalation.
- **RF-HITL-03:** estados `pending`, `approved`, `rejected`, `needs_information`, `cancelled`.
- **RF-HITL-04:** la revisión debe quedar auditada.

## 22. Payroll requirements

Payroll no debe reducirse a analytics agregada.

- **RF-PAY-01:** consultar payroll por empleado/período.
- **RF-PAY-02:** comparar payroll entre períodos.
- **RF-PAY-03:** explicar cambios por concepto.
- **RF-PAY-04:** cruzar overtime registrado vs pagado.
- **RF-PAY-05:** cruzar leave/absence con conceptos afectados cuando el modelo sintético lo permita.
- **RF-PAY-06:** permitir análisis agregado por área/departamento.
- **RF-PAY-07:** aplicar restricciones de acceso.
- **RF-PAY-08:** no permitir escritura en MVP.

## 23. Attendance requirements

- tardanzas;
- ausencias;
- overtime;
- incidencias;
- métricas temporales;
- employee/department dimensions.

## 24. Vacation/Leave requirements

- balance;
- earned/available days cuando aplique;
- scheduled days;
- request dates;
- overlap;
- status;
- policy requirements;
- escalation.

## 25. Contract requirements

- active/expired;
- start/end;
- type;
- renewal;
- upcoming expiration;
- documentation status.

## 26. Synthetic Reference HRIS Data Model

El MVP incluirá un sistema HRIS sintético de referencia con entidades candidatas:

```text
Employee
Department
Position
Contract
AttendanceRecord
AttendanceIncident
OvertimeRecord
VacationBalance
VacationRequest
LeaveRequest
PayrollPeriod
EmployeePayroll
PayrollItem
PayrollConcept
EmployeeDocument
AnalysisInteraction
HumanReviewRequest
HumanReviewDecision
```

Estas entidades son correctas para construir datos sintéticos, ground truth y pruebas.

**No constituyen el contrato de datos de PeopleOps AI.**

PeopleOps no debe asumir que un ERP real posee estas tablas, nombres o relaciones físicas.

El Reference MCP Server será responsable de descubrir y exponer el modelo disponible y de proporcionar metadata semántica suficiente para que el LLM pueda razonar sobre él.

Para validar independencia de schema, se implementará además un esquema alternativo pequeño con nombres/estructuras diferentes utilizado únicamente en pruebas de integración MCP.

## 27. AnalysisInteraction — persistencia funcional y auditoría

PeopleOps AI debe persistir una interacción de análisis desde que la API acepta la solicitud hasta su finalización, fallo o suspensión por Human Review.

Este requisito toma como referencia un patrón ya validado en ERP AI Analyst: crear primero la interacción, asignar `request_id`, y actualizar el mismo registro durante cada etapa del workflow.

### RF-AUD-01 — Crear antes del workflow

Al recibir:

```text
POST /api/v1/analysis
```

la API debe:

1. resolver/generar `conversation_id`;
2. generar un `request_id` único;
3. crear `AnalysisInteraction`;
4. registrar stage/status `received`;
5. iniciar el workflow.

La respuesta HTTP debe exponer `request_id` y el API podrá incluirlo además como header de correlación.

### RF-AUD-02 — Modelo conceptual

Campos mínimos:

```text
id
request_id
conversation_id
created_at
updated_at

question
status
current_stage
stage_history

analysis_goal
semantic_request
query_plan
query_candidate
query_hash

provider_type
provider_catalog_version

validation
structured_result

policy_sources
policy_versions
evidence

human_review_status
human_review_id

response
warnings

latency_ms
model_name

error_type
error_detail
```

El schema físico puede ajustar nombres o dividir responsabilidades, pero no eliminar la trazabilidad requerida.

### RF-AUD-03 — Stage history

Cada transición relevante debe anexar un evento lógico:

```json
{
  "stage": "policy_retrieval",
  "status": "running",
  "at": "timestamp",
  "error_type": null
}
```

La implementación MVP puede utilizar JSONB para `stage_history`.

### RF-AUD-04 — Current stage

Debe existir una representación durable del stage actual para permitir:

- troubleshooting;
- UI de estado;
- detección de ejecuciones incompletas;
- Human Review;
- reanudación.

### RF-AUD-05 — Snapshots estructurados

A medida que exista información, el registro debe consolidar snapshots estructurados como:

- semantic request;
- analysis goal;
- query plan/candidate;
- validation;
- provider result;
- policy retrieval;
- evidence;
- final response.

No es obligatorio que todos los campos existan desde el inicio.

### RF-AUD-06 — Fallos

Ante una excepción controlada o no controlada del workflow:

```text
status = failed
current_stage = <stage>
error_type = <exception/type>
error_detail = <safe detail>
```

y debe añadirse un evento al `stage_history`.

La falla del mecanismo de auditoría no debe exponer datos sensibles ni producir errores secundarios difíciles de diagnosticar; debe registrarse en logging técnico.

### RF-AUD-07 — Human Review durable

Cuando el workflow derive a revisión humana:

```text
status = pending_human_review
current_stage = human_review
human_review_status = pending
```

El análisis debe poder reanudarse posteriormente sin crear una nueva identidad funcional para la misma ejecución.

La acción humana debe quedar relacionada con `analysis_id/request_id`.

### RF-AUD-08 — Conversation correlation

Cada ejecución tiene `request_id` único.

Varias ejecuciones pueden compartir `conversation_id`.

Los follow-ups deben generar un nuevo `request_id`, preservando el `conversation_id`.

### RF-AUD-09 — No almacenar chain-of-thought

El audit trail no debe almacenar razonamiento privado del modelo.

Solo se almacenarán outputs observables/estructurados requeridos por operación, evidencia, seguridad y auditoría.

### RF-AUD-10 — LangSmith complementario

LangSmith no constituye la base funcional de análisis.

La persistencia de `AnalysisInteraction` debe funcionar aunque LangSmith no esté disponible.

### RF-AUD-11 — Versiones de fuentes

Cuando corresponda, la interacción debe conservar suficiente información para reconstruir el contexto utilizado:

```text
provider_type
provider_catalog_version
policy_document_id
policy_version
knowledge/index version
model_name
```

Esto es especialmente importante cuando políticas o datos cambian después de una ejecución.

### RF-AUD-12 — Separación del Evaluation Dataset

Las tablas/archivos de evaluación no deben mezclarse con `AnalysisInteraction`.

```text
Evaluation Dataset
→ qué debería hacer el sistema

AnalysisInteraction
→ qué hizo realmente una ejecución
```

### Evolución opcional

Si el crecimiento del audit trail lo justifica, se podrán crear:

```text
AnalysisEvent
AnalysisEvidence
AnalysisProviderCall
AnalysisModelCall
```

El MVP puede mantener snapshots JSONB para evitar sobrearquitectura inicial.

---

## 28. Ground truth scenarios

Los datos deben contener hechos deliberados:

- contrato próximo a vencer;
- vacaciones disponibles suficientes;
- vacaciones insuficientes;
- conflicto de fechas;
- empleado con overtime registrado;
- overtime ausente en payroll;
- payroll neto reducido por descuento;
- ausencia con efecto previsto;
- política anterior vs actual;
- solicitud con excepción;
- caso que requiere Human Review.

## 29. Evaluation Dataset

Formato conceptual:

```text
case_id
question
language
scenario
expected_intent
expected_domains
expected_query_features
expected_policy_sources
expected_facts
expected_policy_facts
expected_human_review
expected_status
expected_answer_characteristics
```

Debe contener múltiples idiomas.

## 30. Evaluation metrics

### Semantic understanding
- intent accuracy;
- domain selection;
- temporal interpretation;
- multilingual consistency.

### Structured query
- table/entity correctness;
- filter correctness;
- calculation correctness;
- result correctness.

### RAG
- Recall@K;
- MRR;
- policy version accuracy;
- evidence correctness;
- groundedness.

### Workflow
- correct branch rate;
- unnecessary provider call rate;
- Human Review routing accuracy;
- retry/error recovery.

### Response
- key fact coverage;
- unsupported claim rate;
- rule/evidence attribution;
- fact/rule/inference separation.

## 31. Negative evaluation cases

- unsupported request;
- missing employee;
- insufficient data;
- missing policy;
- conflicting policy;
- unauthorized payroll query;
- future period without data;
- query validation failure;
- provider failure;
- RAG failure;
- prompt injection inside policy;
- sensitive decision request;
- multilingual paraphrase.

## 32. Security requirements

- **SEC-01:** read-only structured provider for MVP.
- **SEC-02:** no arbitrary writes.
- **SEC-03:** data classification.
- **SEC-04:** payroll restrictions.
- **SEC-05:** role/scoped access conceptually supported.
- **SEC-06:** no secrets in repo.
- **SEC-07:** audit.
- **SEC-08:** limits/timeouts.
- **SEC-09:** policy documents treated as untrusted content.
- **SEC-10:** no prompt instructions from documents may override system policy.
- **SEC-11:** sensitive responses must be minimised.

## 33. Observability

Debe registrar request ID, LangGraph nodes, provider calls, structured query, validation, policy retrieval, sources, Human Review, errors, retries, model calls y latency.

LangSmith se utilizará cuando aporte trazabilidad/evaluación útil.

## 34. API conceptual

```text
POST /api/v1/analysis
GET  /api/v1/analysis/{request_id}
GET  /api/v1/analysis/{request_id}/evidence

GET  /api/v1/reviews
GET  /api/v1/reviews/{review_id}
POST /api/v1/reviews/{review_id}/decision

GET  /api/v1/health
```

## 35. UX MVP

Pantalla principal:

- pregunta;
- respuesta;
- key findings;
- employee/context;
- data evidence;
- policy evidence;
- warnings.

Review screen:

- solicitud;
- hechos;
- políticas;
- recomendación;
- motivo de revisión;
- aprobar/rechazar/pedir información.

## 36. Requisitos no funcionales

- reproducibilidad;
- typed contracts;
- testabilidad;
- modularidad;
- provider substitution;
- trazabilidad;
- privacidad;
- Docker;
- config por entorno;
- logging;
- retries controlados;
- performance razonable;
- documentación;
- production-oriented.

## 37. Testing

### Unit
- conceptual query contracts;
- semantic metadata contracts;
- calculations;
- validators;
- security;
- policy metadata;
- MCP translation components inside the Reference MCP Server.

### Integration
- PeopleOps → HRDataGateway;
- HRDataGateway → MCP Client;
- MCP Client → Reference MCP Server;
- Reference MCP Server → Synthetic Reference HRIS;
- RAG → vector store;
- workflow → MCP;
- workflow → RAG;
- HITL persistence;
- `AnalysisInteraction` stage updates.

### Agentic
- semantic parsing;
- planning;
- dynamic use of MCP discovery;
- conceptual query generation;
- routing;
- corrections;
- synthesis.

### MCP Contract
- capability discovery;
- schema/entity discovery;
- field metadata;
- relationship discovery;
- semantic metadata;
- query validation;
- read-only execution;
- evidence;
- error normalization;
- request correlation;
- security/scoping.

### Schema independence
Ejecutar casos equivalentes sobre al menos dos esquemas físicos distintos sin modificar la lógica agentic de PeopleOps.

### Evaluation regression
- dataset completo;
- casos multilingües;
- RAG;
- HITL routing;
- MCP integration.

## 38. Criterios de aceptación MVP

El MVP será aceptable cuando:

1. funcione con datos y documentos sintéticos;
2. consulte employees/contracts/attendance/vacation/payroll;
3. no exista semantic hardcoding por idioma;
4. preguntas nuevas puedan resolverse mediante composición dinámica;
5. LangGraph no dependa de tablas físicas ni de un dialecto SQL;
6. exista `HRDataGateway`;
7. exista MCP Client funcional;
8. exista Reference MCP Server funcional;
9. todo acceso estructurado integrado atraviese MCP;
10. el Reference MCP Server descubra capabilities;
11. descubra entidades/tablas y campos;
12. descubra relaciones;
13. exponga metadata semántica;
14. acepte consultas conceptuales tipadas;
15. valide las consultas antes de ejecutarlas;
16. traduzca consultas al mecanismo PostgreSQL del Synthetic Reference HRIS;
17. ejecute únicamente operaciones read-only autorizadas;
18. devuelva resultados y evidence provider-neutral;
19. exista Policy RAG con LlamaIndex;
20. se recupere la versión correcta de una política;
21. exista al menos un workflow datos + RAG;
22. exista al menos un workflow con Human Review;
23. Payroll soporte análisis individual;
24. exista reconciliación Attendance ↔ Payroll;
25. exista `AnalysisInteraction`;
26. cada análisis tenga `request_id` persistente;
27. `current_stage` y `stage_history` se actualicen durante el workflow;
28. los fallos queden registrados con stage y error;
29. un análisis en Human Review pueda persistirse y reanudarse;
30. evidencia estructurada acompañe las respuestas;
31. exista evaluation dataset;
32. se prueben preguntas en más de un idioma;
33. existan MCP contract tests;
34. exista al menos una prueba de schema independence;
35. existan guardrails;
36. existan tests unitarios/integración/agentic;
37. exista Docker;
38. exista `.env.example`;
39. README documente límites, privacidad, arquitectura MCP y modelo de integración.

El MVP **no se considera terminado** si PeopleOps funciona únicamente mediante acceso directo al Synthetic Reference HRIS.

## 39. Criterios obligatorios MCP para completar el MVP

El proyecto **no se considerará MVP completo** hasta cumplir:

1. existe `HRDataGateway`;
2. existe MCP Client real;
3. existe Reference MCP Server real;
4. PeopleOps no accede directamente al Synthetic Reference HRIS;
5. el servidor descubre capabilities;
6. el servidor descubre entidades/tablas y campos;
7. el servidor descubre relaciones;
8. existe metadata semántica;
9. el cliente puede construir/enviar consultas conceptuales tipadas;
10. el servidor valida la consulta;
11. el servidor traduce al mecanismo PostgreSQL del HRIS sintético;
12. el servidor ejecuta read-only con guardrails;
13. devuelve resultado y evidence provider-neutral;
14. `request_id` se correlaciona end-to-end;
15. existen MCP contract tests;
16. existe al menos una prueba de schema independence;
17. LangGraph no conoce tablas físicas ni dialecto SQL;
18. los errores MCP quedan normalizados y auditados en `AnalysisInteraction`.

Los adapters BIZAG/SAP/Workday/etc. no son requisito del MVP. El Reference MCP Server sí lo es.

## 40. Roadmap

### Fase 0 — Diseño
- PDD/PRD;
- architecture;
- ADRs;
- synthetic scenario;
- Synthetic Reference HRIS;
- MCP contract;
- semantic metadata contract;
- conceptual query contract;
- policy corpus;
- AnalysisInteraction.

### Fase 1 — Foundation
- FastAPI;
- PostgreSQL;
- Docker;
- migrations;
- config;
- tests;
- base MCP Server/client packages.

### Fase 2 — Synthetic Reference HRIS
- employees;
- contracts;
- attendance;
- vacation;
- payroll;
- seed scenarios;
- ground truth.

### Fase 3 — Reference MCP Server + MCP Client
- capability discovery;
- schema/entity discovery;
- field discovery;
- relationship discovery;
- semantic metadata;
- HRDataGateway;
- MCP Client;
- request correlation.

### Fase 4 — Dynamic Conceptual Query
- semantic interpretation;
- conceptual query schema;
- MCP query validation;
- PostgreSQL translation inside Reference MCP Server;
- DBMS validation;
- read-only execution;
- evidence;
- guardrails.

### Fase 5 — Policy RAG
- documents;
- LlamaIndex;
- metadata;
- versions;
- retrieval evaluation.

### Fase 6 — Agentic Workflow
- LangGraph;
- planner;
- data + RAG orchestration;
- synthesis;
- AnalysisInteraction stage tracking.

### Fase 7 — Human-in-the-loop
- review model;
- pause/resume;
- UI/API;
- audit.

### Fase 8 — Payroll Deepening
- individual payroll;
- concepts;
- Attendance ↔ Payroll;
- exception scenarios.

### Fase 9 — Evaluation
- ground truth;
- multilingual cases;
- agentic evaluation;
- RAG evaluation;
- MCP contract tests;
- schema-independence test;
- regression.

### Fase 10 — UX / Portfolio Hardening
- frontend;
- screenshots;
- demo;
- README;
- observability;
- security docs;
- architecture diagrams.

### Fase 11 — Real ERP/HRIS Integration
Posterior al MVP:
- BIZAG MCP Server/adapter;
- SAP/Workday/etc.;
- customer-specific implementations.

## 41. ADRs recomendados

- ADR-001 — No semantic keyword routing.
- ADR-002 — Dynamic HR Query Strategy.
- ADR-003 — HRDataProvider abstraction.
- ADR-004 — Local Provider vs MCP Provider boundary.
- ADR-005 — Policy RAG with LlamaIndex.
- ADR-006 — Human Review governance.
- ADR-007 — Payroll privacy model.
- ADR-008 — Policy versioning.
- ADR-009 — Evidence contract.
- ADR-010 — Multilingual semantic handling.

## 42. Definition of Done para portfolio

PeopleOps AI será presentable cuando un evaluador pueda:

- ejecutar el sistema;
- formular preguntas no preprogramadas;
- ver que el sistema interpreta semánticamente la consulta;
- consultar datos HR dinámicamente;
- recuperar políticas;
- comprobar evidencia;
- observar un workflow multi-step;
- observar una decisión derivada a Human Review;
- analizar payroll individual;
- revisar evaluación;
- entender la arquitectura provider-neutral;
- entender cómo podría sustituirse PostgreSQL por un MCP provider;
- revisar seguridad, límites y ADRs.

## 43. Declaración final de producto

PeopleOps AI será:

> **Un HR Intelligence Copilot agentic y policy-aware que combina datos estructurados descubiertos dinámicamente mediante MCP, payroll, políticas documentales y Human-in-the-loop, sin quedar acoplado al esquema físico o DBMS del ERP/HRIS origen.**

El MVP incluye obligatoriamente:

```text
PeopleOps AI
+ MCP Client
+ Reference MCP Server
+ Synthetic Reference HRIS
+ Dynamic Conceptual Query
+ Policy RAG
+ Human Review
+ AnalysisInteraction
+ Evaluation
```

El Synthetic Reference HRIS valida el producto, pero no define su contrato de datos.

El **Reference MCP Server** es quien descubre y describe el modelo disponible, valida consultas conceptuales, las traduce al sistema origen, las ejecuta bajo guardrails y devuelve evidencia.

Posteriormente, PeopleOps podrá conectarse a otros ERPs/HRIS sustituyendo el servidor/adaptador MCP, sin reescribir el razonamiento agentic principal.

