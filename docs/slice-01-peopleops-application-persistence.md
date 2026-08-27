# Slice 01 — PeopleOps Application Persistence

**Estado:** Especificación de slice  
**Objetivo:** Implementar la persistencia propia de PeopleOps y el lifecycle mínimo de una interacción auditable antes de introducir razonamiento agentic.  
**Dependencias:** Slice 00.

## 1. Requisitos trazados

- REQ-AUD-001..011
- REQ-CONV-001..004
- REQ-PHY-004

## 2. Alcance

- Crear PeopleOps Application DB y migraciones.
- Implementar Conversation.
- Implementar AnalysisInteraction con `request_id`, `conversation_id`, status, current_stage y stage_history.
- Preparar campos/snapshots JSONB necesarios para futuras etapas sin sobre-normalizar.
- Crear API mínima para registrar/consultar una interacción.
- Definir servicio de auditoría/stage transition reutilizable.

## 3. Fuera de alcance

- LangGraph.
- MCP.
- Policy RAG.
- Human Review completo.
- Normalización avanzada en tablas AnalysisEvent/AnalysisEvidence.

## 4. Diseño descriptivo esperado

- `AnalysisInteraction` debe crearse antes del futuro workflow.
- `stage_history` debe ser append-only desde la perspectiva del dominio.
- Los errores deben poder persistirse de forma segura.
- Conversation agrupa múltiples request_id sin confundir identidad de ejecución.
- No almacenar prompts internos ni chain-of-thought.

## 5. Pruebas mínimas

- Crear interacción con request_id único.
- Crear follow-up con mismo conversation_id y nuevo request_id.
- Actualizar current_stage y stage_history.
- Persistir error controlado.
- Verificar que stage_history no se reemplaza accidentalmente.
- Test de schema/migración limpio desde cero.

## 6. Impacto en evaluación

- Base para métricas de workflow posteriores.
- Debe permitir reconstruir qué hizo una ejecución sin depender de LangSmith.

## 7. Definition of Done

- Persistencia levantable desde cero.
- CRUD mínimo/lectura de análisis disponible.
- Lifecycle received→stage update→completed/failed probado.
- Tests de unicidad y correlación aprobados.
- Sin dependencia de LangSmith.

## 8. Guardrails y riesgos

- No modelar toda la observabilidad futura ahora.
- No mezclar Evaluation Dataset con tablas de ejecución real.
- No guardar datos sensibles innecesarios.
- No crear una nueva identidad funcional al actualizar un análisis.
