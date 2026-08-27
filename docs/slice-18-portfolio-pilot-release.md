# Slice 18 — Portfolio / Pilot Release

**Estado:** Especificación de slice  
**Objetivo:** Convertir el MVP técnico en una entrega reproducible, entendible y presentable para portfolio y piloto controlado con un cliente.  
**Dependencias:** Todos los slices obligatorios anteriores.

## 1. Requisitos trazados

- REQ-PHY-005..006
- REQ-PROD-001..005
- Definition of Compliance completa

## 2. Alcance

- Consolidar Docker/Compose de demo.
- README profesional con quickstart.
- Arquitectura y ADRs visibles.
- Documentar Synthetic Reference HRIS y naturaleza sintética de datos.
- Incluir corpus policy sintético.
- Publicar resultados de evaluación y limitaciones.
- Crear demo script con escenarios insignia.
- Preparar screenshots/video assets.
- Preparar guía de piloto real sin incluir adapter propietario.
- Documentar cómo sustituir Reference MCP Server por Customer MCP Server.

## 3. Fuera de alcance

- BIZAG production adapter.
- Deployment production-ready.
- Integration Console.
- Features fuera del PRD.

## 4. Diseño descriptivo esperado

- Un tercero debe poder ejecutar el proyecto siguiendo documentación.
- El demo debe atravesar MCP real, nunca bypass.
- Los resultados publicados deben corresponder a runs reproducibles.
- Las limitaciones deben quedar visibles.
- El mensaje comercial no debe prometer capacidades no implementadas.

## 5. Pruebas mínimas

- Fresh clone → setup → run.
- Smoke E2E de escenarios insignia.
- Evaluation baseline desde entorno limpio.
- Schema independence demo.
- Policy upload/retrieval.
- HITL demo.
- Security sanity checks.

## 6. Impacto en evaluación

- Este slice congela el baseline de portfolio/pilot.
- Los números publicados deben apuntar a artifacts identificables.

## 7. Definition of Done

- Repo reproducible.
- README y arquitectura defendibles.
- Demo completa.
- Evaluation results publicados.
- Limitaciones y roadmap claros.
- Material para piloto preparado.
- MVP no depende de componentes pendientes.

## 8. Guardrails y riesgos

- No agregar features durante hardening salvo blocker.
- No afirmar production-ready.
- No usar datos reales de cliente en repo/demo.
- No presentar MCP futuro: Reference MCP Server debe estar funcionando.
