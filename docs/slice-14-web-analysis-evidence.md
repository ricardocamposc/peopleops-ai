# Slice 14 — PeopleOps Web: Analysis & Evidence

**Estado:** Especificación de slice  
**Objetivo:** Crear la experiencia de consulta que permita al usuario ver respuesta, estado y evidencia sin exponer detalles internos innecesarios.  
**Dependencias:** Slices 06 y 09.

## 1. Requisitos trazados

- REQ-UI-001..004
- REQ-UI-007
- REQ-PROD-004

## 2. Alcance

- Implementar peopleops-web.
- Pantalla Analysis con pregunta/respuesta.
- Mostrar status/current stage mientras aplique.
- Mostrar key findings.
- Separar Data Evidence y Policy Evidence.
- Analysis History con request_id/status/duration/review state.
- Detalle de interacción con stage timeline seguro.
- Integrar con API; nunca conectar frontend directamente al MCP Server.

## 3. Fuera de alcance

- Policy administration completa.
- Human Review inbox.
- MCP admin UI.
- Dashboard BI.

## 4. Diseño descriptivo esperado

- No mostrar chain-of-thought ni prompts internos.
- No mostrar SQL físico como requisito de usuario.
- Evidence debe permitir abrir/ver fuente policy cuando esté disponible.
- Estados de error/insufficient_data deben ser comprensibles.

## 5. Pruebas mínimas

- Submit analysis.
- Polling/refresh status según diseño.
- Completed.
- Failed.
- Insufficient data.
- Policy evidence rendering.
- Structured data evidence rendering.
- History/detail.

## 6. Impacto en evaluación

- No introduce nuevas métricas de modelo; permite validación UX y screenshots.
- Debe facilitar inspección manual de evidence correctness.

## 7. Definition of Done

- Flujo principal usable.
- Evidence claramente separada.
- History operativo.
- Sin conexión directa MCP/DB desde web.
- Responsive desktop-first básico.

## 8. Guardrails y riesgos

- No convertir el frontend en BI.
- No exponer stack traces.
- No duplicar lógica de autorización en cliente como única defensa.
