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

## 2.1 Flujo durable de `needs_information`

`needs_information` no es una aprobación, un rechazo ni un estado terminal de
la solicitud. Representa una pausa gobernada porque el revisor necesita un
dato o una aclaración del usuario antes de continuar.

El ciclo definido es:

1. El revisor selecciona `Necesita información` y registra un comentario con el
   dato requerido. La decisión se persiste en `HumanReviewDecision` y el caso
   original conserva su evidencia y su snapshot inmutables.
2. La `AnalysisInteraction` original pasa a `waiting_for_user_information`.
   Su respuesta visible explica que falta información y muestra el comentario
   del revisor. El caso permanece en el historial y queda enlazado como origen
   de la continuación.
3. La interfaz de Análisis muestra un formulario de respuesta únicamente para
   ese estado. El usuario envía la información solicitada; no se modifica la
   pregunta original ni la decisión ya auditada.
4. La API crea una nueva `AnalysisInteraction` con un nuevo `request_id`, la
   misma `conversation_id` y una referencia durable al análisis original.
   Guarda la respuesta del usuario como contexto adicional de esa continuación
   y la ejecuta desde el inicio del workflow.
5. La nueva ejecución vuelve a aplicar interpretación, autorización, MCP,
   políticas, evidencia y Human Review. Si sigue requiriendo aprobación, crea
   una nueva revisión para la continuación; si está autorizada, completa la
   respuesta de la continuación.
6. El historial muestra ambos análisis relacionados. El original conserva el
   estado `waiting_for_user_information`, la solicitud del revisor y la
   respuesta del usuario; la continuación muestra su propio resultado y
   auditoría.

La respuesta del usuario es contexto no confiable: no concede permisos, no
omite validaciones y no puede cambiar por sí sola el estado de revisión. La
continuación debe pasar por el mismo flujo de autorización y por el mismo
camino MCP que una consulta nueva.

## 3. Fuera de alcance

- UI completa de inbox (slice 15).
- Automatizar decisiones sensibles.
- Escrituras en HRIS.

## 4. Diseño descriptivo esperado

- La revisión puede durar horas/días.
- No depender del proceso en memoria.
- La decisión humana es un input autoritativo del workflow, no una sugerencia del LLM.
- needs_information debe dejar estado coherente y auditable.
- needs_information debe permitir una continuación durable con nuevo
  `request_id`, relación con el caso original y retorno al workflow completo.

## 5. Pruebas mínimas

- Pause/resume tras reinicio de proceso si la tecnología elegida lo soporta.
- Approve.
- Reject.
- Needs information.
- Continuación después de información del usuario, con nueva identidad de
  análisis y relación con el caso original.
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
