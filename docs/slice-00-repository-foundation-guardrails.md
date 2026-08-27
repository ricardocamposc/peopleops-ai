# Slice 00 — Repository Foundation & Guardrails

**Estado:** Especificación de slice  
**Objetivo:** Crear la base reproducible del monorepo y establecer desde el primer commit las restricciones arquitectónicas que ningún slice posterior puede vulnerar.  
**Dependencias:** Ninguna.

## 1. Requisitos trazados

- REQ-PHY-001..006
- REQ-SEC-001..003
- REQ-SEM-001..005

## 2. Alcance

- Crear el monorepo con los tres deployables previstos: `peopleops-api`, `peopleops-web` y `reference-mcp-server`.
- Definir estructura para paquetes compartidos, documentación, evaluation, synthetic-hris y policies sintéticas.
- Configurar entornos, `.env.example`, Docker/Compose base, linting, testing y comandos de desarrollo reproducibles.
- Crear `AGENTS.md`/reglas para Codex con anti-hardcoding, frontera MCP, ownership de datos y prohibición de bypass.
- Establecer contratos base compartidos sin cerrar todavía el modelo conceptual completo.
- Preparar health checks mínimos por servicio.

## 3. Fuera de alcance

- Modelo HRIS completo.
- MCP discovery funcional.
- LangGraph productivo.
- RAG.
- Frontend funcional.
- Human Review.

## 4. Diseño descriptivo esperado

- La topología física debe permitir ejecutar los tres servicios independientemente aunque inicialmente algunos tengan implementación mínima.
- `peopleops-api` no debe disponer de credenciales ni conexión al Synthetic HRIS.
- `reference-mcp-server` no debe depender de PeopleOps DB.
- Las dependencias compartidas deben limitarse a contratos/utilidades neutrales; no compartir ORM del HRIS con PeopleOps.
- Las reglas anti-hardcoding deben quedar escritas en el repositorio, no solo implícitas en documentación.

## 5. Pruebas mínimas

- Smoke test de arranque de servicios.
- Test de configuración faltante/incorrecta.
- Verificación automática de `.env.example` sin secretos.
- Test o comprobación de que PeopleOps API no puede abrir conexión al HRIS DB.
- Lint/test command reproducible.

## 6. Impacto en evaluación

- No crea todavía métricas funcionales.
- Establece infraestructura necesaria para que todas las evaluaciones posteriores sean reproducibles.
- Debe permitir guardar artifacts de evaluación por run.

## 7. Definition of Done

- Monorepo creado y documentado.
- Tres deployables identificables.
- Docker/Compose base operativo.
- Test/lint ejecutable con un comando documentado.
- Guardrails Codex/AGENTS presentes.
- No existe acceso directo PeopleOps→HRIS.

## 8. Guardrails y riesgos

- No introducir Redis, colas, observabilidad SaaS u otros componentes sin necesidad demostrada.
- No crear un cuarto servicio administrativo.
- No utilizar shortcuts de desarrollo que luego sean ruta productiva.
- No introducir keywords de intención en ejemplos o scaffolding.
