# Slice 13 — MCP Contract & Schema Independence

**Estado:** Especificación de slice  
**Objetivo:** Probar que PeopleOps depende del contrato MCP y metadata semántica, no del schema físico del Reference HRIS.  
**Dependencias:** Slices 05, 06 y 11.

## 1. Requisitos trazados

- REQ-EVAL-010..011
- REQ-DISC-001..009
- REQ-MCP-001..009
- REQ-PHY-004

## 2. Alcance

- Crear MCP contract test suite reutilizable.
- Crear segundo schema físico reducido con nombres y relaciones diferentes.
- Implementar mapping/semantic metadata correspondiente en un servidor/adaptador de test.
- Ejecutar mismo build PeopleOps y subconjunto representativo del evaluation dataset contra ambos orígenes.
- Comparar resultados semánticos y evidence.
- Documentar qué cambia y qué no.

## 3. Fuera de alcance

- Adapter productivo BIZAG/SAP.
- Integration Console.
- Tercer DBMS salvo que sea trivial.

## 4. Diseño descriptivo esperado

- PeopleOps code/prompts no pueden cambiar entre Schema A y B.
- Solo cambian metadata/mapping/source implementation del lado MCP.
- El test debe incluir al menos una relación cross-domain y payroll.
- Debe verificarse que no existan imports/nombres físicos del HRIS en PeopleOps.

## 5. Pruebas mínimas

- Contract discovery suite en ambos servers.
- Conceptual query suite.
- Error normalization.
- Security/limits.
- Evaluation subset Schema A vs B.
- Static check de referencias a nombres físicos.

## 6. Impacto en evaluación

- Métrica principal: equivalencia funcional/schema independence.
- Guardar artifacts comparables de ambos runs.

## 7. Definition of Done

- Contract suite reutilizable.
- Schema B operativo.
- Mismo PeopleOps build supera casos representativos en ambos.
- Informe de independence generado.
- Sin cambios de agentic layer.

## 8. Guardrails y riesgos

- No diseñar Schema B como copia con nombres cambiados solamente; debe variar estructura suficiente para ser prueba útil.
- No modificar PeopleOps para acomodar el test.
- No introducir lógica condicional por provider/schema en agentic layer.
