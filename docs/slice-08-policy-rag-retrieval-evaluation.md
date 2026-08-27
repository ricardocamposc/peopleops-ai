# Slice 08 — Policy RAG Retrieval & Evaluation Baseline

**Estado:** Especificación de slice  
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

- Medir al menos document hit/recall, filter precision cuando aplique, citation validity, answerability y abstention.
- Groundedness/relevance por judge solo como capa adicional.

## 7. Definition of Done

- Policy RAG funcional y medido.
- Baseline guardado.
- Casos negativos incluidos.
- Version correctness probado.
- Evidence visible y verificable.

## 8. Guardrails y riesgos

- No optimizar por una sola métrica.
- No usar LLM judge como único criterio.
- No permitir respuesta con conocimiento general cuando el corpus no basta.
- No mezclar policy facts esperados con chunks de ingestión.
