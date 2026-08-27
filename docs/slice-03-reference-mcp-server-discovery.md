# Slice 03 — Reference MCP Server: Discovery

**Estado:** Especificación de slice  
**Objetivo:** Implementar el Reference MCP Server y demostrar que puede describir el HRIS sin que PeopleOps conozca tablas físicas.  
**Dependencias:** Slice 02.

## 1. Requisitos trazados

- REQ-MCP-003..004
- REQ-DISC-001..009
- REQ-SEC-009

## 2. Alcance

- Crear servidor MCP funcional.
- Exponer capability discovery.
- Exponer entidades/tablas relevantes, campos, tipos, PK/FK/relaciones cuando corresponda.
- Exponer semantic metadata: business name, descripción, roles semánticos, sensibilidad y operaciones.
- Generar catalog version/fingerprint.
- Definir errores tipados de discovery.
- Agregar health/diagnostics técnicos sin frontend.

## 3. Fuera de alcance

- Conceptual query execution.
- LangGraph.
- Frontend MCP.
- Adapters BIZAG/SAP/etc.

## 4. Diseño descriptivo esperado

- El catálogo debe derivarse de schema/config/metadata del servidor, no de conocimiento hardcodeado en PeopleOps.
- Semantic metadata puede combinar introspección física con configuración explícita del servidor.
- Las relaciones deben ser suficientes para permitir planificación posterior.
- El contrato no debe asumir que otros servidores usarán PostgreSQL.

## 5. Pruebas mínimas

- Discovery de capabilities.
- Describe entity con fields.
- Discovery de relationships.
- Fingerprint estable cuando no cambia metadata.
- Fingerprint cambia ante modificación relevante.
- Errores seguros ante entidad inexistente.
- Test de clasificación/sensibilidad.

## 6. Impacto en evaluación

- Base para MCP contract tests.
- Permite medir completeness del catálogo más adelante.

## 7. Definition of Done

- Servidor MCP arrancable.
- Catálogo completo para dominios del HRIS sintético.
- Metadata semántica documentada.
- Tests de discovery aprobados.
- Ningún cambio requerido en PeopleOps para conocer nombres físicos.

## 8. Guardrails y riesgos

- No resolver todavía preguntas de negocio.
- No crear tool por dominio/pregunta si una capability genérica basta.
- No exponer secretos ni detalles físicos innecesarios.
- No introducir UI administrativa.
