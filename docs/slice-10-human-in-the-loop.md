# Slice 10 — Human-in-the-loop

**Estado:** Especificación de slice  
**Objetivo:** Convertir Human Review en un estado durable del workflow, con pausa, persistencia, decisión humana y reanudación.  
**Dependencias:** Slice 09.

## 1. Requisitos trazados

- REQ-HITL-001..007
- REQ-AUD-004..009
- REQ-AGT-003

## 2. Alcance

- Implementar HumanReviewRequest.
- Definir criterios/routing de review como resultado estructurado, no keywords.
- Persistir evidence snapshot y recommendation snapshot.
- Pausar workflow en pending_human_review.
- Implementar API de listado/detalle/decision.
- Soportar approve/reject/needs_information.
- Reanudar la misma AnalysisInteraction/request_id.
- Actualizar stage_history y decisión humana.

## 3. Fuera de alcance

- UI completa de inbox (slice 15).
- Automatizar decisiones sensibles.
- Escrituras en HRIS.

## 4. Diseño descriptivo esperado

- La revisión puede durar horas/días.
- No depender del proceso en memoria.
- La decisión humana es un input autoritativo del workflow, no una sugerencia del LLM.
- needs_information debe dejar estado coherente y auditable.

## 5. Pruebas mínimas

- Pause/resume tras reinicio de proceso si la tecnología elegida lo soporta.
- Approve.
- Reject.
- Needs information.
- Evidence snapshot inmutable lógico.
- Decision audit.
- Error al reanudar.

## 6. Impacto en evaluación

- Medir Human Review routing accuracy con casos conocidos.
- Registrar false positive/false negative de escalamiento.

## 7. Definition of Done

- Workflow durable de revisión funcionando.
- Misma identidad de análisis preservada.
- Decisiones auditadas.
- Tests de lifecycle aprobados.
- Sin efecto transaccional laboral automático.

## 8. Guardrails y riesgos

- No reducir HITL a una pantalla sin pause/resume.
- No crear nuevo request_id al reanudar la misma ejecución.
- No permitir que el LLM simule la decisión humana.
- No almacenar comentarios sensibles innecesarios en logs.
