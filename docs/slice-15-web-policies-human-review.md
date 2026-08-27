# Slice 15 — PeopleOps Web: Policies & Human Review

**Estado:** Especificación de slice  
**Objetivo:** Completar la interfaz operativa para administrar policies y gestionar revisiones humanas.  
**Dependencias:** Slices 07, 08, 10 y 14.

## 1. Requisitos trazados

- REQ-UI-005..006
- REQ-RAG-ING-001
- REQ-HITL-005..006

## 2. Alcance

- Policies list/search/filter.
- Upload new policy.
- Upload new version.
- Mostrar metadata, vigencia, status e ingestion state.
- Ver documento original.
- Acción de reindex si falló.
- Human Review inbox.
- Detalle con facts, policies, recommendation, reason y warnings.
- Approve/reject/needs_information con confirmación.

## 3. Fuera de alcance

- Editor de semantic mapping MCP.
- Editor de chunks como fuente principal.
- Employee master maintenance.
- Workflow designer.

## 4. Diseño descriptivo esperado

- Una policy version debe ser visible independientemente de otras.
- Review actions deben reflejar auditoría y estado.
- Datos sensibles deben respetar scope.
- Uploads fallidos deben quedar claramente diferenciados de policy disponible.

## 5. Pruebas mínimas

- Upload/version.
- Failed ingestion display.
- View policy history.
- Review approve/reject/needs_information.
- Concurrent/duplicate decision handling básico.
- Unauthorized review/payroll evidence.

## 6. Impacto en evaluación

- Facilita pilot/demo; no cambia evaluación agentic.
- Puede añadirse test E2E de lifecycle policy y review.

## 7. Definition of Done

- Administración documental usable.
- Inbox HITL usable.
- Estados consistentes con backend.
- E2E mínimo aprobado.
- Sin frontend MCP.

## 8. Guardrails y riesgos

- No editar source facts de policy manualmente para corregir RAG.
- No permitir decisiones sin confirmación/audit.
- No exponer evidence sensible fuera de scope.
