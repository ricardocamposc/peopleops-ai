# Phase 4.2 — Query Programmer Skill Prompts

## 1. Objetivo e hipótesis

Se evaluó si separar las instrucciones del único agente lógico `sqlalchemy_query_developer` en tres skills mejora el comportamiento sin cambiar el workflow, el dataset, los modelos, el validador ni los presupuestos:

- `GENERATE`
- `TECHNICAL_REPAIR`
- `SEMANTIC_REPAIR`

La hipótesis no se confirmó en esta corrida: la variante skill-specific generó ligeramente más queries, pero obtuvo menor validez técnica final y menor aprobación semántica en `AGENT_TEAM`.

## 2. Configuración y reproducibilidad

- Rama: `phase42-programmer-skills`
- HEAD de ejecución: `010679e255ee1b59e520e025d99c8e11a40de4a0`
- Dataset: `evaluation/spikes/direct_sqlalchemy_phase42_cases.jsonl`
- Dataset actual: 36 casos, `P42-001` a `P42-036`
- Modelos: `gpt-4o-mini` para Functional Analyst, Query Programmer y Senior Reviewer
- Temperatura: `0`
- Base de datos/MCP: no se ejecutaron queries; solo validación determinista y compilación PostgreSQL
- Variante: `query_programmer_prompt_strategy = skill_specific`
- Artefacto skill-specific: `evaluation/runs/phase42-skill-prompts-baseline-20260906-184337/`
- Artefacto broad-prompt comparable: `evaluation/runs/phase42-broad-prompt-baseline-20260906-185924/`

Los artefactos históricos disponibles con nombre Phase 4.2 usaban otro dataset (`P41-01`…`P41-24`), por lo que no se usaron para la comparación cuantitativa. Se ejecutó un baseline broad-prompt adicional sobre los mismos 36 casos para mantener la comparación 1:1.

## 3. Resultados agregados

### QUERY_DEVELOPER_ONLY

| Métrica | Broad prompt | Skill-specific |
|---|---:|---:|
| Casos | 36 | 36 |
| Query generation | 30 (83.33%) | 31 (86.11%) |
| First-pass technical validity | 22 (73.33%) | 18 (58.06%) |
| Final technical validity | 22 (73.33%) | 18 (58.06%) |
| Internal validation attempts | 47 | 63 |
| Internal self-repair attempts | 19 | 32 |
| Internal self-repair success | 1 | 4 |
| NEEDS_CLARIFICATION | 2 | 2 |
| CANNOT_IMPLEMENT | 4 | 3 |
| Latencia media por caso | 6,623.82 ms | 7,471.46 ms |
| Llamadas LLM derivadas | 89 | 102 |

### AGENT_TEAM

| Métrica | Broad prompt | Skill-specific |
|---|---:|---:|
| Casos | 36 | 36 |
| Query generation | 31 (86.11%) | 31 (86.11%) |
| First-pass technical validity | 23 (74.19%) | 17 (54.84%) |
| Final technical validity | 21 (67.74%) | 15 (48.39%) |
| External technical repairs | 10 | 16 |
| External technical repair success | 0 | 0 |
| Internal validation attempts | 123 | 169 |
| Internal self-repair attempts | 62 | 99 |
| Internal self-repair success | 2 | 3 |
| Senior first-pass approval | 13/23 (56.52%) | 10/17 (58.82%) |
| Senior revision requested | 10 | 7 |
| Semantic repair attempted | 10 | 7 |
| Semantic repair success | 0 | 0 |
| Final semantic approval | 13/23 (56.52%) | 10/17 (58.82%) |
| Technical validation failed | 10 | 16 |
| Max semantic revisions reached | 8 | 5 |
| NEEDS_CLARIFICATION | 2 | 2 |
| CANNOT_IMPLEMENT | 3 | 3 |
| Latencia media por caso | 15,763.29 ms | 17,332.09 ms |
| Llamadas LLM derivadas | 193 | 230 |

## 4. Skills y audit trail

En la variante skill-specific, las invocaciones del Query Programmer quedaron registradas dentro de `query_programmer_invocations` y cada una incluye `agent_id`, `skill`, `prompt_id`, `prompt_version`, `model`, `repair_type`, `repair_attempt`, `latency_ms`, `input_artifacts` y `output_status`.

Conteo total de invocaciones del Query Programmer en ambos modos:

| Skill | Invocaciones | Latencia media |
|---|---:|---:|
| `GENERATE` | 68 | 2,787.81 ms |
| `TECHNICAL_REPAIR` | 163 | 2,615.65 ms |
| `SEMANTIC_REPAIR` | 7 | 2,937.26 ms |

El manifest registra SHA-256 separados para los tres prompts. El smoke previo verificó el routing `GENERATE -> TECHNICAL_REPAIR` en self-repair, `TECHNICAL_REPAIR` en reparación externa y `SEMANTIC_REPAIR` después de una revisión Senior.

## 5. Casos con cambio de outcome

La comparación usa los mismos IDs y la misma configuración general; las diferencias también reflejan la variabilidad normal de llamadas LLM independientes. No se atribuye causalidad al prompt únicamente por observar un cambio.

### QUERY_DEVELOPER_ONLY

| Caso | Broad prompt | Skill-specific |
|---|---|---|
| P42-008 | CANNOT_IMPLEMENT | QUERY_DEVELOPER_ONLY_COMPLETE |

### AGENT_TEAM

| Caso | Broad prompt | Skill-specific |
|---|---|---|
| P42-003 | APPROVED | MAX_SEMANTIC_REVISIONS_REACHED |
| P42-004 | APPROVED | MAX_SEMANTIC_REVISIONS_REACHED |
| P42-006 | APPROVED | TECHNICAL_VALIDATION_FAILED |
| P42-007 | MAX_SEMANTIC_REVISIONS_REACHED | APPROVED |
| P42-010 | MAX_SEMANTIC_REVISIONS_REACHED | APPROVED |
| P42-012 | MAX_SEMANTIC_REVISIONS_REACHED | TECHNICAL_VALIDATION_FAILED |
| P42-014 | MAX_SEMANTIC_REVISIONS_REACHED | APPROVED |
| P42-016 | MAX_SEMANTIC_REVISIONS_REACHED | TECHNICAL_VALIDATION_FAILED |
| P42-017 | APPROVED | TECHNICAL_VALIDATION_FAILED |
| P42-018 | APPROVED | TECHNICAL_VALIDATION_FAILED |
| P42-021 | MAX_SEMANTIC_REVISIONS_REACHED | TECHNICAL_VALIDATION_FAILED |
| P42-023 | APPROVED | MAX_SEMANTIC_REVISIONS_REACHED |
| P42-024 | TECHNICAL_VALIDATION_FAILED | APPROVED |
| P42-032 | APPROVED | TECHNICAL_VALIDATION_FAILED |

## 6. Análisis de causas

- **Generación inicial:** skill-specific mejoró el número de queries generadas en developer-only de 30 a 31, pero redujo la validez técnica inicial de 22 a 18. En team, ambas variantes generaron 31 queries, pero skill-specific validó técnicamente 17 frente a 23.
- **Internal technical repair:** skill-specific ejecutó más intentos (32 frente a 19 en developer-only; 99 frente a 62 en team). El número absoluto de éxitos aumentó ligeramente, pero no compensó el mayor número de candidatos inválidos.
- **External technical repair:** ninguna variante tuvo éxito externo en esta corrida; skill-specific necesitó más reparaciones (16 frente a 10).
- **Semantic repair:** skill-specific pidió menos revisiones (7 frente a 10), pero ninguna reparación semántica terminó en éxito en ninguna variante.
- **Senior:** entre las queries que llegaron técnicamente válidas, la tasa de aprobación de primer pase fue parecida (58.82% skill-specific frente a 56.52% broad). La diferencia principal ocurrió antes, en generación/validación técnica.
- **Causalidad:** las llamadas fueron independientes y no existe un diseño repetido/controlado por caso que permita separar completamente efecto del prompt y variabilidad estocástica. Este resultado es evidencia de una corrida, no una prueba definitiva.

## 7. Limitaciones

- El baseline histórico de 24 casos no era comparable porque contenía IDs y dataset P41; por eso se ejecutó un broad-prompt baseline nuevo de 36 casos.
- La comparación es una sola repetición por estrategia.
- Los artefactos no ejecutan consultas contra la base de datos.
- La métrica de aprobación semántica refleja el Senior Reviewer y no una ejecución real de resultados.

## 8. Conclusión y recomendación

La separación de skills está correctamente integrada y es observable, pero en esta corrida no mejora la confiabilidad global: aumenta las llamadas y la latencia, reduce la validez técnica final en `AGENT_TEAM` de 67.74% a 48.39% y reduce la aprobación semántica final de 13 a 10 casos.

Recomendación: **ITERATE**.

No se recomienda aceptar `skill_specific` como reemplazo del broad prompt todavía. El siguiente experimento debería repetir varias veces el mismo conjunto de 36 casos y revisar las trazas de los fallos técnicos antes de ajustar prompts. No se hicieron ajustes de prompts después de observar estos resultados.

## 9. Quality gates

- Tests Phase 4.2/4.3 específicos: 34 passed.
- Suite backend: 173 passed.
- Suite reference MCP: 32 passed, 6 skipped.
- Ruff check: passed.
- Frontend lint: passed.
- `git diff --check`: passed.
- Formato estricto Ruff: detecta cinco archivos históricos que requerirían reformateo; no se modificaron.
- Smoke real: 5 casos `AGENT_TEAM`, completado con audit trail y hashes.
- Baselines broad y skill-specific: 36 casos × 2 modos, 72 ejecuciones cada uno.
