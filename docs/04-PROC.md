# PeopleOps AI — Processes and Workflows (PROC)

## PROC-01 — Analysis Request
```text
User → POST /analysis → Create AnalysisInteraction → Understand Request
→ Build Plan → Structured Data / Policy RAG / both → Merge Evidence
→ Assess completeness/sensitivity → Human Review? → Synthesis/Complete
```
Reglas:
- AnalysisInteraction se crea antes de LangGraph.
- cada transición actualiza stage.
- failure persiste error + stage.
- sin evidencia suficiente, no inventar.

## PROC-02 — MCP Discovery
```text
Need structured data → HRDataGateway → MCP Client
→ discover_capabilities → discover_entities
→ describe_entity → discover_relationships
→ discover_semantics → catalog version/fingerprint
```
Discovery puede cachearse, pero debe quedar versionado.

## PROC-03 — Conceptual Query Execution
```text
Plan → Conceptual Query → MCP validate_query
→ valid?
   no → feedback → limited replan
   yes → translate → physical validation → safety guardrails
       → read-only execute → structured result + evidence
```
Máximo de revisiones configurable. SQL físico no forma parte de la interfaz funcional PeopleOps.

## PROC-04 — Policy Ingestion
```text
Upload → validate file → persist PolicyDocument/Version
→ store original → IngestionJob → parse → chunk
→ metadata → embed → pgvector → verify → completed
```
Una nueva versión no elimina la anterior.

## PROC-05 — Policy Retrieval
```text
Need policy → retrieval intent → metadata/date filters
→ LlamaIndex → evidence verifier
→ sufficient?
   no → POLICY_NOT_FOUND / INSUFFICIENT_DATA
   yes → policy evidence
```
La vigencia de la versión es parte de la validez de la evidencia.

## PROC-06 — Data + Policy Combined Analysis
```text
Question
→ facts via MCP
+ policy via RAG
→ Facts + Rules
→ Reasoning
→ Fact/Rule/Inference separation
→ Human Review decision
```

## PROC-07 — Payroll Explanation
```text
Question → discover payroll capabilities
→ current payroll → comparable period → concepts
→ attendance/overtime/leave as needed
→ deterministic differences
→ policy retrieval if relevant
→ explanation + evidence
```
Si la solicitud requiere datos payroll/HRIS restringidos y el contexto de
seguridad actual no incluye `hr:payroll`, el flujo payroll debe detenerse con
`AUTHORIZATION_DENIED` y pasar a `PROC-14`. No debe gastar rondas adicionales
del modelo intentando entidades payroll alternativas, ni validar/ejecutar una
consulta conceptual payroll sin aprobación.

## PROC-08 — Attendance ↔ Payroll Reconciliation
```text
Period → discover overtime/payroll relations
→ conceptual query → MCP translate/execute
→ compare recorded vs paid → discrepancy set → summarize
```
No crear una tool específica por wording.

## PROC-09 — Human Review
```text
review required → HumanReviewRequest → snapshot evidence
→ AnalysisInteraction=pending_human_review → pause
→ reviewer approve/reject/needs_information
→ persist → resume → synthesis
```
Para autorización payroll restringida, Human Review funciona como punto de
aprobación del mismo análisis bloqueado. La aprobación no otorga permisos
globales al usuario; autoriza una re-ejecución auditada de la solicitud
pendiente con `hr:payroll` registrado explícitamente en el rastro del workflow.

## PROC-10 — Conversation Follow-up
```text
conversation_id → new question → new request_id
→ relevant context → new AnalysisInteraction → normal workflow
```

## PROC-11 — Failure Handling
Tipos conceptuales:
SEMANTIC_ERROR, MCP_DISCOVERY_ERROR, QUERY_VALIDATION_ERROR,
QUERY_EXECUTION_ERROR, POLICY_RETRIEVAL_ERROR, AUTHORIZATION_ERROR,
MODEL_ERROR, HUMAN_REVIEW_ERROR, SYSTEM_ERROR.

```text
Failure → normalize → persist stage/error
→ retry only if policy permits → safe response
```
`AUTHORIZATION_DENIED` desde MCP no es transitorio. Para payroll restringido es
una pausa gobernada: persistir la respuesta segura de autorización, crear el
item de Human Review y esperar la decisión del revisor.

## PROC-12 — Evaluation Run
```text
Versioned cases → execute → capture predictions/evidence
→ deterministic metrics → optional LLM judge → versioned run artifact
```

## PROC-13 — Schema Independence
```text
Evaluation subset
├─ Schema A
└─ Schema B
→ different MCP mappings
→ same PeopleOps build
→ compare outcomes
```
Falla si hay que cambiar PeopleOps para soportar el segundo schema.

## PROC-14 — Restricted Payroll Authorization
```text
User question requires restricted payroll/HRIS data
→ AnalysisInteraction created
→ Functional Analyst discovers available capabilities
→ MCP scoped payroll discovery/read attempt
→ MCP returns AUTHORIZATION_DENIED because hr:payroll is absent
→ PeopleOps persists safe authorization state
→ HumanReviewRequest created with authorization recommendation
→ AnalysisInteraction=pending_human_review
→ Human Review inbox shows the blocked request
→ reviewer decision
   reject / needs_information → persist decision and keep safe response
   approve → re-run the same analysis with explicit hr:payroll scope
→ normal payroll discovery/planning/validation/execution through MCP
→ evidence merge + synthesis
→ AnalysisInteraction completed with human_review_status=approve
```

Reglas:
- `hr:payroll` es requerido antes de exponer filas payroll, campos payroll,
  conceptos payroll, montos payroll o evidencia payroll a nivel empleado.
- El primer intento no autorizado debe fallar cerrado antes de validar o
  ejecutar una consulta conceptual payroll.
- La denegación de autorización del MCP es autoritativa y debe conservarse
  aunque el modelo intente después un alcance de catálogo más amplio o distinto.
- La aprobación está acotada a la solicitud de análisis pendiente. No debe
  mutar permisos globales del usuario, saltarse MCP ni crear acceso directo a
  HRIS.
- La re-ejecución aprobada usa el camino normal PeopleOps API → HRDataGateway
  → MCP Client → Reference MCP Server con `hr:payroll` incluido.
- El análisis final debe quedar auditable en el historial: denegación original,
  decisión de Human Review, scope elevado para la re-ejecución aprobada,
  validación del proveedor, evidencia de ejecución y respuesta final persistida
  en `AnalysisInteraction`.
- No se permiten escrituras payroll/HRIS.
