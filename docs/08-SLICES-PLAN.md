# PeopleOps AI — Implementation Slices Plan

**Este documento solo define índice, objetivo y dependencias.**  
No desarrolla tareas, archivos, prompts ni criterios detallados.

Cada slice deberá especificarse justo antes de su implementación usando SPEC/REQ/ADR/PROC/DATA/UI/CTX como baseline.

## Slice 00 — Repository Foundation & Guardrails
Objetivo: monorepo, configuración, calidad, contratos básicos y guardrails anti-hardcoding.  
Dependencias: ninguna.

## Slice 01 — PeopleOps Application Persistence
Objetivo: persistencia PeopleOps con Conversation y AnalysisInteraction baseline.  
Dependencias: Slice 00.

## Slice 02 — Synthetic Reference HRIS
Objetivo: modelo HR sintético y escenarios/ground truth iniciales.  
Dependencias: Slice 00.

## Slice 03 — Reference MCP Server: Discovery
Objetivo: MCP Server con capabilities, entities, fields, relationships y semantic metadata.  
Dependencias: Slice 02.

## Slice 04 — MCP Client & HRDataGateway
Objetivo: PeopleOps conectado exclusivamente al Reference MCP Server mediante contratos tipados.  
Dependencias: Slices 01 y 03.

## Slice 05 — Conceptual Query Contract & MCP Execution
Objetivo: conceptual query, validación, traducción PostgreSQL, guardrails y read-only execution.  
Dependencias: Slices 03 y 04.

## Slice 06 — Structured HR Analysis Baseline
Objetivo: preguntas HR dinámicas con LangGraph + MCP, sin Policy RAG todavía.  
Dependencias: Slice 05.

## Slice 07 — Policy Knowledge Ingestion
Objetivo: upload/versionado e ingestión basada en patrones probados de Enterprise RAG.  
Dependencias: Slices 00 y 01.

## Slice 08 — Policy RAG Retrieval & Evaluation Baseline
Objetivo: retrieval, filters, evidence verification, abstention y evaluación.  
Dependencias: Slice 07.

## Slice 09 — Combined Data + Policy Workflow
Objetivo: combinar structured HR evidence y policy evidence en LangGraph.  
Dependencias: Slices 06 y 08.

## Slice 10 — Human-in-the-loop
Objetivo: pause/resume, decisiones humanas y audit trail durable.  
Dependencias: Slice 09.

## Slice 11 — Payroll Deep Analysis & Reconciliation
Objetivo: payroll individual y Attendance/Overtime ↔ Payroll.  
Dependencias: Slices 06 y 09.

## Slice 12 — Multilingual & Anti-Hardcoding Regression
Objetivo: demostrar cobertura semántica sin keyword routing ni funciones por wording.  
Dependencias: Slices 06, 09 y 11.

## Slice 13 — MCP Contract & Schema Independence
Objetivo: contract tests y segundo schema físico sin cambios en PeopleOps.  
Dependencias: Slices 05, 06 y 11.

## Slice 14 — PeopleOps Web: Analysis & Evidence
Objetivo: interfaz de consulta, respuesta y evidencia.  
Dependencias: Slices 06 y 09.

## Slice 15 — PeopleOps Web: Policies & Human Review
Objetivo: administración documental y bandeja Human Review.  
Dependencias: Slices 07, 08, 10 y 14.

## Slice 16 — Integrated Evaluation & Observability
Objetivo: evaluación structured-data, RAG, MCP, workflow y respuesta.  
Dependencias: Slices 08, 10, 11, 12 y 13.

## Slice 17 — Security & Failure Hardening
Objetivo: permisos, payroll sensitivity, timeouts, retries, safe logging, prompt injection y fallos MCP/model.  
Dependencias: Slice 16.

## Slice 18 — Portfolio / Pilot Release
Objetivo: Docker reproducible, README, demo, screenshots, resultados y preparación de piloto.  
Dependencias: todos los slices obligatorios anteriores.

## Regla de desarrollo
Antes de cada slice se redactará su especificación detallada con:
- objetivo;
- REQ afectados;
- alcance/fuera de alcance;
- cambios esperados;
- tests;
- evaluation impact;
- Definition of Done.

Ese detalle no se incluye aquí para evitar diseño prematuro.
