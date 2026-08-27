# Slice 09 — Combined Data + Policy Workflow

**Estado:** Especificación de slice  
**Objetivo:** Combinar hechos estructurados vía MCP con reglas documentales vía Policy RAG dentro de un único workflow agentic trazable.  
**Dependencias:** Slices 06 y 08.

## 1. Requisitos trazados

- REQ-AGT-008
- REQ-PROD-004..005
- REQ-RAG-RET-004..008
- REQ-HR-007

## 2. Alcance

- Extender LangGraph para ejecutar ramas structured data y Policy RAG según el plan.
- Permitir ejecución de una o ambas fuentes.
- Merge de evidence.
- Separar Facts, Policies e Inference en state y respuesta.
- Resolver Vacation Policy Decision Support como escenario insignia.
- Persistir policy sources/versions y structured evidence en AnalysisInteraction.
- Agregar estados de insufficient data/policy not found/conflict.

## 3. Fuera de alcance

- Human Review durable.
- Payroll profundo.
- Frontend.

## 4. Diseño descriptivo esperado

- El planner decide si necesita policy; no keyword routing.
- Policy evidence no puede transformarse en dato estructurado.
- Structured result no puede presentarse como regla.
- Si facts o policy son insuficientes, el sistema debe declararlo.

## 5. Pruebas mínimas

- Data-only question.
- Policy-only question.
- Data+policy question.
- Historical policy.
- Missing policy.
- Policy conflict.
- Missing HR fact.
- Paráfrasis del escenario Vacation.

## 6. Impacto en evaluación

- Agregar métricas de correct branch, unnecessary source calls, fact/policy coverage y unsupported claims.

## 7. Definition of Done

- Workflow combinado estable.
- Vacation scenario resuelto con evidence.
- Fact/Rule/Inference visible en salida estructurada.
- AnalysisInteraction conserva ambas fuentes.
- Casos insuficientes no alucinan.

## 8. Guardrails y riesgos

- No obligar a consultar RAG siempre.
- No obligar a consultar MCP siempre.
- No resolver conflictos documentales inventando prioridad.
- No fusionar evidence sin provenance.
