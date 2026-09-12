# Semantic Analysis Capability Plan

Estado: `IN_PROGRESS`
Ultima actualizacion: `2026-09-12`
Responsable operativo: Codex, siguiendo `AGENTS.md`

## Objetivo

Elevar PeopleOps AI desde una aplicacion que ejecuta agentes, herramientas y
queries validas hacia una aplicacion que pueda analizar preguntas de negocio,
convertir conceptos humanos en condiciones verificables, comprobar la cobertura
semantica de las queries y abstenerse cuando la evidencia no soporte una
respuesta correcta.

El caso que motiva este plan fue:

```text
Que empleados tienen contrato vigente?
```

La falla observada no fue de ejecucion MCP ni de persistencia. La aplicacion
pudo producir una query valida y devolver filas, pero uso una senal insuficiente
de estado y omitio las condiciones temporales que prueban vigencia:

```text
record.valid_from <= fecha_de_referencia
AND (record.valid_to IS NULL OR record.valid_to >= fecha_de_referencia)
```

Este plan no debe resolverse con reglas especificas para contratos. El objetivo
es soportar patrones generales como vigente, vencido, pendiente, abierto,
cerrado, mayor que un umbral, proximo a vencer, sin relacion vigente y otros
conceptos que requieran transformar lenguaje de negocio en condiciones
verificables.

## Principios

- Mantener MCP como unico camino hacia HRIS.
- No introducir SQL fisico ni nombres de tablas fisicas en PeopleOps API.
- No agregar routing por palabras clave ni listas de frases por idioma.
- Usar salidas estructuradas para intencion semantica, query planning,
  verificacion y sintesis.
- Separar validacion tecnica de validacion semantica.
- Persistir evidencia, advertencias, decisiones y resultados verificables sin
  almacenar chain-of-thought privado.
- Fallar con `insufficient_data` o advertencias accionables cuando la evidencia
  no alcance.

## Alcance

Incluido:

- Enriquecer la intencion semantica con interpretaciones operacionales.
- Ampliar `ConceptualQuery` para filtros logicos agrupados.
- Permitir planes con multiples queries cuando una condicion no pueda expresarse
  como una sola query conceptual.
- Crear un verificador semantico independiente de la validacion MCP existente.
- Fortalecer el reviewer para evaluar cobertura semantica, no solo ejecucion.
- Agregar evaluaciones genericas de patrones de analisis.
- Exponer en trazas y respuestas informacion suficiente para auditar por que una
  respuesta fue considerada soportada.

Excluido:

- Conectar PeopleOps API directamente al HRIS.
- Agregar SQL como escape hatch.
- Crear un agente por modulo de negocio.
- Codificar reglas especificas para una pregunta, idioma o dataset.
- Cambiar la arquitectura base sin ADR aprobado.

## Estado De Seguimiento

| Track | Estado | Resultado esperado | Evidencia al completar |
| --- | --- | --- | --- |
| A. Intencion semantica operacional | `IMPLEMENTED_PARTIAL` | La app representa conceptos de negocio como condiciones verificables y supuestos explicitos. | Tests de contratos Pydantic, traces con interpretacion operacional. |
| B. Query conceptual con logica agrupada | `IMPLEMENTED` | `ConceptualQuery` soporta `AND`, `OR`, `NOT`, comparaciones, null checks y agrupacion. | Tests MCP de validacion, traduccion y ejecucion read-only. |
| C. Planes multi-query y union semantica | `IMPLEMENTED_PARTIAL` | El planner puede resolver conceptos que requieren mas de una query conceptual. | Tests de workflow con planes de comparacion/union y run real focalizado. |
| D. Semantic Coverage Verifier | `IMPLEMENTED_PARTIAL` | Un verificador distinto al MCP detecta queries tecnicamente validas pero semanticamente incompletas. | Tests que rechazan evidencia insuficiente aunque existan filas. |
| E. Reviewer semantico | `IMPLEMENTED_PARTIAL` | El Senior Reviewer usa la verificacion semantica antes de aprobar. | Traces con aprobacion/rechazo fundado en cobertura. |
| F. Sintesis protegida | `IMPLEMENTED_PARTIAL` | La sintesis no convierte datos parciales en respuesta `completed`. | Tests de `insufficient_data` y advertencias accionables. |
| G. Evaluacion generica | `IMPLEMENTED_PARTIAL` | Casos reproducibles cubren patrones, no preguntas hardcodeadas. | Artifacts en `evaluation/runs/phaseNN/`. |
| H. UI/auditoria visible | `IMPLEMENTED_PARTIAL` | La interfaz muestra interpretacion, queries y advertencias relevantes. | Viewer de runs/traces, endpoint de detalle auditado desde DB y UI producto con timeline enriquecido. |

## Fase A: Intencion Semantica Operacional

Objetivo: ampliar la salida estructurada del Functional Analyst para que no solo
identifique entidades, fuentes y filtros textuales, sino que tambien capture la
interpretacion operacional de conceptos de negocio.

Diseno esperado:

- Agregar un contrato tipado para conceptos inferidos, por ejemplo:
  - `business_concept`
  - `operational_definition`
  - `reference_date`
  - `required_conditions`
  - `optional_conditions`
  - `assumptions`
  - `confidence`
  - `requires_verification`
- Resolver expresiones relativas usando la fecha de ejecucion registrada, no una
  fecha implicita del modelo.
- Permitir que el modelo proponga condiciones generales cuando el catalogo
  contiene campos compatibles.
- Registrar cuando una condicion es inferida y cuando viene explicitamente del
  usuario.

Criterios de aceptacion:

- [x] La intencion para "contrato vigente" incluye fecha de referencia,
      inicio efectivo y fin nulo o futuro.
- [ ] La intencion para "facturas vencidas" puede expresarse como fecha de
      vencimiento menor a la referencia y ausencia de pago/cierre si el catalogo
      lo soporta.
- [ ] Si faltan campos necesarios, el resultado es `insufficient_data` o
      `needs_clarification`, no una respuesta inventada.
- [ ] No se agregan reglas por frase ni listas de sinonimos por idioma.

Estado 2026-09-11:

- [x] `SemanticRequest` acepta `operational_conditions` tipadas como filtros o
      grupos de filtros provider-neutral.
- [x] Prompts de Functional Analyst actualizados para declarar condiciones
      operacionales cuando el significado de negocio las requiere y el catalogo
      las soporta.
- [x] Smoke real con API/MCP/OpenAI resolvio el caso de contrato vigente con
      condiciones operacionales temporales y excluyo registros terminados antes
      de la fecha de referencia.
- [ ] Falta estabilizar la produccion de condiciones operacionales en el
      baseline completo para patrones genericos, especialmente comparaciones
      temporales y solicitudes ambiguas.

## Fase B: Query Conceptual Con Logica Agrupada

Objetivo: permitir condiciones logicas provider-neutral sin filtrar hacia SQL
fisico en PeopleOps.

Diseno esperado:

- Evolucionar `ConceptualQuery` con un arbol de filtros:
  - `and`
  - `or`
  - `not`
  - `predicate`
- Mantener compatibilidad temporal con `filters` planos si es necesario.
- Soportar operadores existentes: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`,
  `not_in`, `is_null`, `not_null`.
- Traducir la logica agrupada dentro del Reference MCP Server, no en PeopleOps
  API.
- Validar limites de profundidad, cantidad de nodos y campos permitidos.

Criterios de aceptacion:

- [x] Puede expresarse `A AND (B OR C)` sin multiples queries.
- [x] El MCP valida campos, operadores, scopes, profundidad y limites.
- [x] La traduccion SQL queda encapsulada en el servidor MCP.
- [x] Las queries siguen siendo read-only, acotadas por timeout y limite.

Estado 2026-09-11:

- [x] `ConceptualQuery` acepta `where` como arbol agrupado con `and`, `or` y
      `not`, manteniendo `filters` planos por compatibilidad.
- [x] El Reference MCP Server valida referencias dentro de `where`.
- [x] El Reference MCP Server traduce `where` a SQL parametrizado provider-side.
- [x] `filters` y `where` coexisten y se combinan con `AND`.
- [x] Tests cubren `A AND (B OR C)`, campo desconocido y shape invalido de
      `not`.
- [x] Smoke real `production-smoke-semantic-20260911-154648` ejecuto flujo
      API -> MCP -> PostgreSQL con `where` agrupado y devolvio solo registros
      vigentes soportados por fecha.

## Fase C: Planes Multi-Query

Objetivo: permitir que el planner emita mas de una query conceptual cuando el
concepto solicitado requiera union, interseccion, exclusion o comparacion entre
resultados.

Diseno esperado:

- `AnalysisPlan` debe poder representar:
  - queries independientes;
  - dependencia entre queries;
  - estrategia de combinacion provider-neutral;
  - claves de deduplicacion;
  - razon por la cual se requiere mas de una query.
- La combinacion debe ocurrir sobre evidencia normalizada, no sobre SQL.
- El resultado combinado debe conservar provenance de cada query.

Criterios de aceptacion:

- [x] Se puede resolver una condicion equivalente a `end_date IS NULL OR
      end_date >= reference_date` con una query agrupada o con dos queries y
      union documentada.
- [x] La deduplicacion es deterministica cuando la estrategia declara claves de
      deduplicacion.
- [x] La evidencia final conserva los hashes/queries fuente.
- [x] Si una query parcial falla, la respuesta no se marca como completa sin
      advertencia.

Estado 2026-09-12:

- [x] `AnalysisPlan` incluye `QueryCombination` con estrategia, claves de
      deduplicacion, politica de falla parcial y razon del plan.
- [x] El Query Programmer recibe instrucciones provider-neutral para emitir
      multiples queries cuando la pregunta requiere evidencias separadas,
      comparacion de periodos, union, interseccion o exclusion.
- [x] El workflow normaliza comparaciones temporales que el modelo entrega como
      filtros incompatibles en una sola query y las expande a queries separadas
      con `time_scope` fechado.
- [x] La cobertura semantica acepta que una condicion `or` este cubierta por un
      plan con estrategia `union`, siempre que cada rama quede cubierta por
      alguna query del plan.
- [x] Tests unitarios cubren expansion de periodo actual/anterior, ventanas
      temporales multiples, grano mensual para rangos multi-mes, union semantica
      y no duplicacion de campos seleccionados como dimensiones.
- [ ] Falta ampliar combinacion materializada de resultados para interseccion,
      diferencia y comparaciones con calculos derivados; por ahora se conserva
      provenance por query y la sintesis opera sobre evidencias separadas.

## Fase D: Semantic Coverage Verifier

Objetivo: agregar una verificacion distinta de las validaciones MCP actuales.
Esta capa no decide si la query es valida tecnicamente; decide si la query y sus
resultados cubren la intencion semantica.

Debe verificar:

- Que cada condicion requerida tenga cobertura en la query o en el plan.
- Que se usen campos disponibles cuando son necesarios para probar el concepto.
- Que no se use una senal debil si existe una senal mas fuerte indispensable.
- Que las filas devueltas no contradigan las condiciones operacionales.
- Que la respuesta final no omita advertencias criticas.

Ejemplo de rechazo esperado:

```text
Pregunta: registros vigentes
Query: record.state = active
Resultado: filas encontradas
Decision: SEMANTICALLY_INCOMPLETE
Motivo: la query no verifica vigencia temporal contra la fecha de referencia.
```

Criterios de aceptacion:

- [x] Rechaza una query de "vigente" que solo use `status`.
- [ ] Rechaza una query de "vencido" que no compare fecha contra referencia.
- [ ] Rechaza una query de "pendiente de pago" si no usa campos que prueben pago
      o cierre cuando el catalogo los expone.
- [x] Produce advertencias seguras y persistibles.
- [x] No accede al HRIS ni ejecuta SQL.

Estado 2026-09-11:

- [x] Agregado `SemanticCoverageVerifier` en PeopleOps API.
- [x] El verifier compara condiciones operacionales tipadas contra el plan/query
      conceptual sin ejecutar SQL ni acceder al HRIS.
- [x] Detecta queries con filas pero cobertura semantica incompleta.
- [x] Puede detectar contradicciones fila-condicion cuando los campos necesarios
      estan proyectados en el resultado.
- [ ] Falta ampliar casos para otros patrones: vencido, pendiente, umbral,
      proximo a vencer, ausencia de relacion vigente y comparaciones sin
      metrica explicita.

## Fase E: Reviewer Semantico

Objetivo: hacer que el Senior Reviewer use la verificacion semantica como una
herramienta obligatoria antes de aprobar evidencia estructurada.

Criterios de aceptacion:

- [x] El reviewer no aprueba solo porque MCP valido y ejecuto.
- [x] El reviewer puede solicitar replanificacion cuando falta cobertura.
- [x] Las decisiones quedan en `evaluation_trace` y `stage_history`.
- [x] El flujo evita loops infinitos con presupuesto/reintentos acotados.

Estado 2026-09-11:

- [x] El Senior Reviewer tool-calling expone `verify_semantic_coverage`.
- [x] La aprobacion exige cobertura semantica `COMPLETE` cuando existen
      `operational_conditions`.
- [x] El workflow aplica un override deterministico: un `APPROVE` del modelo se
      transforma en `REVISE` si el plan no cubre condiciones operacionales.
- [x] La traza `senior_reviews` conserva el resultado de cobertura semantica.
- [ ] Falta prueba real con OpenAI/tool-calling verificando que el reviewer use
      la herramienta en una ejecucion completa de API.

## Fase F: Sintesis Protegida

Objetivo: impedir que la etapa de sintesis convierta evidencia parcial en una
respuesta final confiada.

Criterios de aceptacion:

- [x] Una query con filas pero cobertura semantica incompleta no se convierte en
      `completed`.
- [ ] La respuesta distingue hechos, inferencias, supuestos y advertencias.
- [x] La sintesis puede decir "no puedo responder con los datos disponibles" de
      forma normal, sin error interno.

Estado 2026-09-11:

- [x] `_merge_evidence` adjunta `semantic_coverage` a la evidencia estructurada.
- [x] `_synthesize` ya no considera disponible evidencia estructurada con
      cobertura `INCOMPLETE` o `CONTRADICTED`.
- [x] Workflow test cubre filas presentes con cobertura incompleta y estado
      final `insufficient_data`.
- [ ] Falta estabilizar validacion de claims numericos en sintesis para evitar
      afirmaciones cuantitativas no soportadas por evidencia. Esta mejora queda
      diferida por decision explicita del usuario hasta cerrar el incremento de
      planning/cobertura semantica.

## Fase G: Evaluacion Generica

Objetivo: agregar casos de evaluacion por patrones de analisis, no por la frase
exacta del usuario.

Patrones iniciales:

- vigente/actual/effective as of date;
- vencido/expired/overdue;
- pendiente/open/unpaid;
- mayor/menor que umbral;
- proximo a vencer;
- ausencia de relacion vigente;
- contradiccion entre status y fechas;
- insuficiencia de campos.

Criterios de aceptacion:

- [ ] Cada patron tiene casos en espanol, ingles y portugues cuando aplique.
- [ ] Los expected results usan ground truth deterministico.
- [x] Los resultados observados se guardan en `evaluation/runs/phaseNN/`.
- [ ] No se alteran prompts con preguntas especificas para mejorar el score.

Estado 2026-09-12:

- [x] Smoke de 8 casos guardado en
      `evaluation/runs/phase44/production-smoke-semantic-20260911-154648`, con
      8/8 completados.
- [x] Baselines y rechecks guardados bajo `evaluation/runs/phase44/`.
- [x] El viewer de evaluacion descubre los runs por fase y muestra flujo,
      rondas de modelo, llamadas de herramienta, validaciones, cobertura
      semantica y respuesta final.
- [ ] El baseline completo aun no esta estable: la corrida
      `production-baseline-semantic-20260911-175819` completo 29/36; rechecks
      focales posteriores demostraron mejoras en casos especificos y el run
      focalizado `production-baseline-targeted-20260912-030000` completo 7/10,
      con 2 insuficiencias esperadas por falta de evidencia/dominio y 1 bloqueo
      de autorizacion. Falta una corrida completa donde solo queden casos
      genuinamente irresolubles o no autorizados.
- [ ] Falta cubrir los patrones iniciales en espanol, ingles y portugues con
      expected results deterministas.
- [x] Se removieron ejemplos fixture/HRIS de prompts runtime introducidos
      durante la implementacion; las pruebas/evaluaciones pueden seguir usando
      identificadores sinteticos porque no forman parte de la logica runtime.

## Fase H: UI Y Auditoria Visible

Objetivo: que el usuario pueda entender por que la aplicacion respondio,
abstuvo o pidio mas datos.

Criterios de aceptacion:

- [ ] La UI muestra interpretacion operacional resumida.
- [ ] La UI muestra queries conceptuales o referencias auditables.
- [ ] La UI muestra advertencias de cobertura insuficiente.
- [ ] La UI no expone SQL fisico ni detalles sensibles.

Estado 2026-09-12:

- [x] El viewer de evaluaciones muestra el flujo auditable de Phase 4.4:
      interpretacion funcional, query conceptual, validacion MCP, cobertura
      semantica, revisiones y respuesta final.
- [x] Los artifacts por caso contienen `semantic_coverage`, `senior_reviews`,
      `provider_validations`, `provider_executions` y `audit_trail`.
- [x] La UI producto consume `/api/v1/analysis/{request_id}/details`, una vista
      segura derivada de `AnalysisInteraction` persistido en DB, no de JSON de
      evaluacion.
- [x] La ficha Detalles muestra resumen de auditoria, etapas de workflow,
      interpretacion semantica, plan conceptual, validaciones/ejecuciones MCP,
      revision semantica y sintesis sin exponer prompts ni mensajes internos.
- [x] La pantalla principal agrega animacion de procesamiento al boton
      Analizar, scroll interno del historial y polling acotado al analisis
      seleccionado mientras su estado no sea terminal.
- [ ] Falta decidir si el siguiente paso de auditoria requiere normalizar el
      `audit_trail` JSONB en una tabla/event stream consultable. La alternativa
      actual evita duplicar persistencia y sirve a la UI; una tabla separada
      tendria sentido cuando se necesiten filtros historicos por nodo,
      herramienta, latencia o actor.

## Secuencia Recomendada

1. Documentar contratos actuales y agregar tests de regresion que fallen con el
   comportamiento actual.
2. Implementar `SemanticIntent`/conceptos operacionales en PeopleOps API.
3. Extender `ConceptualQuery` con grupos logicos en contratos compartidos.
4. Implementar validacion/traduccion de grupos logicos en Reference MCP Server.
5. Agregar soporte planner para query agrupada o multi-query.
6. Crear `SemanticCoverageVerifier`.
7. Integrar el verifier en reviewer y workflow antes de sintesis.
8. Ajustar sintesis para respetar cobertura semantica.
9. Agregar evaluaciones genericas y guardar runs reproducibles.
10. Exponer interpretacion y advertencias en API/UI.
11. Actualizar este documento con estado, decisiones, tests y evidencias.

## Preguntas De Diseno Pendientes

- Que formato final debe tener el arbol logico: mantener `filters` como legado o
  migrar a `where` como estructura principal?
- La combinacion multi-query debe ser parte de `AnalysisPlan` solamente o tambien
  del contrato MCP?
- El verificador semantico debe ser deterministico puro, LLM con salida
  estructurada, o hibrido con reglas generales verificables?
- Que fase/slice numerado del roadmap debe alojar esta mejora transversal?
- Que informacion de auditoria semantica debe mostrarse en la UI por defecto?

## Bitacora De Implementacion

Actualizar esta tabla al finalizar cada implementacion relacionada con este
plan.

| Fecha | Cambio | Archivos principales | Verificacion | Estado |
| --- | --- | --- | --- | --- |
| 2026-09-11 | Plan inicial creado a partir de auditoria del caso "contrato vigente". | `docs/SEMANTIC-ANALYSIS-CAPABILITY-PLAN.md`, `AGENTS.md` | Documentacion solamente. | `PLANNED` |
| 2026-09-11 | Primer incremento implementado: `where` agrupado en `ConceptualQuery`, traduccion MCP provider-side, `operational_conditions` en `SemanticRequest`, `SemanticCoverageVerifier`, prompts actualizados y sintesis protegida ante cobertura incompleta. | `apps/peopleops-api/src/peopleops_api/query_contracts.py`, `apps/reference-mcp-server/src/reference_mcp_server/query_contracts.py`, `apps/reference-mcp-server/src/reference_mcp_server/execution.py`, `apps/reference-mcp-server/src/reference_mcp_server/main.py`, `apps/peopleops-api/src/peopleops_api/analysis_contracts.py`, `apps/peopleops-api/src/peopleops_api/semantic_coverage.py`, `apps/peopleops-api/src/peopleops_api/analysis_workflow.py`, prompts Query Programmer/Functional Analyst, tests. | `pytest tests/test_execution.py tests/test_discovery.py`; `ruff check src tests/test_execution.py tests/test_discovery.py`; `pytest tests/test_analysis_workflow.py tests/test_openai_structured_schema.py tests/test_temporal_resolution.py`; `ruff check src tests/test_analysis_workflow.py tests/test_openai_structured_schema.py tests/test_temporal_resolution.py`. | `IN_PROGRESS` |
| 2026-09-11 | Segundo incremento implementado: reviewer semantico con herramienta `verify_semantic_coverage`, bloqueo de aprobacion sin cobertura completa, override deterministico del workflow y preflight local para campos dentro de `where`. | `apps/peopleops-api/src/peopleops_api/senior_reviewer_agent.py`, `apps/peopleops-api/src/peopleops_api/resources/prompts/senior-reviewer.md`, `apps/peopleops-api/src/peopleops_api/analysis_workflow.py`, `apps/peopleops-api/tests/test_analysis_workflow.py`, `docs/SEMANTIC-ANALYSIS-CAPABILITY-PLAN.md`. | `pytest tests/test_analysis_workflow.py tests/test_openai_structured_schema.py tests/test_temporal_resolution.py`; `ruff check src tests/test_analysis_workflow.py tests/test_openai_structured_schema.py tests/test_temporal_resolution.py`. | `IN_PROGRESS` |
| 2026-09-11 | Tercer incremento implementado: presupuesto dinamico de agentes segun herramientas disponibles, normalizacion estructural de payloads del Query Programmer, soporte conceptual para dimensiones temporales derivadas, fallback de auto-envio solo para queries ya validadas, propagacion correcta de errores MCP de autorizacion y limpieza de nombres fisicos/fixture en prompts runtime. | `apps/peopleops-api/src/peopleops_api/functional_analyst_agent.py`, `apps/peopleops-api/src/peopleops_api/query_programmer_agent.py`, `apps/peopleops-api/src/peopleops_api/analysis_workflow.py`, `apps/peopleops-api/src/peopleops_api/mcp_client.py`, `apps/reference-mcp-server/src/reference_mcp_server/execution.py`, `apps/peopleops-api/src/peopleops_api/resources/prompts/*.md`, `apps/peopleops-api/src/peopleops_api/resources/prompts/phase44/query-programmer.md`, tests API/MCP. | API: `pytest tests/test_analysis_workflow.py tests/test_openai_structured_schema.py` => 80 passed; `ruff check src tests/test_analysis_workflow.py tests/test_openai_structured_schema.py` => passed. MCP: `pytest tests/test_discovery.py tests/test_execution.py` => 34 passed; `ruff check src tests/test_discovery.py tests/test_execution.py` => passed. Smoke: `evaluation/runs/phase44/production-smoke-semantic-20260911-154648` => 8/8 completed. Baseline: `evaluation/runs/phase44/production-baseline-semantic-20260911-175819` => 29/36 completed; focused recheck `evaluation/runs/phase44/production-baseline-recheck-20260911-175302` proved P44-012/P44-017 completed; focused recheck `evaluation/runs/phase44/production-baseline-recheck-20260911-175651` proved P44-022 completed and P44-019 degrades to insufficient data without internal budget error. Prompt scan for physical fixture examples in runtime prompts returned no matches. | `IN_PROGRESS` |
| 2026-09-12 | Documento de seguimiento actualizado contra el estado real: se marcaron como implementados los criterios ya probados, se separo viewer/evaluacion de UI producto, y se registro la brecha restante del baseline completo. | `docs/SEMANTIC-ANALYSIS-CAPABILITY-PLAN.md` | Revision de `git status`, artifacts en `evaluation/runs/phase44/`, tests unitarios existentes y secciones de viewer. Sin cambios de runtime. | `IN_PROGRESS` |
| 2026-09-12 | Cuarto incremento implementado: planes multi-query parciales, normalizacion estructural de comparaciones temporales en varias queries, cobertura semantica a nivel de plan para uniones, y estabilizacion focalizada de casos complejos del baseline sin introducir nombres fisicos en prompts runtime. | `apps/peopleops-api/src/peopleops_api/analysis_contracts.py`, `apps/peopleops-api/src/peopleops_api/analysis_workflow.py`, `apps/peopleops-api/src/peopleops_api/semantic_coverage.py`, `apps/peopleops-api/src/peopleops_api/query_programmer_agent.py`, prompts Query Programmer, `apps/peopleops-api/tests/test_analysis_workflow.py`, `docs/SEMANTIC-ANALYSIS-CAPABILITY-PLAN.md`. | API: `pytest tests/test_analysis_workflow.py tests/test_openai_structured_schema.py` => 85 passed; `ruff check src tests/test_analysis_workflow.py tests/test_openai_structured_schema.py` => passed. MCP: `pytest tests/test_discovery.py tests/test_execution.py` => 34 passed; `ruff check src tests/test_discovery.py tests/test_execution.py` => passed. Run real focalizado `evaluation/runs/phase44/production-baseline-targeted-20260912-030000`: 7/10 completed, 2 insufficient_data, 1 authorization failure; P44-020 genero 2 queries con cobertura COMPLETE. | `IN_PROGRESS` |
| 2026-09-12 | Quinto incremento implementado: preservacion de denegaciones `AUTHORIZATION_DENIED` emitidas por MCP durante descubrimiento sensible aunque el analista intente otros scopes despues, respuesta de autorizacion como restriccion funcional para la UI, y sintesis compacta para resultados tabulares sin duplicar filas en el resumen. | `apps/peopleops-api/src/peopleops_api/functional_analyst_agent.py`, `apps/peopleops-api/src/peopleops_api/analysis_workflow.py`, `apps/peopleops-api/tests/test_analysis_workflow.py`, `apps/peopleops-api/tests/test_persistence.py`, `docs/SEMANTIC-ANALYSIS-CAPABILITY-PLAN.md`. | `pytest tests/test_analysis_workflow.py tests/test_persistence.py` => 76 passed; `ruff check src/peopleops_api/analysis_workflow.py src/peopleops_api/functional_analyst_agent.py tests/test_analysis_workflow.py tests/test_persistence.py` => passed. Prueba real API con servicios desde fuente: `Que trabajadores ganan mas de 1000?` => `insufficient_data` con `AUTHORIZATION_ERROR` y mensaje de permisos; `lista todos los trabajadores` => `completed`, 4 filas en tabla y resumen compacto sin enumerar filas. | `IN_PROGRESS` |
| 2026-09-12 | Correccion de regresion de payroll: Human Review ya no eleva scopes ni reinicia el workflow con permisos fabricados; la autorizacion `hr:payroll` se valida siempre de forma determinista antes de cualquier validacion/ejecucion MCP, incluso cuando el plan conceptual intenta leer payroll sin declararlo semanticamente. Las denegaciones crean una revision durable pendiente y conservan la respuesta funcional de permisos. | `apps/peopleops-api/src/peopleops_api/analysis_workflow.py`, `apps/peopleops-api/src/peopleops_api/main.py`, `apps/peopleops-api/tests/test_analysis_workflow.py`. | `pytest tests/test_analysis_workflow.py tests/test_human_review.py tests/test_persistence.py` => 85 passed; prueba focalizada de payroll => 9 passed; Ruff passed; no quedan referencias runtime a elevacion `approved_human_review`/`_provider_security`. | `IN_PROGRESS` |
| 2026-09-12 | Correccion del flujo gobernado de payroll restringido: una denegacion por falta de `hr:payroll` pausa la misma `AnalysisInteraction` en `pending_human_review`, crea item durable de Human Review y no valida/ejecuta payroll. Si el revisor aprueba, la misma request se re-ejecuta una sola vez con `hr:payroll` agregado al contexto de esa re-ejecucion y registrado en `evaluation_trace`; no se mutan permisos globales ni se salta MCP. | `apps/peopleops-api/src/peopleops_api/analysis_workflow.py`, `apps/peopleops-api/tests/test_analysis_workflow.py`, `docs/04-PROC.md`, `docs/SEMANTIC-ANALYSIS-CAPABILITY-PLAN.md`. | `poetry run pytest tests/test_analysis_workflow.py::test_evaluation_trace_persists_authorization_decision tests/test_analysis_workflow.py::test_payroll_without_scope_is_denied_even_when_review_is_enabled tests/test_analysis_workflow.py::test_payroll_entity_without_capability_is_denied_before_planning tests/test_analysis_workflow.py::test_restricted_payroll_plan_is_denied_when_semantic_capability_is_omitted tests/test_analysis_workflow.py::test_human_review_approval_reruns_payroll_with_scoped_authorization tests/test_analysis_workflow.py::test_workflow_denies_payroll_without_scope_when_human_review_is_disabled tests/test_human_review.py` => 11 passed; `ruff check src/peopleops_api/analysis_workflow.py tests/test_analysis_workflow.py tests/test_human_review.py` => passed. Prueba real API desde fuente: consulta `Que trabajadores ganan mas de 1000?` sin `hr:payroll` => `pending_human_review`, `AUTHORIZATION_ERROR`, 0 validaciones/ejecuciones; inbox muestra item pendiente; decision `approve` => misma request `completed`, `human_review_status=approve`, `authorization_resume.scope_added=hr:payroll`, detalles con 1 validacion MCP y 1 ejecucion MCP. | `IN_PROGRESS` |

## Definicion De Hecho Global

Este plan se considera completo cuando:

- [x] La aplicacion puede resolver correctamente el caso "empleados con contrato
      vigente" excluyendo contratos terminados antes de la fecha de referencia.
- [x] La solucion no depende de hardcoding de esa frase ni de IDs del dataset.
- [x] Existen filtros agrupados o una alternativa multi-query documentada y
      verificada.
- [x] La cobertura semantica se verifica antes de sintesis.
- [x] La aplicacion puede abstenerse con estado funcional, no con error interno.
- [ ] Hay evaluaciones genericas para los patrones principales.
- [x] La UI/API permiten auditar interpretacion, query conceptual, evidencia y
      advertencias.
- [ ] Este documento refleja el estado final y las evidencias de verificacion.
