# Handoff a Codex — Slice 00

## 1. Alcance confirmado del slice

### Sí entra

- Monorepo reproducible con tres deployables: `peopleops-api`, `peopleops-web` y `reference-mcp-server`.
- Estructura base de `packages/`, `synthetic-hris/`, `policies/`, `evaluation/`, `ops/` y documentación.
- Stack confirmado: Python 3.11, Poetry, FastAPI, Pydantic v2, pydantic-settings, Pytest, Ruff, Alembic preparado, Next.js, React, TypeScript, App Router, npm, Docker Compose y PostgreSQL.
- Dos servicios PostgreSQL separados: `peopleops-db` y `synthetic-hris-db`.
- `.env.example` seguro, `.gitignore`, configuración separada por ownership y CORS explícito para `http://localhost:3000`.
- Scaffold mínimo, health/liveness, logging técnico seguro, baseline de lint/tests y `Makefile` raíz.
- Guardrails comprobables contra acceso directo PeopleOps → HRIS, credenciales cruzadas, semantic hardcoding, secretos y servicios no autorizados.

### No entra

- Tablas, modelos o migraciones HR/PeopleOps funcionales.
- `Conversation`, `AnalysisInteraction`, Human Review, LangGraph productivo, OpenAI, Policy RAG/LlamaIndex, pgvector funcional, MCP discovery/tools/query execution o schema-independence.
- Frontend funcional, chat, dashboard, navegación o design system.
- Redis, LocalStack, Phoenix, colas, scheduler, WebSocket/SSE, adapters BIZAG/SAP/Workday o un cuarto servicio.

Adelantar cualquiera de esos puntos rompe el trabajo por slices y requiere una decisión documental explícita.

## 2. Contraste con el repositorio real

### Estado observado

- `AGENTS.md` existe y confirma la arquitectura, stack, puertos, ownership y orden de slices.
- `prompts/design-slice-00.md` existe y contiene el diseño completo del slice.
- Los documentos fuente existen en `docs/`, incluyendo BRD, PDD, PRD, mapa documental, SPEC, REQ, ADR, PROC, DATA, UI, CTX, plan de slices y especificación de Slice 00.
- No se detectó un repositorio Git inicializado desde `/Users/ricardocamposc/Projects/peopleops-ai` (`git status` devuelve `fatal: not a git repository`). Esto debe resolverse o documentarse antes de ejecutar operaciones Git del runbook.
- No existen actualmente `README.md`, `.gitignore`, `Makefile`, `docker-compose.yml`, `.env.example`, `apps/`, `packages/`, código de aplicaciones, tests ni configuraciones de frontend/backend visibles en el árbol inspeccionado.
- No existen implementaciones previas que reutilizar ni slices previos que preservar.

### Faltantes

Falta toda la fundación física y operativa: scaffolds, Compose, configuración, entornos de ejemplo, health endpoints, CORS, tests de guardrails, comandos canónicos, documentación operativa y áreas de artifacts.

### Puntos de entrada probables

Crear desde la raíz: `docker-compose.yml`, `Makefile`, `.env.example`, `.gitignore`, `README.md` y las tres aplicaciones bajo `apps/`. La implementación de cada app debe permanecer aislada; `packages/contracts` y `packages/shared` solo pueden contener piezas neutrales justificadas.

### Plantilla frontend

`AGENTS.md` confirma que no hay template UI propietario para Slice 00. No consultar ni copiar una plantilla. El frontend debe ser únicamente un scaffold mínimo de Next.js + TypeScript + App Router + npm. No registrar fake APIs, MSW, mocks, demo plugins ni datos de ejemplo.

### Base de datos

Slice 00 no crea persistencia funcional ni migraciones de dominio. La infraestructura debe ser PostgreSQL con los puertos host `5436` y `5437`, puertos internos `5432`, bases `peopleops` y `synthetic_hris`, y usuarios separados `peopleops_app` y `synthetic_hris_app`. No usar SQLite. Cualquier test que contacte una base debe usar PostgreSQL y no debe destruir bases de desarrollo.

### CORS

No existe configuración previa. El baseline debe crearla de forma explícita en FastAPI mediante `FRONTEND_URL`/`FRONTEND_URLS`, con `http://localhost:3000` como origen documentado, sin wildcard con credenciales, y con prueba de preflight si se expone el API desacoplado.

## 3. Ajustes al diseño original

### Mantener

- Los tres deployables y los cinco servicios Compose.
- Python 3.11 + Poetry para ambos backends; FastAPI/Pydantic/Pytest/Ruff.
- Next.js + React + TypeScript + App Router + npm para web.
- Health HTTP `GET /api/v1/health` y `GET /health`.
- Separación estricta de credenciales: API solo PeopleOps DB; MCP Server solo Synthetic HRIS DB; web ninguna DB.
- `Makefile` como interfaz operativa; puertos configurables por entorno; single-tenant por instancia.
- Preparación de Alembic sin migraciones de entidades.

### Adaptar al repo real

- Como el repo está vacío, la lista de archivos autorizados se concreta en el prompt operativo y debe mantenerse mínima.
- `git status`, rama base, remote y PR no pueden darse por hechos: el runbook debe comprobarlos y detener las operaciones Git si no hay `.git` o no se puede identificar la rama base.
- No documentar comandos como verificados hasta ejecutarlos realmente. La ejecución de Docker, Poetry, npm o `gh` puede quedar como requisito pendiente si el entorno no los tiene.
- No crear `.env` con secretos durante esta fase; solo `.env.example` versionable y reglas para que el implementador cree archivos locales ignorados.

### Requiere confirmación

- Si la carpeta no es el checkout Git correcto, confirmar la raíz/branch antes de crear rama o PR.
- El diseño menciona una posible preparación de Alembic, pero no exige una migración vacía: usar solo tooling/configuración mínima y no introducir una migration si no es necesaria para el scaffold.
- Confirmar la disponibilidad local de Docker, Compose, Poetry, npm y Node antes de marcar verificaciones como ejecutadas.

## 4. Plan de trabajo para Codex

1. Releer `AGENTS.md` y los documentos en el orden obligatorio; después consultar `08-SLICES-PLAN.md` y `slice-00-repository-foundation-guardrails.md`.
2. Comprobar raíz Git, branch, remotes y árbol actual; clasificar lo existente como crear, modificar por integración directa o no tocar.
3. Crear la estructura mínima y separar ownership/configuración antes de añadir runtime.
4. Crear `.gitignore`, `.env.example`, `docker-compose.yml`, `Makefile` y `README.md` con solo comandos soportados.
5. Crear scaffolds mínimos de las tres apps y health endpoints de backend; mantener web sin UI funcional.
6. Añadir tests unitarios/configuración/health/guardrails, sin mocks que oculten la frontera que se pretende probar.
7. Validar Compose, builds, arranque, health, lint, tests, preflight y escaneos de secretos/ownership cuando las herramientas estén disponibles.
8. Revisar el diff contra REQ-PHY-001..006, REQ-SEC-001..003, REQ-SEM-001..005 y ADR-001/004/006/009/010/011/012.

Durante el trabajo reconsultar `07-CTX.md` + ADR-009 para estructura, REQ-PHY-004 + ADR-006 para ownership, ADR-001 + REQ-MCP-001/009 para frontera, y REQ-SEM-001..005 + ADR-004 antes de agregar cualquier router/tool. No implementar slices posteriores.

## 5. Decisiones operativas transversales

- Triggers: solo acciones manuales de inspección, build, startup, test y health; no cron, jobs ni eventos de negocio.
- Concurrencia/locking: no hay operaciones de dominio ni tablas; no se requieren locks, transacciones de dominio o unicidad activa.
- Estados: solo estados operativos de configuración/servicio/test; no persistir enums.
- Autogeneración: no generar IDs de negocio, folios, empleados ni datos de evaluación.
- UI casi tiempo real: no aplica; no polling, SSE ni WebSocket.
- Multi-tenancy: single-tenant por instancia; no `tenant_id`, schemas por tenant ni switching de base.
- Servicios externos: ninguno; no OpenAI, LangSmith, S3, correo, webhooks o retries de integración.
- Persistencia: no hay tablas nuevas; no seeders; no assertions de dominio. Cualquier conectividad usa PostgreSQL, nunca SQLite.
- Archivos locales: `.env`, `.env.local`, `.secrets` y equivalentes deben ignorarse; no incluir secretos reales.

## 6. Resultado esperado

El prompt operativo de `prompts/prompt-codex-code-slice-00.md` contiene el contexto completo para implementar el slice. El runbook ejecutable vive en `ops/PLAN-slice00.md`. Ambos deben permanecer alineados; si aparece un archivo adicional necesario, debe marcarse como `requiere confirmación` antes de incorporarlo.

