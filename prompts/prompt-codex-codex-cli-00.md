# Prompt operativo para Codex — Slice 00

Implementa completamente `Slice 00 — Repository Foundation & Guardrails` en el repositorio PeopleOps AI. Este prompt es una guía de ejecución, no una autorización para saltar requisitos. Debes completar todas las fases y verificaciones que sean posibles en el entorno actual, dejando explícitamente como `BLOQUEADO` solo lo que requiera una herramienta o confirmación externa. Lee primero `AGENTS.md` y, en este orden, `docs/proyecto-03-peopleops-ai-BRD.md`, `docs/proyecto-03-peopleops-ai-PDD.md`, `docs/proyecto-03-peopleops-ai-PRD.md`, `docs/00-documentation-map.md`, `docs/01-SPEC.md`, `docs/02-REQ.md`, `docs/03-ADR.md`, `docs/04-PROC.md`, `docs/05-DATA.md`, `docs/06-UI.md`, `docs/07-CTX.md`, `docs/08-SLICES-PLAN.md`, `docs/slice-00-repository-foundation-guardrails.md` y `prompts/design-slice-00.md`. Inspecciona el repositorio real antes de editar.

La ausencia de `.git` no bloquea la implementación de archivos ni las pruebas locales: bloquea únicamente crear rama, commit, push o PR. No inicialices Git silenciosamente.

## Objetivo (1)

Construye la base física, reproducible y gobernada del monorepo: `peopleops-api`, `peopleops-web`, `reference-mcp-server`, dos PostgreSQL separados, configuración por entorno, Compose, Makefile, health checks, CORS explícito, baseline de lint/tests y guardrails arquitectónicos. No implementes comportamiento HR.

Cubre: estructura, scaffolds mínimos, ownership, configuración segura, Docker/Compose, áreas de soporte, health/liveness y pruebas de frontera. Queda fuera: cualquier funcionalidad de Slices 01–18, incluyendo tablas HR/PeopleOps, MCP funcional, queries, LangGraph, OpenAI, RAG/LlamaIndex, Human Review, frontend funcional y evaluación de negocio.

## Documentos que gobiernan (2)

- `AGENTS.md`: stack, límites, ownership, seguridad, testing y protocolo de ejecución.
- `docs/08-SLICES-PLAN.md`: orden y alcance de Slice 00.
- `docs/slice-00-repository-foundation-guardrails.md`: requisitos y Definition of Done directa.
- `docs/01-SPEC.md`: deployables, fronteras y baseline production-oriented.
- `docs/02-REQ.md`: REQ-PHY-001..006, REQ-SEC-001..003, REQ-SEM-001..005 y condicionantes MCP.
- `docs/03-ADR.md`: ADR-001, 004, 006, 009, 010, 011 y 012.
- `docs/07-CTX.md`: topología física, persistencias y trust boundaries.
- `docs/05-DATA.md`: ownership y prohibición de inventar schema de dominio en este slice.
- BRD/PDD/PRD, PROC y UI: contexto de producto, procesos y límites; no habilitan adelantar funcionalidad.

Si encuentras una contradicción real, detén la parte afectada y reporta los documentos involucrados. No elijas la interpretación más fácil.

## Impacto funcional (3)

No hay flujo de usuario HR. El flujo operativo es: checkout → `.env` local desde `.env.example` → validación → `docker compose config` → build/start → health de cinco servicios → lint/tests → revisión de guardrails.

Entradas: checkout, Docker/Compose, Python 3.11/Poetry, Node/npm y configuración local no versionada. Salidas: monorepo arrancable, tres deployables identificables, dos DB aisladas, health verificable y comandos reproducibles.

Reglas obligatorias:

- `peopleops-api` solo recibe configuración de `peopleops-db` y no recibe `SYNTHETIC_HRIS_DATABASE_*`.
- `reference-mcp-server` solo recibe configuración de `synthetic-hris-db` y no recibe `PEOPLEOPS_DATABASE_*`.
- `peopleops-web` solo recibe `NEXT_PUBLIC_API_BASE_URL`; nunca credenciales, URL MCP ni URL de DB.
- No SQL HRIS, ORM HRIS, fallback directo, keyword routing, phrase lists ni funciones por wording.
- No servicios extra: Redis, LocalStack, Phoenix, cola, scheduler o admin frontend.
- Health: `GET /api/v1/health` en API y `GET /health` en MCP Server.
- CORS: `FRONTEND_URL` o `FRONTEND_URLS`, origen explícito `http://localhost:3000`, sin `*` con credenciales; probar `OPTIONS` si el endpoint queda expuesto.

Ambigüedades: confirma la raíz Git si no existe `.git`; confirma disponibilidad de herramientas antes de afirmar éxito; no inventes host, puerto, credenciales o transporte MCP más allá de los valores documentados.

## Diseño de datos (4)

No crear tablas, modelos de dominio, enums persistidos, FKs, índices, seeders ni migraciones funcionales. No crear `Conversation`, `AnalysisInteraction`, `HumanReviewRequest`, `Employee`, `Contract`, `Payroll`, `PolicyDocument`, `PolicyVersion` ni `IngestionJob`.

Crear solo la infraestructura Compose de:

- `peopleops-db`: PostgreSQL, DB `peopleops`, usuario `peopleops_app`, host `5436`, container `5432`.
- `synthetic-hris-db`: PostgreSQL, DB `synthetic_hris`, usuario `synthetic_hris_app`, host `5437`, container `5432`.

Los passwords son placeholders/locales y nunca se versionan. No crear FKs cross-database ni un usuario compartido. Alembic puede quedar preparado como tooling, pero no debe crear entidades de Slice 01/02. Los tests que usen DB deben usar PostgreSQL de test, nunca SQLite; en este slice no son necesarias pruebas de tablas.

## Diseño backend (5)

### `apps/peopleops-api/`

Scaffold Python 3.11 + Poetry + FastAPI + Pydantic v2/pydantic-settings + Pytest/Ruff. Configuración propia de PeopleOps DB, CORS y logging seguro. Implementa únicamente `/api/v1/health`, tests y estructura base. No análisis, reviews, policies, HR, LangGraph, OpenAI ni conexión HRIS.

### `apps/reference-mcp-server/`

Scaffold Python 3.11 + Poetry + FastAPI o mecanismo HTTP mínimo compatible con el stack documentado para `GET /health`. Configuración propia de Synthetic HRIS. No discovery, catálogo, tools MCP, query validation, traducción o ejecución.

### `apps/peopleops-web/`

Scaffold mínimo Next.js + React + TypeScript + App Router + npm. Puede mostrar únicamente un placeholder técnico si el scaffold lo necesita para arrancar. No implementar pantallas ni datos demo.

### `packages/contracts/` y `packages/shared/`

Crear solo si el scaffold necesita estas áreas. Mantenerlos neutrales. Prohibido poner ORM, modelos HR, SQL, mappings físicos, acceso DB o contratos funcionales futuros.

### Infraestructura y configuración

Crear Compose con exactamente cinco servicios: `peopleops-web`, `peopleops-api`, `reference-mcp-server`, `peopleops-db`, `synthetic-hris-db`. Usar nombres de servicio y puertos internos entre contenedores; dejar puertos host configurables por `.env`. DBs con health checks. Aplicaciones con health/liveness mínimo. Añadir `Makefile` con `help install build up down restart ps logs lint format test test-unit test-integration health clean`, delegando a Poetry, npm y Compose.

## Diseño frontend (6)

No hay pantallas, formularios, componentes de negocio, navegación, polling ni responsive UX que implementar. No hay template UI confirmado en `AGENTS.md`; seguir las convenciones mínimas de Next.js y no incorporar plantilla propietaria.

Crear/verificar `apps/peopleops-web/.env.example` con `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` y crear localmente `.env.local` desde él solo si se ejecutan comandos frontend. `.env.local` debe estar en `.gitignore`, sin secretos. El frontend solo consume el API; no conoce MCP ni ninguna DB. No agregar fake APIs, MSW, `mockServiceWorker.js`, handlers, aliases de mocks ni demo plugins.

## Secuencia recomendada (7)

1. Orientar: verificar raíz Git, branch/remotes, herramientas y estado; si no hay `.git`, marcar bloqueo de operaciones Git sin borrar ni inicializar silenciosamente.
2. Releer documentos y clasificar archivos actuales; como el repo observado está vacío, crear solo archivos autorizados.
3. Crear estructura, `.gitignore`, `.env.example`, Compose, Makefile y README con comandos que se puedan probar.
4. Crear scaffolds backend/frontend, configuración separada, health endpoints y CORS.
5. Añadir tests unitarios/config/health/guardrails y preparar Alembic solo sin migraciones de negocio.
6. Crear `.env.local` frontend únicamente para las verificaciones frontend; nunca commitearlo.
7. Ejecutar config/build/up/health/lint/test/preflight y escaneos; corregir solo problemas del slice.
8. Revisar diff, alcance, secretos y Definition of Done. No commit/push/PR sin autorización expresa.

### Detalle obligatorio por fase

#### Fase 1 — Orientación y auditoría

- Ejecuta `pwd`, `git status`, `git branch --show-current` y `git remote -v` si existe `.git`; registra la ausencia de Git sin detener la implementación no-Git.
- Inspecciona `AGENTS.md`, README, docs, `prompts/`, `ops/`, Compose, `.env*`, `Makefile`, `apps/`, `packages/`, tests y configuraciones existentes.
- Confirma Python 3.11, Poetry, Node, npm, Docker y Compose. No sustituyas herramientas por analogía.
- Clasifica cada archivo como `crear`, `modificar por integración directa` o `no tocar`.
- Busca secretos y datos reales. No copies datos del HRIS ni documentos privados.

#### Fase 2 — Estructura y configuración

- Crea `apps/peopleops-api/`, `apps/peopleops-web/`, `apps/reference-mcp-server/`, `packages/contracts/`, `packages/shared/`, `synthetic-hris/migrations/`, `synthetic-hris/seeds/`, `synthetic-hris/alternate-schema/`, `policies/synthetic/`, `evaluation/cases/`, `evaluation/runs/` y `ops/` solo cuando el scaffold las necesite.
- Crea `.gitignore` con `.env`, `.env.*` salvo `.env.example`, `.env.local`, `.secrets`, caches, builds, dependencias y datos locales; no ignores `.env.example`.
- Crea el `.env.example` raíz con placeholders no secretos, puertos configurables y configuración de ambos ownerships sin compartir usuario.
- Crea los `.env.example` de API, MCP Server y web; no pongas credenciales HRIS en API ni PeopleOps DB en MCP Server.
- Usa nombres de servicio Compose, nunca `localhost`, para comunicación entre contenedores.
- Si preparas Alembic, deja solo estructura/configuración sin migrations de entidades.

#### Fase 3 — Aplicaciones backend

- API: FastAPI, Pydantic v2/pydantic-settings, logging seguro, CORS explícito y `GET /api/v1/health`; sin rutas de negocio.
- MCP Server: servicio HTTP mínimo independiente con `GET /health` en puerto configurable; configuración exclusiva de Synthetic HRIS; sin transporte MCP funcional, discovery ni tools.
- Para ambos, añade tests de arranque/health/configuración inválida y tests que aseguren la ausencia de variables de ownership ajeno.
- No añadas conexión real a ninguna DB desde API/MCP si no es necesaria para el health de Slice 00; si añades conectividad, respeta exclusivamente el ownership y usa PostgreSQL.

#### Fase 4 — Compose y bases

- Declara exactamente cinco servicios: `peopleops-web`, `peopleops-api`, `reference-mcp-server`, `peopleops-db`, `synthetic-hris-db`.
- Publica por defecto web `3000`, API `8000`, MCP `8001`, PeopleOps DB `5436:5432`, Synthetic HRIS DB `5437:5432`, todos configurables.
- Usa PostgreSQL para ambas DB; DB/nombre/usuario documentados: `peopleops`/`peopleops_app` y `synthetic_hris`/`synthetic_hris_app`.
- Añade health checks PostgreSQL y dependencias de startup solo cuando sean necesarias; no añadas migraciones, seeds, colas o schedulers.
- Verifica `docker compose config`, build, startup, `docker compose ps` y endpoints health. Si Docker no está disponible, reporta el bloqueo exacto y ejecuta checks estáticos.

#### Fase 5 — Frontend

- Crea el scaffold mínimo Next.js + React + TypeScript + App Router + npm.
- Crea/verifica `apps/peopleops-web/.env.example` con `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`; crea `.env.local` desde ese archivo solo si ejecutas checks frontend.
- No copies template, no agregues UI funcional, páginas demo, fake APIs, MSW, `mockServiceWorker.js`, handlers, aliases mock ni datos de ejemplo.
- Verifica que web no contenga variables de DB, Synthetic HRIS, MCP o secretos.

#### Fase 6 — Makefile y documentación

- Crea `Makefile` raíz con exactamente los targets mínimos documentados: `help`, `install`, `build`, `up`, `down`, `restart`, `ps`, `logs`, `lint`, `format`, `test`, `test-unit`, `test-integration`, `health`, `clean`.
- Cada target debe delegar a Poetry, npm o Docker Compose existentes; no inventes targets que no puedan ejecutarse.
- Documenta en README el arranque limpio, variables, puertos, ownership, health, tests y límites de Slice 00. No afirmes checks no ejecutados.

#### Fase 7 — Pruebas y guardrails

- Ejecuta lint, format check, tests unitarios, tests de configuración/health, Compose config, smoke tests y preflight CORS cuando el API esté expuesto.
- Inspecciona que API no incluya `SYNTHETIC_HRIS_DATABASE_*`, que MCP no incluya `PEOPLEOPS_DATABASE_*` y que web no incluya DB credentials.
- Escanea `AnalysisInteraction`, `Employee`, `Contract`, `Payroll`, `LangGraph`, `OpenAI`, `LlamaIndex`, `MCP discovery`, `ConceptualQuery`, `HumanReview`, `setupWorker`, `mockServiceWorker`, `fake-api`, `@db` y `@api-utils`; cualquier implementación real de esos elementos es una violación de alcance.
- Si alguna prueba usa una DB, comprueba primero conexión no destructiva y usa PostgreSQL; nunca SQLite ni una base de desarrollo para pruebas destructivas.

#### Fase 8 — Cierre

- Revisa archivos autorizados, diff, secretos, servicios Compose, dependencias y Definition of Done completa.
- Reporta por separado `PASÓ`, `NO APLICA` y `BLOQUEADO`; no marques Slice 00 completo si quedan checks obligatorios bloqueados.
- No hagas commit, push ni PR sin autorización. Si no hay `.git`, reporta que las operaciones Git quedan pendientes, pero no deshagas los archivos creados.

## Riesgos y puntos de control (8)

- Detener si aparece acceso API → Synthetic HRIS, acceso MCP → PeopleOps DB, credencial cruzada, ORM compartido o SQL HRIS en PeopleOps.
- Detener si se propone una cuarta app, un servicio Docker extra, SQLite, un template completo o una dependencia especulativa.
- No agregar MCP funcional, LangGraph, OpenAI, RAG, tablas de dominio o frontend funcional.
- No documentar ports/commands no verificados. No asumir `main` como rama base.
- No cambiar archivos fuera de la lista autorizada; si surge uno adicional, marcar `requiere confirmación`.
- Concurrencia, locking, eventos, jobs, autogeneración y casi tiempo real no aplican.
- Como no hay persistencia funcional, no ejecutar migraciones/seeders ni crear bases de test destructivas.

## Checklist de aceptación (9)

- [ ] Existen los tres deployables y las áreas de soporte necesarias, sin cuarto deployable.
- [ ] Compose declara exactamente cinco servicios y `docker compose config` pasa.
- [ ] DBs PostgreSQL separadas, health checks y puertos configurables.
- [ ] API, MCP Server y web tienen configuración de ownership correcta.
- [ ] API no contiene credenciales/rutas de Synthetic HRIS; MCP no contiene PeopleOps DB; web no contiene DB.
- [ ] `GET /api/v1/health` y `GET /health` funcionan cuando los servicios arrancan.
- [ ] CORS explícito con `http://localhost:3000`, sin wildcard con credenciales, y preflight verificado si aplica.
- [ ] `.env.example` no tiene secretos; `.env`, `.env.local`, `.secrets` ignorados.
- [ ] No hay SQLite, tablas/migrations HR, SQL HRIS, semantic hardcoding, MCP tools, RAG, LangGraph, UI funcional ni servicios extra.
- [ ] Makefile, lint, format, test, smoke/config/guardrail tests y README contienen solo comandos comprobados.
- [ ] No se usan servicios externos ni jobs/retries de integración.
- [ ] El diff no adelanta Slices 01–18 y la Definition of Done queda trazable.

### Matriz de trazabilidad mínima

| Requisito | Evidencia obligatoria |
|---|---|
| REQ-PHY-001..003 | Directorios y scaffolds de los tres deployables |
| REQ-PHY-004 | Dos DB/usuarios separados y variables sin cruce |
| REQ-PHY-005 | Compose reproducible, health checks y README verificado |
| REQ-PHY-006 | Apps separables y configuración independiente |
| REQ-SEC-001..003 | Datos sintéticos, `.env.example`, `.gitignore`, scan sin secretos |
| REQ-SEM-001..005 | Guardrail/test sin keyword routing, phrase lists ni functions por wording |
| ADR-001/006/009 | Topología, ownership y tres deployables comprobados |
| ADR-004/011/012 | Sin semantic hardcoding, schema físico o lógica agentic prematura |

### Persistencia

Este slice no modifica persistencia funcional. No se requieren migraciones, seeders ni assertions de tablas. Si una prueba necesita DB, usar PostgreSQL del mismo motor documentado y comprobar conexión antes; nunca SQLite.

## Archivos autorizados para cambio

Crear/modificar únicamente, salvo confirmación adicional:

```text
AGENTS.md                         # solo si hace falta alinear decisiones cerradas
README.md
.gitignore
.env.example
docker-compose.yml
Makefile
apps/peopleops-api/**
apps/peopleops-web/**
apps/reference-mcp-server/**
packages/contracts/**
packages/shared/**
synthetic-hris/.gitkeep
policies/synthetic/.gitkeep
evaluation/.gitkeep
ops/PLAN-slice00.md
tests/**                           # solo foundation/health/config/guardrails
```

No tocar otros archivos. En particular, no crear migraciones de dominio, código HR, MCP funcional, RAG, LangGraph, Human Review, UI funcional ni cambios cosméticos.

## Git/PR

Solo con autorización explícita: rama `codex/slice00`; commits claros por fase; `git push --set-upstream origin codex/slice00`; PR con `gh pr create` hacia la rama base real verificada, título `Slice 00: Repository Foundation & Guardrails`, y etiquetas solo si ya existen. Abrir PR únicamente con checklist verde.

## Comportamiento ante bloqueos

No conviertas una herramienta ausente en una razón para omitir la implementación. Si falta Git, continúa con archivos y checks no-Git; si falta Docker, ejecuta validaciones estáticas y reporta los smoke tests pendientes; si falta Poetry/npm, valida estructura/configuración y reporta los comandos pendientes. Solo detén una decisión que cambie arquitectura, seguridad, contrato público o alcance.

## Runbook

Guardar y mantener sincronizada la versión ejecutable en `ops/PLAN-slice00.md`; ejecutarla con `ops/run-runbook.sh` si ese runner existe y está autorizado. No inicializar Git, no instalar dependencias globales y no ejecutar comandos destructivos sin confirmación.

```bash
set -eu

git status
git branch --show-current
git remote -v
find . -maxdepth 3 -type f | sort | sed -n '1,240p'

test -f AGENTS.md
test -f prompts/design-slice-00.md
test -f docs/slice-00-repository-foundation-guardrails.md

find . -maxdepth 3 \( -name 'docker-compose*.yml' -o -name 'compose*.yml' -o -name '.env.example' -o -name '.gitignore' -o -name 'pyproject.toml' -o -name 'package.json' -o -name 'Makefile' \) -print

docker compose config
docker compose build
docker compose up -d
docker compose ps

curl --fail --silent --show-error http://localhost:8000/api/v1/health
curl --fail --silent --show-error http://localhost:8001/health

make lint
make test
git diff --check
git diff --stat
git diff

if command -v rg >/dev/null 2>&1; then
  rg -n 'SYNTHETIC_HRIS|HRIS_DATABASE|password|secret|token' apps/peopleops-api .env.example || true
  rg -n 'PEOPLEOPS_DATABASE|password|secret|token' apps/reference-mcp-server .env.example || true
  rg -n 'AnalysisInteraction|EmployeePayroll|LangGraph|LlamaIndex|HumanReview|setupWorker|mockServiceWorker|fake-api|@db|@api-utils' apps packages synthetic-hris || true
fi

docker compose down

# Solo con autorización explícita y checklist verde:
# git switch -c codex/slice00
# git add <archivos-autorizados>
# git commit -m "chore(slice00): scaffold repository foundation"
# git push --set-upstream origin codex/slice00
# gh pr create --base <rama-base-real> --head codex/slice00 --title "Slice 00: Repository Foundation & Guardrails" --body-file ops/PLAN-slice00.md
```
