# Proyecto 03 — PeopleOps AI — HR Intelligence Copilot
## Project Definition Document (PDD)

**Estado:** Diseño activo  
**Rol en el portfolio:** Domain-specific AI — Recursos Humanos  
**Producto conceptual:** Policy-Aware HR Intelligence Copilot  
**Documento:** Definición del proyecto  
**Versión:** 3.0
**Precede a:** PRD y documentación de arquitectura posterior

---

## 1. Propósito

PeopleOps AI será un **copiloto inteligente de Recursos Humanos** capaz de combinar:

- datos estructurados de empleados y procesos HR;
- información de nómina;
- asistencia y horas extra;
- contratos;
- vacaciones y permisos;
- documentos y políticas internas;
- razonamiento agentic;
- evidencia;
- Human-in-the-loop.

El proyecto debe demostrar que una aplicación empresarial moderna de IA para RRHH no se limita a un chatbot documental ni a un catálogo de funciones estáticas por pregunta.

PeopleOps AI debe interpretar preguntas en lenguaje natural, construir planes dinámicos, descubrir y consultar datos HR mediante una capa semántica/estructurada, recuperar políticas relevantes mediante RAG, combinar hechos y reglas, identificar incertidumbre y escalar a revisión humana cuando una salida tenga impacto sensible.

La aplicación pública funcionará con un **Synthetic Reference HRIS** y documentos ficticios. Desde el MVP, todo acceso a datos HR estructurados se realizará mediante una frontera MCP obligatoria: PeopleOps AI utilizará un **MCP Client** y se integrará con un **Reference MCP Server** conectado al HRIS sintético. Esta separación deberá permitir sustituir posteriormente el Reference MCP Server por un MCP Server específico para un ERP/HRIS real sin reescribir la capa agentic de PeopleOps.

## 2. Posicionamiento dentro del portfolio

PeopleOps AI representa la evolución desde:

**Enterprise RAG** → recuperación documental y grounding  
**ERP AI Analyst** → análisis agentic dinámico sobre datos empresariales estructurados

hacia:

> **Dynamic HR Intelligence + Policy RAG + Sensitive Workflows + Human Governance**

El proyecto debe demostrar una capacidad nueva y no repetir simplemente las arquitecturas anteriores.

## 3. Qué capacidad profesional demuestra

**Diseño de sistemas agentic empresariales aplicados a un dominio sensible, combinando datos estructurados, conocimiento documental, decisiones asistidas y Human-in-the-loop.**

Debe aportar evidencia de:

- AI Solutions Architecture;
- Agentic AI aplicada a RRHH;
- LangGraph;
- LlamaIndex;
- OpenAI tool calling y structured outputs;
- dynamic structured-data querying;
- semantic abstraction;
- Policy RAG;
- data + document grounding;
- Human-in-the-loop;
- privacidad y autorización;
- provider abstraction;
- arquitectura con MCP como frontera obligatoria de acceso a datos estructurados desde el MVP;
- evaluación multi-capa;
- observabilidad y trazabilidad;
- diseño production-oriented.

## 4. Problema empresarial

Los equipos de Recursos Humanos suelen trabajar con información distribuida entre ERP / HRIS, módulos de nómina, asistencia, contratos, vacaciones, permisos, documentos del trabajador, políticas internas, procedimientos y conocimiento operativo.

Responder una pregunta aparentemente sencilla puede requerir consultar varias fuentes.

Ejemplo:

> “¿Puede este empleado solicitar 15 días de vacaciones en noviembre?”

Para responder correctamente podrían ser necesarios contrato vigente, saldo de vacaciones, vacaciones ya programadas, asistencia, calendario, política vigente, restricciones por antigüedad, posibles excepciones y revisión humana.

PeopleOps AI busca convertir estas fuentes fragmentadas en un sistema consultable y gobernado, sin sustituir decisiones humanas sensibles.

## 5. Principios arquitectónicos fundamentales

### 5.1 No hardcoding semántico

Queda expresamente prohibido resolver intención o significado mediante listas de keywords, frases hardcodeadas, expresiones dependientes de idioma o árboles `if/elif` basados en lenguaje natural.

Ejemplo no permitido:

```python
if "vacaciones" in question:
    ...
```

La interpretación del lenguaje debe producir estructuras tipadas.

### 5.2 Una nueva pregunta no debe requerir una nueva función

No se diseñará una función Python por cada pregunta, métrica o combinación de filtros. Las tools deben representar **capacidades generales**, no preguntas predefinidas.

### 5.3 Las tools son primitivas; el plan es dinámico

Ejemplos conceptuales:

```text
discover_hr_model
query_hr_data
search_hr_policy
get_policy_version
request_human_review
```

La consulta concreta, filtros, métricas, relaciones y períodos deben construirse dinámicamente.

### 5.4 LLM para semántica; código para invariantes

El LLM puede interpretar, planificar, seleccionar capacidades, proponer consultas, correlacionar datos, analizar evidencia y explicar.

El código debe controlar autorización, seguridad, tipos, límites, acceso read-only, cálculos reproducibles, validaciones objetivas, persistencia y auditoría.

### 5.5 Facts + Policies + Reasoning

El sistema debe distinguir:

- **Hecho:** dato estructurado proveniente del HRIS / ERP / provider.
- **Regla:** política o documento recuperado y versionado.
- **Inferencia:** interpretación o recomendación generada por IA.

Nunca deben mezclarse silenciosamente.

### 5.6 Human Governance

Una respuesta que pueda tener consecuencias sobre una persona debe poder derivarse a Human Review.

## 6. ¿Para qué sirve?

PeopleOps AI sirve para consultar información HR mediante lenguaje natural, realizar análisis dinámicos sin conocer tablas ni SQL, relacionar empleados, contratos, asistencia, vacaciones y payroll, interpretar políticas internas, determinar qué política vigente aplica, combinar hechos estructurados con evidencia documental, detectar situaciones que requieren atención, explicar por qué una situación necesita revisión, apoyar procesos de RRHH sin automatizar decisiones sensibles y permitir integración futura con ERPs/HRIS reales.

## 7. ¿Qué tipo de preguntas responde?

### 7.1 Empleados y estructura organizacional
- “¿Cuántos empleados activos tenemos?”
- “¿Cuántos empleados ingresaron durante este trimestre?”
- “¿Cómo se distribuyen los empleados por departamento?”
- “¿Qué posiciones concentran más personal?”
- “¿Qué empleados cambiaron de departamento recientemente?”
- “¿Qué empleados tienen información obligatoria incompleta?”

### 7.2 Contratos
- “¿Qué contratos vencen en los próximos 45 días?”
- “¿Qué empleados tienen contratos que requieren revisión?”
- “¿Qué contratos se renovaron durante este trimestre?”
- “¿Qué empleados tienen documentación contractual pendiente?”
- “¿Qué contratos vencen mientras el empleado tiene vacaciones programadas?”
- “¿Qué procedimiento debe seguirse para renovar este tipo de contrato?”

### 7.3 Asistencia
- “¿Qué empleados registraron más tardanzas este mes?”
- “¿Qué áreas presentan mayor ausentismo?”
- “¿Cómo evolucionó el ausentismo en los últimos seis meses?”
- “¿Qué empleados tienen incidencias repetidas?”
- “¿Qué departamentos incrementaron más sus horas extra?”
- “¿Existe relación entre ausencias y horas extra en un área?”
- “¿Qué incidencias de asistencia requieren revisión?”

### 7.4 Vacaciones y permisos
- “¿Qué empleados tienen más de 20 días de vacaciones pendientes?”
- “¿Quiénes tienen vacaciones programadas el próximo mes?”
- “¿Qué solicitudes están pendientes?”
- “¿Puede este empleado solicitar 15 días de vacaciones en noviembre?”
- “¿Qué requisitos debe cumplir esta solicitud?”
- “¿Qué política regula este permiso?”
- “¿Esta solicitud cumple las condiciones documentadas?”
- “¿Qué solicitudes requieren revisión humana?”

### 7.5 Payroll — análisis individual y agregado

Payroll será una capacidad importante de PeopleOps AI. A diferencia de ERP AI Analyst, que trabaja payroll principalmente a nivel agregado económico-financiero, PeopleOps podrá analizar payroll dentro del contexto laboral de cada persona.

- “¿Por qué este empleado recibió menos neto este mes?”
- “¿Qué conceptos cambiaron respecto al período anterior?”
- “¿Cuántas horas extra fueron consideradas en la nómina?”
- “¿Las horas extra pagadas coinciden con las registradas?”
- “¿Qué descuentos explican la diferencia?”
- “¿Qué empleados presentan diferencias entre asistencia y nómina?”
- “¿Qué conceptos de nómina cambiaron para este empleado?”
- “¿Qué áreas incrementaron más el costo de horas extra?”
- “¿Cómo evolucionó el costo de nómina?”
- “¿Qué conceptos explican la variación global?”
- “¿Qué casos de payroll deberían revisarse manualmente?”

### 7.6 Políticas y procedimientos
- “¿Qué política regula las vacaciones?”
- “¿Cuál es la versión vigente?”
- “¿Dónde se define el procedimiento de horas extra?”
- “¿Qué documentos contienen reglas de trabajo remoto?”
- “¿Qué requisitos debe cumplir una licencia?”
- “¿Qué política se aplicaba en enero?”
- “¿Qué cambió entre la versión anterior y la actual?”
- “¿Qué evidencia respalda esta regla?”

### 7.7 Consultas combinadas
- “¿Qué empleados tienen contrato próximo a vencer y vacaciones pendientes?”
- “¿Qué áreas combinan alto ausentismo con mayor uso de horas extra?”
- “¿Qué empleados tienen documentación pendiente e incidencias recurrentes?”
- “¿Qué solicitudes de vacaciones requieren revisión según la política vigente?”
- “¿Qué diferencias de payroll coinciden con incidencias de asistencia?”
- “¿Qué empleados tienen horas extra registradas pero no reflejadas en nómina?”
- “¿Qué contratos próximos a vencer pertenecen a personas actualmente de licencia?”
- “¿Qué empleados tienen mayor saldo de vacaciones y contrato próximo a vencer?”

### 7.8 Preguntas policy-aware
- “Según la política vigente, ¿qué condiciones debe cumplir esta solicitud?”
- “¿Qué reglas aplican a este empleado?”
- “¿Existe alguna excepción documentada?”
- “¿La información disponible es suficiente para recomendar aprobación?”
- “¿Qué dato falta para tomar una decisión?”
- “¿Hay conflicto entre políticas?”
- “¿Debe intervenir una persona?”

### 7.9 Seguimiento conversacional

Ejemplo:

> “Muéstrame los contratos que vencen en los próximos 60 días.”  
> “Solo los del área de operaciones.”  
> “¿Cuáles de ellos tienen vacaciones pendientes?”  
> “Revisa la política de renovación y dime cuáles requieren atención.”

La conversación debe conservar contexto semántico sin introducir reglas de strings.

### 7.10 Preguntas que debe rechazar o limitar

- decisiones automáticas de despido, promoción o contratación;
- sanciones automáticas;
- inferencias de personalidad;
- conclusiones basadas en atributos sensibles;
- modificación de payroll sin autorización;
- escritura en HRIS fuera de workflows explícitamente aprobados;
- preguntas sin permisos suficientes.

## 8. Escenarios insignia

### 8.1 Vacation Policy Decision Support
Pregunta: **“¿Puede este empleado solicitar 15 días de vacaciones en noviembre?”**

Debe demostrar integración real entre datos estructurados, RAG, reglas documentales y HITL.

### 8.2 Payroll Reconciliation
Pregunta: **“¿Por qué este empleado recibió menos neto este mes?”**

Debe combinar payroll actual/anterior, conceptos, asistencia, overtime, leave y políticas/procedimientos relevantes.

### 8.3 Attendance + Payroll discrepancy
Pregunta: **“¿Qué empleados tienen horas extra registradas que no aparecen correctamente en nómina?”**

Debe construir la consulta dinámicamente y no depender de una función específica para esa frase.

## 9. Usuarios objetivo

- Recursos Humanos;
- People Operations;
- Payroll;
- responsables administrativos;
- jefaturas con permisos adecuados;
- analistas HR;
- responsables de contratos;
- responsables de asistencia;
- responsables de vacaciones.

## 10. Arquitectura conceptual

PeopleOps AI combinará tres fuentes/capacidades principales:

```text
                    PeopleOps AI
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
 Structured HR Data   Policy RAG    Human Review
          │              │              │
          ▼              ▼              ▼
         MCP          LlamaIndex      Governance
          │
          ▼
      ERP / HRIS
```

Principios:

- los datos estructurados se obtienen mediante MCP;
- la aplicación no depende del esquema físico del ERP/HRIS;
- las políticas son conocimiento administrado por PeopleOps;
- el LLM razona sobre hechos y reglas;
- las decisiones sensibles pueden requerir Human Review;
- la trazabilidad debe conservar datos, políticas y evidence utilizados.

La arquitectura física detallada se documentará posteriormente.

## 11. Dynamic semantic querying

La aplicación debe razonar sobre capacidades y metadata descubiertas dinámicamente, no sobre un catálogo fijo de funciones o tablas.

El flujo conceptual será:

```text
user question
    ↓
semantic understanding
    ↓
MCP discovery
    ↓
available entities / fields / relationships / capabilities
    ↓
conceptual query plan
    ↓
MCP validation
    ↓
source-specific translation
    ↓
safe execution
    ↓
evidence
```

Una consulta conceptual puede expresar:

```text
entities
metrics
dimensions
filters
relationships
time scope
comparisons
aggregations
conditions
ordering
limits
```

La representación exacta deberá definirse mediante contrato tipado.

PeopleOps no debe generar una nueva función para cada pregunta ni depender de nombres físicos de tablas.

El MCP Server podrá traducir la consulta conceptual a:

- PostgreSQL;
- SQL Server;
- Oracle;
- APIs;
- otros mecanismos del sistema origen.

## 12. Frontera de datos estructurados

PeopleOps AI debe permanecer desacoplado del modelo físico del ERP/HRIS.

Toda interacción con datos estructurados utilizará una frontera MCP.

Conceptualmente:

```text
PeopleOps AI
    ↓
MCP
    ↓
ERP / HRIS
```

El sistema conectado deberá poder exponer capacidades, estructura, relaciones y metadata semántica suficientes para que PeopleOps comprenda qué información está disponible.

El detalle de componentes, deployables, protocolos internos y estructura física se definirá posteriormente en Architecture/ADRs.

## 13. MCP como capacidad obligatoria del MVP

MCP forma parte del producto definido para el MVP.

El MVP deberá demostrar una integración end-to-end mediante un Reference MCP Server conectado a un HRIS sintético.

El objetivo es validar que:

- PeopleOps no depende de tablas físicas;
- el sistema conectado puede describir sus capacidades;
- el modelo puede razonar sobre metadata descubierta;
- las consultas pueden expresarse conceptualmente;
- el servidor puede validar, traducir y ejecutar la consulta sobre su origen;
- el resultado vuelve acompañado de evidencia.

Los adapters para ERPs reales serán extensiones posteriores.

## 14. Integraciones ERP/HRIS posteriores

El **Reference MCP Server** se implementará contra el Synthetic Reference HRIS y será obligatorio para cerrar el MVP.

Después podrán construirse MCP Servers o adapters específicos para:

- BIZAG HR;
- SAP HR;
- Workday;
- Dynamics;
- Odoo;
- otros ERP/HRIS;
- desarrollos particulares de clientes.

BIZAG es un candidato natural para una primera integración real, pero no será una dependencia del repositorio público.

La integración real no publicará:

- esquemas propietarios;
- datos de clientes;
- credenciales;
- código privado.

El conocimiento específico del ERP residirá dentro del servidor/adaptador MCP correspondiente, no dentro de PeopleOps AI.

## 15. Independencia del esquema

Una capacidad diferenciadora del producto será demostrar que PeopleOps no depende del esquema del HRIS sintético.

El producto deberá poder trabajar contra más de una representación física equivalente, siempre que el servidor MCP proporcione metadata y capacidades compatibles.

Esta propiedad deberá ser demostrada mediante pruebas, no solo documentada como intención.

## 16. Policy RAG

LlamaIndex será responsable de ingestión, parsing, chunking, embeddings, metadata, retrieval, versionado documental y evidencia/citación.

Documentos sintéticos iniciales:

- Vacation Policy;
- Leave Policy;
- Attendance Policy;
- Overtime Policy;
- Payroll Procedure;
- Remote Work Policy;
- Contract Renewal Procedure;
- Employee Documentation Procedure;
- Data Privacy Policy;
- HR Approval Matrix.

## 17. Human-in-the-loop

HITL es una capacidad central.

Estados conceptuales:

```text
SAFE_TO_ANSWER
RECOMMENDATION_READY
HUMAN_REVIEW_REQUIRED
INSUFFICIENT_DATA
POLICY_NOT_FOUND
POLICY_CONFLICT
PERMISSION_DENIED
```

Casos típicos de Human Review:

- excepciones;
- políticas ambiguas;
- conflictos documentales;
- información incompleta;
- consecuencias laborales;
- cambios de payroll;
- decisiones que afectan derechos del empleado.

## 18. Synthetic Reference HRIS Data Model

El **Synthetic Reference HRIS** debe incluir como mínimo:

- employees;
- departments;
- positions;
- contracts;
- attendance;
- overtime;
- vacation balances;
- vacation requests;
- leave requests;
- payroll periods;
- payroll items;
- payroll concepts;
- employee documents;
- approval records.

Estas entidades pertenecen al sistema sintético de referencia y no constituyen el contrato de integración de PeopleOps. El contrato real se deriva de capabilities, metadata y semantic discovery expuestos por MCP.

## 19. Anti-hardcoding rules para implementación

Estas reglas deben incorporarse también a `AGENTS.md` al comenzar el desarrollo:

1. Prohibido interpretar lenguaje mediante keywords.
2. Prohibido mantener listas de frases por idioma.
3. Prohibido crear una función nueva únicamente para una nueva pregunta.
4. Language understanding debe producir structured output.
5. Las tools representan capacidades.
6. Los guardrails validan estructura, seguridad y permisos.
7. Los cálculos reproducibles son determinísticos.
8. Las excepciones deben documentarse mediante ADR.
9. La agentic layer no accede directamente a tablas físicas.
10. Ninguna decisión sensible se automatiza sin gobernanza explícita.


## 21. Registro persistente de análisis y audit trail

PeopleOps AI debe incorporar una entidad persistente de análisis inspirada en el patrón ya validado en ERP AI Analyst.

No debe tratarse solamente de logging técnico. Será una **bitácora funcional durable** de cada solicitud y de las etapas recorridas por el workflow.

### AnalysisInteraction

Modelo conceptual:

```text
AnalysisInteraction
-------------------
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

La estructura exacta se cerrará en el modelo físico, pero estas responsabilidades deben conservarse.

### Particularidades del ciclo de vida

El registro debe crearse en el límite de la API **antes de iniciar el workflow**.

```text
API recibe pregunta
    ↓
genera request_id
    ↓
crea AnalysisInteraction
status = received
current_stage = received
    ↓
LangGraph
```

Cada transición relevante debe actualizar:

- `status`;
- `current_stage`;
- `stage_history`;
- snapshots estructurados disponibles en esa etapa;
- errores cuando correspondan;
- `updated_at`.

`stage_history` debe ser append-only desde la perspectiva lógica del workflow, conservando como mínimo:

```text
stage
status
timestamp
error_type (si aplica)
```

### Estados y stages conceptuales

Ejemplos:

```text
received
semantic_understanding
planning
structured_query
query_validation
policy_retrieval
evidence_merge
policy_reasoning
human_review
synthesis
completed
failed
```

Los stages reales se cerrarán con el diseño del LangGraph.

### Human Review y reanudación

A diferencia de una consulta puramente analítica, PeopleOps puede detenerse durante minutos u horas esperando revisión humana.

Por ello:

```text
status = pending_human_review
current_stage = human_review
```

debe poder persistirse durablemente.

Cuando el responsable humano actúe, la ejecución debe poder reanudarse manteniendo la identidad de análisis, su evidencia y su historia.

### Request y Conversation

`request_id` identifica una ejecución individual.

`conversation_id` permite relacionar una secuencia conversacional:

```text
Conversation
  ├── AnalysisInteraction A-001
  ├── AnalysisInteraction A-002
  └── AnalysisInteraction A-003
```

Cada follow-up constituye una ejecución auditable independiente aunque herede contexto de conversación.

### Qué se audita

Se deben persistir outputs estructurados observables, no razonamiento privado del modelo:

- interpretación semántica;
- plan de análisis;
- provider seleccionado;
- query plan / query candidate;
- validaciones;
- resultados estructurados;
- políticas recuperadas y versiones;
- evidencia;
- decisiones/routing;
- solicitud y resultado de Human Review;
- warnings;
- respuesta final;
- errores;
- latencia/modelo.

### Separación respecto a evaluación

`AnalysisInteraction` contiene ejecuciones reales de aplicación.

El **Evaluation Dataset** contiene casos de prueba y ground truth.

No son la misma entidad.

### Separación respecto a LangSmith

LangSmith se utilizará para observabilidad técnica cuando aporte valor.

La aplicación no dependerá de LangSmith como almacén funcional de:

- historial;
- auditoría;
- Human Review;
- reanudación;
- evidencia del usuario.

### Estrategia de persistencia

Para el MVP podrán utilizarse columnas JSONB para snapshots complejos como:

```text
stage_history
semantic_request
query_plan
validation
structured_result
policy_sources
evidence
response
warnings
```

Posteriormente podrán normalizarse eventos, evidencias y provider calls en tablas hijas si los requisitos de auditoría, reporting o volumen lo justifican.

---

## 22. Tecnologías principales

- **LangGraph** — workflow agentic y Human Review;
- **LlamaIndex** — HR Policy RAG;
- **OpenAI** — structured outputs, tool calling, interpretación, planificación y síntesis;
- **PostgreSQL** — datos HR sintéticos;
- **pgvector** — documentos/políticas;
- **FastAPI** — API;
- **LangSmith** — tracing/evaluación cuando aporte valor;
- **Docker** — reproducibilidad;
- **MCP** — frontera obligatoria de acceso a datos estructurados en el MVP.

## 23. Evaluación

La evaluación debe cubrir:

### Structured data
- query correctness;
- metric correctness;
- filters;
- joins;
- time range;
- multilingual semantic understanding.

### RAG
- policy retrieval;
- version correctness;
- citation/evidence;
- insufficient evidence.

### Workflow
- routing;
- provider calls;
- RAG usage;
- retries;
- Human Review routing.

### Final response
- facts;
- policy grounding;
- unsupported claims;
- distinction fact/rule/inference;
- correct escalation.

## 24. Seguridad y privacidad

El MVP utilizará únicamente datos ficticios.

La arquitectura debe contemplar read-only por defecto, least privilege, data classification, restricciones específicas para payroll, control de acceso, logging seguro, masking, audit trail, límites de resultados, secrets management, riesgos de prompt injection y Human Review.

## 25. Límites

- no utilizar datos reales de clientes en GitHub;
- no publicar código propietario;
- no automatizar contratación, despido, promoción ni sanción;
- no realizar inferencias de personalidad;
- no utilizar atributos sensibles para decisiones;
- no convertir el proyecto en un HRIS completo;
- no duplicar Enterprise RAG;
- no duplicar ERP AI Analyst;
- no permitir accesos directos desde PeopleOps al Synthetic Reference HRIS ni atajos que eviten la frontera MCP obligatoria del MVP.

## 26. Qué debe mostrar el repositorio

- README profesional;
- PDD;
- PRD;
- arquitectura;
- MCP contracts;
- MCP Client / HRDataGateway;
- Reference MCP Server funcional;
- discovery físico y semántico;
- query translation/validation/execution;
- AnalysisInteraction / durable audit trail;
- Structured HR Query Layer;
- LangGraph workflow;
- LlamaIndex Policy RAG;
- corpus documental sintético;
- modelo HR sintético;
- Payroll;
- Vacation/Leave;
- Attendance;
- Contracts;
- Human Review;
- evidencia;
- tests;
- evaluation suite;
- tracing;
- `.env.example`;
- Docker;
- demo;
- screenshots;
- ADRs;
- roadmap;
- seguridad;
- limitaciones;
- licencia.

## 27. Criterio de éxito

PeopleOps AI será exitoso si demuestra que una aplicación agentic puede combinar de forma segura:

> **dynamic structured HR data + policy knowledge + reasoning + human governance**

sin depender de funciones hardcodeadas por pregunta, sin quedar acoplada a un ERP concreto y manteniendo trazabilidad hacia datos y políticas.
