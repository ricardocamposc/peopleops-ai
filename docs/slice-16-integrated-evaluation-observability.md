# Slice 16 — Integrated Evaluation & Observability

**Estado:** Especificación de slice  
**Objetivo:** Unificar evaluación estructurada, RAG, MCP, workflow y respuesta final en una suite reproducible y trazable.  
**Dependencias:** Slices 08, 10, 11, 12 y 13.

## 1. Requisitos trazados

- REQ-EVAL-001..012
- REQ-AUD-001..011

## 2. Alcance

- Consolidar evaluation dataset global.
- Crear runner versionado.
- Separar métricas por capa: semantic, conceptual query, MCP, RAG, workflow, response.
- Guardar run artifacts JSON/Markdown.
- Registrar latencia/tokens/costes cuando sea útil.
- Integrar LangSmith como observabilidad complementaria si aporta valor.
- Definir baseline y regression thresholds razonables.
- Relacionar evaluation case con request_id/run id.

## 3. Fuera de alcance

- Auto-tuning.
- Continuous evaluation en producción real.
- Dashboards complejos.

## 4. Diseño descriptivo esperado

- Métricas deterministas son referencia primaria cuando existe ground truth objetivo.
- LLM judge debe ser opcional/separado y no ocultar resultados deterministas.
- Los fallos deben atribuirse a la capa correcta.
- Evaluation dataset no se mezcla con AnalysisInteraction.

## 5. Pruebas mínimas

- Run completo reproducible.
- RAG cases.
- Structured query cases.
- MCP contract/schema cases.
- HITL cases.
- Multilingual cases.
- Negative cases.
- Artifact comparison.

## 6. Impacto en evaluación

- Establecer baseline oficial del MVP.
- Documentar métricas, límites y casos fallidos.

## 7. Definition of Done

- Runner único/documentado.
- Artifacts versionables.
- Baseline generado.
- Resultados por capa.
- LangSmith opcional sin dependencia funcional.

## 8. Guardrails y riesgos

- No reducir calidad a una sola métrica.
- No ocultar fallos con retries ilimitados.
- No cambiar expected results para hacer pasar el sistema sin justificar.
