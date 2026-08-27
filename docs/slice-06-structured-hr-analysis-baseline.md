# Slice 06 — Structured HR Analysis Baseline

**Estado:** Especificación de slice  
**Objetivo:** Implementar el primer workflow agentic capaz de responder preguntas HR nuevas mediante comprensión semántica, planning dinámico y MCP, sin Policy RAG.  
**Dependencias:** Slice 05.

## 1. Requisitos trazados

- REQ-PROD-001..005
- REQ-SEM-001..005
- REQ-AGT-001..007
- REQ-HR-001..007
- REQ-CONV-001..004

## 2. Alcance

- Implementar LangGraph con state tipado.
- Interpretar pregunta a structured semantic request.
- Seleccionar capabilities por metadata, no por keywords.
- Construir plan y conceptual queries.
- Ejecutar mediante HRDataGateway/MCP.
- Permitir revisión/replan limitada ante validación fallida.
- Sintetizar facts con evidence.
- Actualizar AnalysisInteraction por stages.
- Implementar follow-up conversacional básico.

## 3. Fuera de alcance

- Policy RAG.
- Human Review.
- Payroll profundo más allá de casos básicos.
- Frontend.

## 4. Diseño descriptivo esperado

- No crear agentes por módulo HR.
- El planner debe poder combinar dominios.
- Los cálculos reproducibles deben ejecutarse en código/resultado estructurado.
- La síntesis no puede alterar cifras.
- Debe distinguir dato insuficiente de error técnico.

## 5. Pruebas mínimas

- Preguntas simples employee/contract/attendance/vacation.
- Pregunta cross-domain.
- Paráfrasis no vista.
- Pregunta fuera del catálogo.
- Validación fallida seguida de un replan máximo controlado.
- Follow-up con conversation_id.
- Unsupported claim check básico.

## 6. Impacto en evaluación

- Crear baseline inicial structured-data.
- Medir semantic interpretation, query features, result correctness y unnecessary calls.

## 7. Definition of Done

- Workflow LangGraph multi-step real.
- Preguntas no preprogramadas resueltas.
- Sin keywords ni functions por wording.
- AnalysisInteraction completo por ejecución.
- Casos estructurados base aprobados.

## 8. Guardrails y riesgos

- No introducir Policy RAG de forma parcial.
- No esconder errores de planner con reglas estáticas.
- No convertir los ejemplos del dataset en conditions hardcodeadas.
- No permitir loops sin límite.
