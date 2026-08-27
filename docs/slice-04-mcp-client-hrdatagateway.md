# Slice 04 — MCP Client & HRDataGateway

**Estado:** Especificación de slice  
**Objetivo:** Conectar PeopleOps al servidor MCP mediante una abstracción estable y demostrar que MCP es la única ruta integrada a datos HR.  
**Dependencias:** Slices 01 y 03.

## 1. Requisitos trazados

- REQ-MCP-001..009
- REQ-AUD-008
- REQ-SEC-004

## 2. Alcance

- Implementar MCP Client real en PeopleOps.
- Implementar HRDataGateway como boundary interno.
- Exponer operaciones genéricas de discovery a la capa superior.
- Propagar request_id y security context.
- Normalizar timeouts/errores MCP.
- Persistir provider type y catalog version en AnalysisInteraction cuando exista acceso.
- Prohibir fallback directo a DB.

## 3. Fuera de alcance

- Query conceptual completa.
- LangGraph completo.
- Policy RAG.
- UI.

## 4. Diseño descriptivo esperado

- LangGraph futuro debe depender de HRDataGateway, no del SDK MCP directamente.
- HRDataGateway no contiene mappings de tablas ERP.
- Errores MCP deben transformarse a errores provider-neutral.
- Timeouts/retries deben ser limitados y configurables.

## 5. Pruebas mínimas

- PeopleOps obtiene capabilities vía MCP.
- Timeout simulado.
- Servidor MCP no disponible.
- Error de contrato.
- Correlación request_id.
- Comprobación de ausencia de DB credentials del HRIS en peopleops-api.

## 6. Impacto en evaluación

- Permite comenzar a medir disponibilidad/latencia provider.
- Establece datos de auditoría para futuras evaluaciones de MCP.

## 7. Definition of Done

- PeopleOps consulta catálogo exclusivamente vía MCP.
- HRDataGateway probado.
- Errores normalizados.
- request_id correlacionado.
- Sin acceso directo alternativo.

## 8. Guardrails y riesgos

- No acoplar el dominio a objetos específicos del SDK MCP.
- No esconder fallos mediante fallback.
- No copiar metadata física a constantes PeopleOps.
