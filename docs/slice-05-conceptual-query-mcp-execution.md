# Slice 05 — Conceptual Query Contract & MCP Execution

**Estado:** Especificación de slice  
**Objetivo:** Crear el contrato declarativo provider-neutral y ejecutar consultas read-only seguras traducidas por el Reference MCP Server.  
**Dependencias:** Slices 03 y 04.

## 1. Requisitos trazados

- REQ-QRY-001..009
- REQ-EXEC-001..009
- REQ-MCP-004
- REQ-SEM-005

## 2. Alcance

- Definir schema tipado de Conceptual Query.
- Soportar entities, select/metrics, filters, relationships, time scopes, comparisons, ordering y limit según necesidades del MVP.
- Validar query contra el catálogo semántico.
- Traducir en Reference MCP Server a PostgreSQL.
- Validar query física/AST o mecanismo equivalente.
- Aplicar read-only, row limit, timeout y scope.
- Devolver structured result + evidence provider-neutral.
- Implementar feedback de validación para permitir replan posterior.

## 3. Fuera de alcance

- Interpretación de lenguaje natural.
- LangGraph.
- RAG.
- Schema alternativo.

## 4. Diseño descriptivo esperado

- El query conceptual no debe convertirse en SQL textual disfrazado.
- Las referencias deben usar IDs/nombres semánticos del catálogo.
- La traducción física pertenece exclusivamente al MCP Server.
- El servidor debe rechazar operaciones no soportadas antes de ejecutar.
- Evidence debe permitir saber qué datos/capabilities sustentaron el resultado.

## 5. Pruebas mínimas

- Consulta simple.
- Filtro.
- Relación/join.
- Agregación.
- Comparación de períodos.
- Campo inexistente.
- Relación inválida.
- Intento de write.
- Row limit/timeout.
- Query física inválida.

## 6. Impacto en evaluación

- Primer conjunto de casos deterministas para structured query correctness.
- Base para medir validation success y execution correctness.

## 7. Definition of Done

- Contrato tipado versionado.
- Traducción PostgreSQL funcional.
- Guardrails read-only probados.
- Evidence estructurada.
- Errores provider-neutral.
- PeopleOps sigue sin SQL físico.

## 8. Guardrails y riesgos

- No generar SQL en prompts de PeopleOps.
- No permitir raw SQL escape hatch.
- No ampliar DSL para casos no requeridos.
- No usar validación del LLM como único guardrail.
