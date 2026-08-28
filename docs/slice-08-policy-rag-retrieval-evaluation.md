# Slice 08 — Policy RAG Retrieval & Evaluation Baseline

**Estado:** Implementado en la rama de auditoría; pendiente baseline end-to-end con corpus real
**Objetivo:** Construir Policy RAG con retrieval trazable, versionado, evidencia verificada, abstention y baseline reproducible.  
**Dependencias:** Slice 07.

## 1. Requisitos trazados

- REQ-RAG-RET-001..008
- REQ-EVAL-001
- REQ-EVAL-005..007
- REQ-EVAL-012

## 2. Alcance

- Implementar PolicyKnowledgeProvider con LlamaIndex.
- Metadata filtering.
- Selección de versión vigente por fecha.
- Evidence verification antes de citar.
- Abstention cuando no existe soporte.
- Distinción POLICY_NOT_FOUND vs POLICY_CONFLICT.
- Dataset RAG versionado con expected sources/facts/version.
- Runner y artifacts de evaluación.
- Métricas deterministas base; LLM judge opcional/separado.

## 3. Fuera de alcance

- Workflow con datos estructurados.
- Human Review.
- Optimización avanzada de retrieval sin evidencia de necesidad.

## 4. Diseño descriptivo esperado

- Reutilizar filosofía de Enterprise RAG: medir antes de optimizar.
- El evaluation runner no debe ocultar fallos de ingestión.
- Una cita recuperada no se acepta automáticamente como evidencia válida.
- Fecha de vigencia es parte del correctness.

## 5. Pruebas mínimas

- Pregunta con policy actual.
- Pregunta histórica.
- Metadata filter.
- Pregunta sin respuesta.
- Policy conflict.
- Cita inválida/fragmento incorrecto.
- Evaluación reproducible con resultado versionado.

## 6. Impacto en evaluación

- Medir al menos document hit/recall, document precision, promoted-document precision,
  retrieval noise, filter precision cuando aplique, citation validity, answerability y abstention.
- Groundedness/relevance por judge solo como capa adicional.

## 7. Definition of Done

- Policy RAG funcional y medido.
- Baseline guardado.
- Casos negativos incluidos.
- Version correctness probado.
- Evidence visible y verificable.
- Dos corridas consecutivas sin fallos, con corpus sintético de cuatro páginas
  por documento y métricas de precisión de recuperación dentro del artefacto.

## 8. Guardrails y riesgos

- No optimizar por una sola métrica.
- No usar LLM judge como único criterio.
- No permitir respuesta con conocimiento general cuando el corpus no basta.
- No mezclar policy facts esperados con chunks de ingestión.

## 9. Implementación y ejecución

El diseño conserva las tablas `PolicyDocument`, `PolicyVersion` y
`PolicyChunk` de PeopleOps, y utiliza LlamaIndex para parsing, chunking y
embeddings. PostgreSQL/pgvector continúa siendo el adapter de persistencia y
distancia vectorial porque respeta el modelo de políticas y su provenance.

La verificación semántica está separada de la validación estructural. Solo se
envían a un modelo externo evidencias marcadas explícitamente como
`synthetic=true`; contenido no marcado no cruza esa frontera.

El dataset versionado está en
`evaluation/cases/policy_rag_v1.jsonl`. Sus observaciones se generan mediante
`ops/policy_rag_baseline.py`, que llama a `/api/v1/analysis`, valida el corpus
previamente y guarda un checkpoint después de cada caso:

```bash
make baseline-policy POLICY_BASELINE_OUTPUT_DIR=evaluation/runs/baseline-local
```

El resultado contiene `manifest.json`, `predictions.jsonl`, `metrics.json` y
`report.md`. El juez LLM es posterior, separado y explícitamente protegido:

```bash
make baseline-policy-judge \
  POLICY_PREDICTIONS=evaluation/runs/baseline-local/predictions.jsonl \
  POLICY_BASELINE_OUTPUT_DIR=evaluation/runs/baseline-local
```

El judge exige que todas las predicciones estén marcadas como corpus sintético
y nunca sustituye las métricas deterministas.
