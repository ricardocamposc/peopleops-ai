# Slice 07 — Policy Knowledge Ingestion

**Estado:** Especificación de slice  
**Objetivo:** Implementar la administración e ingestión documental de políticas reutilizando los patrones sólidos ya validados en Enterprise RAG.  
**Dependencias:** Slices 00 y 01.

## 1. Requisitos trazados

- REQ-RAG-ING-001..007
- REQ-SEC-007..008
- REQ-PHY-004

## 2. Alcance

- Implementar PolicyDocument, PolicyVersion e IngestionJob.
- Permitir upload vía PeopleOps API.
- Conservar archivo original.
- Procesar PDF; DOCX si el esfuerzo es razonable.
- Parsing, chunking, metadata y embeddings con LlamaIndex.
- Persistir vectores con PostgreSQL/pgvector.
- Versionar effective_from/effective_to/status.
- Crear corpus sintético inicial HR con versiones/ambigüedades deliberadas.

## 3. Fuera de alcance

- Retrieval productivo.
- Workflow combinado.
- Frontend completo de policies (salvo API necesaria).
- Edición manual de chunks como fuente de verdad.

## 4. Diseño descriptivo esperado

- Seguir la separación corpus vs evaluation dataset de Enterprise RAG.
- Los chunks son derivados del documento, no reemplazo de la fuente.
- Una nueva versión no elimina la anterior.
- Documentos se tratan como contenido no confiable.

## 5. Pruebas mínimas

- Upload PDF válido.
- Archivo inválido/tamaño/tipo.
- Ingestión completa y chunk count.
- Nueva versión del mismo documento.
- Fallo de parsing.
- Reindexación.
- Metadata de vigencia persistida.

## 6. Impacto en evaluación

- Prepara dataset para evaluación RAG posterior.
- Debe poder inspeccionarse qué versión/chunks se indexaron.

## 7. Definition of Done

- Corpus inicial versionado.
- Pipeline reproducible.
- Originales conservados.
- pgvector poblado.
- IngestionJob auditable.
- Tests de ingestión aprobados.

## 8. Guardrails y riesgos

- No copiar Enterprise RAG entero.
- No añadir reranking/hybrid search sin evaluación.
- No permitir instrucciones del documento controlar el pipeline.
- No sobrescribir silenciosamente versiones previas.
