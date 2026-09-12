# Plan de diagnostico instrumentado del flujo LLM

**Estado:** PLANIFICADO  
**Fecha:** 2026-09-12  
**Objetivo:** medir el comportamiento real del workflow de analisis, explicar su latencia y determinar si existen llamadas al LLM, reintentos o etapas redundantes.

## 1. Objetivo y resultado esperado

Este diagnostico debe producir evidencia reproducible de como se ejecuta cada
consulta desde la API hasta la respuesta final. El resultado no sera una
opinion basada solamente en el numero total de llamadas: debe mostrar que
llamada ocurrio, por que ocurrio, cuanto demoro y que transicion provoco.

El diagnostico debe responder:

- Cuantas llamadas al LLM realiza cada escenario.
- Cuanto tiempo consume cada etapa y cada llamada.
- Cuantas llamadas son obligatorias, defensivas, repetidas o provocadas por
  una respuesta incompleta del modelo.
- Cuantas llamadas a MCP ocurren y cuanto demoran.
- En que punto termina una consulta no autorizada de `hr:payroll`.
- Si la aprobacion de Human Review vuelve a ejecutar etapas innecesarias o
  ejecuta correctamente el flujo completo.
- Cual es el peor caso de llamadas y si sus limites son efectivos.

## 2. Restricciones del diagnostico

El agente que ejecute este plan debe cumplir estas reglas:

1. No cambiar prompts, contratos semanticos, reglas de autorizacion ni
   decisiones del workflow para mejorar artificialmente el resultado.
2. No agregar rutas por keywords, preguntas especificas o respuestas
   esperadas.
3. No consultar directamente la base de datos del HRIS. El camino debe ser
   API -> HRDataGateway -> MCP -> HRIS.
4. No registrar prompts completos, chain-of-thought, credenciales, tokens ni
   datos personales innecesarios.
5. No usar datos reales. Las consultas deben operar sobre el dataset sintetico.
6. No alterar datos de produccion/demo salvo las decisiones necesarias para
   probar Human Review. Preferir un entorno o datos de prueba aislados.
7. No declarar que una llamada es innecesaria sin conservar evidencia de su
   etapa, entrada estructurada, salida estructurada y dependencia.
8. No optimizar durante la primera ejecucion. Primero se obtiene una linea
   base sin cambios funcionales.

## 3. Evidencia disponible que debe usarse primero

Antes de modificar codigo, revisar y correlacionar:

- `AnalysisInteraction.stage_history`.
- `AnalysisInteraction.evaluation_trace`, cuando este habilitado para el caso.
- `AnalysisInteraction.status`, `current_stage`, `warnings` y `error_type`.
- Evidencia de Human Review y sus decisiones.
- Logs estructurados de la API.
- Logs y trazas del Reference MCP Server.
- Latencia total observada por el cliente HTTP.

La evidencia persistida es la fuente funcional de auditoria. LangSmith o
cualquier otra traza externa puede complementar el diagnostico, pero no puede
reemplazar `AnalysisInteraction`.

## 4. Estrategia de ejecucion

### 4.1 Preparacion

El agente debe:

1. Revisar el estado de Git y no sobrescribir cambios existentes.
2. Leer la documentacion base indicada en `AGENTS.md`, el plan de analisis
   semantico y la especificacion de Human Review.
3. Confirmar que las bases de datos estan disponibles.
4. Detener y reiniciar los servicios de aplicacion desde el codigo fuente,
   usando Poetry y el `.env` de la raiz. Docker debe proveer solamente las
   bases de datos.
5. Confirmar las versiones de API, MCP y codigo fuente usadas en la corrida.
6. Confirmar que el diagnostico no usa una aplicacion levantada desde una
   imagen Docker antigua.

Comandos base esperados, ajustando los puertos al entorno:

```bash
set -a; source .env; set +a
make ps
make health
```

El agente debe documentar los comandos reales ejecutados y sus resultados.

### 4.2 Primera fase: diagnostico sin instrumentacion nueva

Ejecutar los escenarios usando los campos de auditoria ya existentes. Para
cada escenario guardar:

- `request_id` y `conversation_id`;
- pregunta enviada;
- contexto de autorizacion usado;
- hora de inicio y fin;
- status final y `current_stage`;
- `stage_history` completo;
- `evaluation_trace` disponible;
- cantidad de llamadas LLM observables;
- cantidad de llamadas MCP observables;
- resultado de Human Review, si aplica.

Si los datos actuales no permiten contar o temporizar una llamada con
precision, no se debe inferir el valor. Se debe pasar a la segunda fase.

### 4.3 Segunda fase: instrumentacion observacional minima

Si la primera fase no basta, agregar instrumentacion temporal o claramente
aislada que observe, sin cambiar la logica funcional:

- contador por llamada al modelo;
- `purpose` o nombre de etapa;
- modelo configurado;
- inicio, fin y duracion en milisegundos;
- resultado: exito, error o reintento;
- tipo de salida estructurada, sin guardar contenido privado completo;
- numero de ronda del planner/programmer/reviewer;
- correlacion con `request_id`.

Para MCP observar:

- operacion (`discover`, `validate`, `execute`);
- inicio, fin y duracion;
- resultado o error normalizado;
- reintento y numero de intento;
- cantidad de filas y tamano de respuesta, sin copiar datos sensibles.

La instrumentacion debe usar logs estructurados o un campo de diagnostico
controlado. No debe cambiar prompts, decisiones, limites, orden del workflow
ni contratos publicos. Debe ser removible despues del diagnostico o quedar
documentada como observabilidad neutral.

## 5. Matriz de escenarios

Cada escenario debe ejecutarse al menos dos veces si el resultado depende del
LLM. Conservar cada corrida como un artefacto separado; no promediar valores
antes de guardar los datos individuales.

### A. Consulta simple de datos

Pregunta de referencia:

```text
Conectate al MCP PeopleOps y listame los empleados de la empresa.
```

Objetivo: medir el camino normal desde interpretacion hasta query conceptual,
ejecucion y sintesis.

### B. Payroll sin autorizacion

Pregunta de referencia:

```text
Lista los empleados y su informacion de payroll.
```

Contexto: sin `hr:payroll`.

Objetivo: comprobar que el caso termina en `AUTHORIZATION_DENIED` o en el
contrato equivalente, solicita Human Review y no ejecuta planificacion,
sintesis ni llamadas MCP de datos restringidos despues de la denegacion.

### C. Payroll con aprobacion

Reutilizar el caso B y ejecutar la aprobacion por la API de Human Review.

Objetivo: medir por separado:

- ejecucion inicial hasta la denegacion;
- persistencia de la solicitud;
- decision humana;
- ejecucion posterior a la aprobacion;
- llamadas adicionales producidas por la reanudacion;
- resultado visible en el historial.

La aprobacion no debe conceder permisos de forma silenciosa fuera del flujo
documentado. La evidencia debe mostrar que la reejecucion usa el contexto
autorizado esperado y vuelve a pasar por MCP.

### D. Consulta de politica

Usar una consulta que requiera un documento de politica, sin datos HRIS.

Objetivo: medir el camino Policy RAG y confirmar que no ejecuta discovery ni
queries MCP innecesarias.

### E. Consulta ambigua

Usar una consulta sintetica que requiera aclaracion real, sin introducir una
regla especial en el codigo.

Objetivo: observar si el sistema hace llamadas de reparacion o si produce un
estado de informacion insuficiente de forma acotada.

### F. Query que requiere reparacion

Usar un caso de evaluacion existente que provoque feedback de validacion MCP
o revision semantica. No crear una pregunta nueva solo para forzar un numero.

Objetivo: medir reintentos, replanteamientos, rondas del Query Programmer y
Senior Reviewer, y verificar que todos terminan por un limite finito.

### G. Fallas externas controladas

Cuando existan pruebas soportadas por el repositorio, ejecutar MCP timeout,
OpenAI timeout o validacion invalida de forma controlada.

Objetivo: distinguir reintento transitorio de loop, y medir el costo de cada
politica de reintento.

## 6. Modelo de registro por llamada

Cada evento de llamada debe poder representarse con este esquema logico:

```json
{
  "request_id": "...",
  "scenario": "payroll_denied",
  "component": "peopleops_api",
  "stage": "functional_analyst",
  "operation": "structured_model_parse",
  "attempt": 1,
  "round": 0,
  "started_at": "...",
  "duration_ms": 0,
  "outcome": "success",
  "output_type": "SemanticRequest",
  "model": "...",
  "input_tokens": null,
  "output_tokens": null,
  "retry_reason": null,
  "parent_event_id": null
}
```

Los campos de tokens son opcionales si el proveedor no los devuelve. El
artefacto no debe contener el prompt completo ni datos HRIS. Para explicar una
decision se deben guardar referencias a la salida estructurada persistida,
por ejemplo su tipo, hash o resumen seguro.

## 7. Clasificacion de llamadas

Cada llamada debe clasificarse despues de observar el flujo:

| Categoria | Definicion |
| --- | --- |
| Necesaria | La llamada corresponde a una etapa requerida por el contrato del caso. |
| Defensiva | Protege una frontera de seguridad, validacion o suficiencia. |
| Refinamiento | Corrige o aterriza una salida estructurada usando evidencia del catalogo o MCP. |
| Reparacion | Responde a feedback tecnico o semantico concreto. |
| Reintento transitorio | Repite una operacion por timeout o falla recuperable. |
| Replanificacion | Genera un plan nuevo despues de una revision que lo justifica. |
| Potencialmente redundante | Repite una etapa sin nueva evidencia ni cambio de estado. |
| Inesperada | No tiene una dependencia explicable en el contrato del workflow. |

`Potencialmente redundante` no significa automaticamente defectuosa. Requiere
revisar el motivo, la entrada y la salida de la llamada antes de recomendar un
cambio.

## 8. Metricas y criterios de diagnostico

Para cada escenario calcular:

- llamadas LLM totales, minimas, maximas y por etapa;
- llamadas MCP por operacion;
- tiempo total de wall clock;
- tiempo acumulado de LLM, MCP y procesamiento local;
- porcentaje de tiempo consumido por cada etapa;
- numero de reintentos y replanteamientos;
- profundidad maxima del ciclo de reparacion;
- tokens de entrada y salida, cuando existan;
- tiempo desde `AUTHORIZATION_ERROR` hasta la creacion de Human Review;
- tiempo desde aprobacion hasta la respuesta final;
- llamadas realizadas despues de que una decision ya era terminal;
- diferencias entre primera ejecucion y continuacion aprobada.

Se considera un hallazgo de alto riesgo cuando:

- una consulta denegada ejecuta datos restringidos despues de la denegacion;
- el numero de llamadas no tiene un limite demostrable;
- una reparacion vuelve a entrar en el mismo ciclo sin nueva evidencia;
- Human Review no queda persistido o la aprobacion no es correlacionable;
- una llamada usa una ruta fuera de MCP;
- el sistema sintetiza una respuesta despues de una falla sin evidencia
  suficiente.

Se considera un candidato de optimizacion cuando:

- dos llamadas consecutivas tienen el mismo objetivo, entradas equivalentes y
  ninguna evidencia nueva;
- una etapa costosa se ejecuta despues de que el estado ya es terminal;
- una consulta simple activa reparaciones sin error verificable;
- la latencia se concentra en una llamada cuyo resultado no cambia el estado.

## 9. Artefactos y ubicacion

Los resultados deben conservarse en la estructura de evaluacion existente, no
mezclados con tablas funcionales de `AnalysisInteraction`.

Ruta recomendada:

```text
evaluation/runs/phase44/llm-flow-diagnostic-<timestamp>/
```

Cada escenario debe tener su propio JSON, por ejemplo:

```text
simple_data_query.json
payroll_denied.json
payroll_approved.json
policy_only.json
ambiguous_query.json
repair_bounded.json
summary.json
raw_responses.jsonl
```

`raw_responses.jsonl` debe ser solamente un indice de artefactos, con una
referencia estable y una descripcion del escenario. No debe duplicar las
respuestas completas.

Cada artefacto de escenario debe incluir:

- identificacion de version y commit;
- fecha, entorno y configuracion no secreta;
- pregunta y contexto seguro;
- request/conversation ids;
- eventos de llamadas;
- resumen de etapas;
- resultados y errores normalizados;
- conteos y latencias;
- clasificacion de llamadas;
- conclusion del escenario;
- limitaciones de la medicion.

## 10. Formato del informe final

El agente debe entregar un informe breve y verificable con estas secciones:

1. **Alcance y version evaluada.**
2. **Metodologia y escenarios ejecutados.**
3. **Tabla de llamadas y latencias por escenario.**
4. **Diagrama textual del flujo real observado.**
5. **Analisis especifico de `hr:payroll`.**
6. **Reintentos, reparaciones y limites observados.**
7. **Hallazgos**, ordenados por severidad.
8. **Llamadas potencialmente redundantes**, con evidencia.
9. **Riesgos no resueltos y gaps de observabilidad.**
10. **Recomendaciones**, separando cambios de bajo riesgo de cambios que
    requieren una decision arquitectonica.

El informe no debe proponer eliminar una validacion de seguridad solamente para
reducir latencia. Toda optimizacion debe conservar autorizacion, MCP,
persistencia, evidencia y Human Review.

## 11. Definition of Done

- [ ] Se ejecutaron los escenarios A, B y C como minimo.
- [ ] Se midio la consulta simple y el caso `hr:payroll` denegado.
- [ ] Se midio la continuacion posterior a aprobacion.
- [ ] Cada llamada LLM observable tiene etapa, duracion, resultado y motivo.
- [ ] Se distinguieron llamadas LLM de operaciones locales y MCP.
- [ ] Se verifico que los limites de reintento/replanificacion se cumplen.
- [ ] Los resultados quedaron en artefactos individuales bajo `evaluation/runs`.
- [ ] No se modificaron prompts ni reglas funcionales durante la linea base.
- [ ] Se ejecutaron las pruebas relevantes y se registraron sus resultados.
- [ ] El informe final contiene evidencia suficiente para decidir si optimizar.

## 12. Regla para la siguiente etapa

No implementar optimizaciones con base solamente en este plan. Primero debe
completarse una corrida de linea base y revisarse el informe. Cualquier cambio
posterior debe formularse como una hipotesis concreta, por ejemplo:

> "La refinacion semantica ocurre dos veces sin cambiar el contrato en el caso
> simple; reducirla a una sola pasada mantiene la misma salida estructurada y
> elimina X milisegundos."

La hipotesis debe probarse con una segunda corrida usando los mismos escenarios,
comparar resultados funcionales y verificar que no se debilitaron autorizacion,
Human Review, MCP ni evidencia.
