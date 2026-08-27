# Design Slice 00 — Repository Foundation & Guardrails

**SLICE:** `00`  
**slice-slug:** `slice00`  
**Estado:** Diseño de implementación — arquitectura técnica cerrada para Slice 00  
**Slice fuente:** `slice-00-repository-foundation-guardrails.md`

## 1. Objetivo del slice

El Slice 00 crea la base física, operativa y de gobernanza del repositorio PeopleOps AI antes de introducir comportamiento funcional de negocio.

Debe dejar preparado un monorepo reproducible con tres deployables claramente separados:

- `peopleops-api`;
- `peopleops-web`;
- `reference-mcp-server`.

También debe dejar preparada la infraestructura común necesaria para los slices posteriores:

- estructura del monorepo;
- configuración por entorno;
- `.env.example` sin secretos;
- Docker/Compose;
- PostgreSQL para PeopleOps;
- PostgreSQL separado para Synthetic Reference HRIS;
- áreas para contratos compartidos, documentación, evaluación, synthetic HRIS y policies sintéticas;
- baseline de linting/testing;
- comandos de desarrollo reproducibles;
- health checks mínimos;
- guardrails explícitos para Codex y para revisión de arquitectura.

El objetivo arquitectónico principal no es implementar funcionalidad HR, sino impedir que los siguientes slices comiencen desde una base que permita romper las fronteras del producto.

### Arquitectura física cerrada

```text
Browser
  │
  ▼
peopleops-web :3000
  │ HTTP
  ▼
peopleops-api :8000
  │
  ├── peopleops-db :5432 internal / :5436 host
  │
  └── [slices posteriores] HRDataGateway
             │
             ▼
          MCP Client
             │
             ▼
reference-mcp-server :8001
             │
             ▼
synthetic-hris-db :5432 internal / :5437 host
```

`peopleops-api` accede a `peopleops-db` y nunca a `synthetic-hris-db`. `reference-mcp-server` accede a `synthetic-hris-db` y nunca a `peopleops-db`. `peopleops-web` solo consume `peopleops-api`.


### Procesos que cubre

1. Inicialización del monorepo.
2. Separación física de deployables.
3. Separación de ownership entre PeopleOps y Synthetic HRIS.
4. Configuración base de Docker/Compose.
5. Configuración segura de variables de entorno.
6. Baseline de calidad, lint y tests.
7. Health/liveness mínimo de los servicios.
8. Guardrails anti-hardcoding.
9. Guardrails de frontera MCP.
10. Preparación de espacios de contratos y artifacts de evaluación, sin implementar todavía contratos funcionales completos.
11. Preparación de CORS si `peopleops-api` se expone desde este slice como API desacoplada para `peopleops-web`.

### Procesos que NO cubre

Quedan expresamente fuera:

- modelo funcional de Synthetic Reference HRIS;
- tablas de Employee, Contract, Attendance, Vacation, Payroll u otras entidades HR;
- `Conversation`;
- `AnalysisInteraction`;
- persistencia funcional de Human Review;
- MCP discovery funcional;
- HRDataGateway funcional;
- MCP Client funcional;
- conceptual query contract completo;
- traducción/validación/ejecución de queries;
- LangGraph productivo;
- OpenAI runtime;
- Policy RAG;
- LlamaIndex ingestion/retrieval;
- pgvector funcional para policies;
- frontend funcional;
- pantallas, navegación y UX final;
- Human-in-the-loop;
- evaluación funcional;
- schema-independence;
- adapters BIZAG/SAP/Workday;
- Redis;
- LocalStack;
- Phoenix;
- colas;
- WebSocket/SSE;
- observabilidad SaaS obligatoria.

El Slice 00 no debe adelantar ningún comportamiento perteneciente a los Slices 01–18.

---

## 2. Documentos que gobiernan este slice

### `AGENTS.md`

Es la instrucción de ejecución obligatoria para Codex.

Aporta estas restricciones relevantes:

- trabajar un slice a la vez;
- no implementar infraestructura hipotética;
- MCP será la única ruta integrada hacia datos HR;
- `peopleops-api` no puede tener credenciales ni conexión directa al Synthetic Reference HRIS;
- `reference-mcp-server` no debe depender de PeopleOps DB;
- no semantic hardcoding;
- los contratos deben ser tipados;
- ownership separado;
- configuración por entorno;
- datos sintéticos;
- no secretos;
- cada slice debe incluir tests suficientes para demostrar su Definition of Done;
- no commit/push salvo instrucción explícita de la ejecución;
- no marcar un slice completo si no cumple su Definition of Done.

### `08-SLICES-PLAN.md`

Fija el objetivo del Slice 00:

> monorepo, configuración, calidad, contratos básicos y guardrails anti-hardcoding.

También establece que Slice 00 no tiene dependencias y que el detalle del slice debe derivarse de SPEC/REQ/ADR/PROC/DATA/UI/CTX.

### `slice-00-repository-foundation-guardrails.md`

Es la especificación directa del slice.

Obliga a:

- crear los tres deployables;
- crear estructura de soporte;
- configurar `.env.example`;
- Docker/Compose;
- linting/testing;
- comandos reproducibles;
- `AGENTS.md`/guardrails;
- contratos base compartidos;
- health checks;
- demostrar que PeopleOps API no puede abrir conexión al HRIS DB.

Prohíbe en este slice:

- HRIS completo;
- MCP discovery;
- LangGraph productivo;
- RAG;
- frontend funcional;
- Human Review;
- Redis, colas y observabilidad SaaS no justificada;
- un cuarto servicio administrativo;
- shortcuts que luego se conviertan en ruta productiva.

### `01-SPEC.md`

Confirma:

- `peopleops-api` como FastAPI;
- `peopleops-web` como deployable separado;
- `reference-mcp-server` backend-only;
- PostgreSQL/pgvector como parte del baseline;
- Docker;
- separación de fronteras;
- ausencia de acceso directo PeopleOps → HRIS;
- baseline production-oriented con `.env.example`, migrations, logging, tests y documentación.

### `02-REQ.md`

Requisitos directamente trazados por el slice:

- `REQ-PHY-001` — debe existir `peopleops-api`;
- `REQ-PHY-002` — debe existir `peopleops-web`;
- `REQ-PHY-003` — debe existir `reference-mcp-server`;
- `REQ-PHY-004` — PeopleOps Data y HRIS Data deben tener ownership lógico separado;
- `REQ-PHY-005` — levantamiento reproducible con Docker/Compose o equivalente;
- `REQ-PHY-006` — monorepo debe permitir despliegue independiente de los tres deployables;
- `REQ-SEC-001` — datos públicos sintéticos;
- `REQ-SEC-002` — secrets por entorno;
- `REQ-SEC-003` — `.env.example` obligatorio;
- `REQ-SEM-001..005` — prohibición de keyword routing, phrase lists y funciones por wording; contracts tipados y guardrails determinísticos.

Requisitos que deben condicionar la base aunque se implementen después:

- `REQ-MCP-001` — PeopleOps API nunca accede directamente al Synthetic HRIS;
- `REQ-MCP-009` — no fallback silencioso a DB directa.

### `03-ADR.md`

Decisiones que no pueden violarse:

- ADR-001 — MCP es frontera obligatoria de structured data.
- ADR-004 — no semantic keyword routing.
- ADR-006 — ownership separado PeopleOps / HRIS.
- ADR-009 — tres deployables dentro de un monorepo.
- ADR-010 — no MCP Admin Frontend en MVP.
- ADR-011 — Synthetic HRIS es fixture, no contrato.
- ADR-012 — deterministic guardrails alrededor del razonamiento agentic.

ADR-005 permite reutilizar conceptualmente patrones probados de Enterprise RAG para Policy RAG, pero no autoriza copiar su arquitectura completa ni introducir en Slice 00 servicios específicos de Enterprise RAG que no estén justificados.

### `07-CTX.md`

Confirma la arquitectura física:

```text
peopleops-web
      ↓
peopleops-api
      ↓
MCP Client
      ↓
Reference MCP Server
      ↓
Synthetic Reference HRIS
```

Confirma la topología Docker mínima prevista:

- `peopleops-web`;
- `peopleops-api`;
- `reference-mcp-server`;
- `peopleops-db`;
- `synthetic-hris-db`.

Confirma también:

- PeopleOps DB y Synthetic HRIS con ownership separado;
- `peopleops-api` sin acceso directo a Synthetic HRIS;
- `reference-mcp-server` sin dependencia de PeopleOps DB;
- Redis no obligatorio.

### Decisiones técnicas cerradas para el foundation

Se cierran las decisiones operativas del Slice 00 para que Codex pueda implementar sin ambigüedad.

#### Backend y runtime Python
- Python **3.11**.
- FastAPI.
- Poetry como gestor de dependencias.
- Pydantic v2 + `pydantic-settings` para configuración/contratos.
- Pytest para tests.
- Ruff para lint/format.
- Alembic para migrations PostgreSQL cuando los slices de persistencia las requieran.
- Versiones concretas bloqueadas mediante `poetry.lock`.

#### Frontend
- **Next.js**.
- **TypeScript**.
- React como runtime de UI provisto por Next.js.
- pnpm como package manager.
- App Router como convención base del frontend.
- Slice 00 crea solo el scaffold técnico mínimo; la UI funcional pertenece al slice de UX.
- No se incorpora un template UI propietario en el foundation.
- Variable pública obligatoria: `NEXT_PUBLIC_API_BASE_URL`.

#### Makefile
`Makefile` raíz es la **interfaz operativa canónica** del repositorio. Targets mínimos: `help`, `install`, `build`, `up`, `down`, `restart`, `ps`, `logs`, `lint`, `format`, `test`, `test-unit`, `test-integration`, `health`, `clean`. Debe delegar en Poetry, pnpm y Docker Compose.

#### Puertos locales
| Servicio | Host | Container |
|---|---:|---:|
| `peopleops-web` | 3000 | 3000 |
| `peopleops-api` | 8000 | 8000 |
| `reference-mcp-server` | 8001 | 8001 |
| `peopleops-db` | 5436 | 5432 |
| `synthetic-hris-db` | 5437 | 5432 |

Todos son configurables por `.env`. Entre containers se usan nombres de servicio y puertos internos.

#### Bases de datos y ownership
PeopleOps:
- service `peopleops-db`;
- database `peopleops`;
- user `peopleops_app`;
- credenciales disponibles solo para `peopleops-api`.

Synthetic HRIS:
- service `synthetic-hris-db`;
- database `synthetic_hris`;
- user `synthetic_hris_app`;
- credenciales disponibles solo para `reference-mcp-server`.

Los passwords nunca se versionan. No existe usuario compartido con acceso a ambas bases.

#### Multi-tenancy
El MVP público es **single-tenant por instancia**. No se implementan `tenant_id`, schemas por tenant, database switching ni paquetes de multitenancy. Una evolución multi-tenant requiere ADR propio.

#### MCP transport y health
`reference-mcp-server` es un deployable backend independiente. En Slice 00 expone health HTTP mínimo en `:8001`; discovery, tools y query execution pertenecen a slices posteriores.

---

## 3. Impacto funcional

### Flujo operativo del usuario/desarrollador

El Slice 00 no implementa todavía un flujo funcional HR para usuario final.

El flujo esperado es de desarrollo/operación:

```text
Developer
   ↓
clone repository
   ↓
prepare environment from .env.example
   ↓
validate configuration
   ↓
build/start Docker Compose
   ↓
peopleops-api          → healthy
peopleops-web          → healthy/placeholder
reference-mcp-server   → healthy/placeholder
peopleops-db           → healthy
synthetic-hris-db      → healthy
   ↓
run lint/tests
   ↓
verify architecture guardrails
```

### Entradas

- checkout limpio del repositorio;
- Docker/Compose disponible;
- archivo `.env` creado a partir de `.env.example`;
- valores locales no sensibles o secrets locales no versionados.

### Salidas

- monorepo estructurado;
- tres deployables identificables;
- dos servicios PostgreSQL separados;
- Docker/Compose validable;
- health/liveness verificable;
- baseline de tests/lint;
- guardrails versionados;
- estructura de evaluation y docs;
- ninguna ruta directa PeopleOps → Synthetic HRIS.

### Estados esperados

Este slice no introduce estados funcionales persistidos.

Estados operativos mínimos:

- configuration-valid;
- configuration-invalid;
- service-starting;
- service-healthy;
- service-unhealthy;
- test-pass;
- test-fail.

Estos son estados operativos, no enums de negocio y no deben persistirse en tablas.

### Reglas obligatorias

1. `peopleops-api` no recibe credenciales de `synthetic-hris-db`.
2. `reference-mcp-server` no recibe credenciales de `peopleops-db`.
3. `peopleops-web` no recibe credenciales de ninguna DB.
4. `peopleops-web` no conecta directamente con MCP.
5. No se introduce conexión directa PeopleOps→Synthetic HRIS.
6. No se implementa fallback directo.
7. No se incorporan keywords/phrase routing ni siquiera en scaffolding.
8. No se copian ORM/models del HRIS hacia PeopleOps.
9. Los tres deployables siguen siendo independientes.
10. Datos/secrets reales no se incluyen.
11. `.env.example` contiene placeholders seguros.
12. Los tests deben demostrar la frontera de credenciales/configuración.
13. No se introducen Redis, LocalStack, Phoenix, colas u otros servicios no requeridos.
14. `reference-mcp-server` continúa backend-only.

### Validaciones obligatorias

- `docker compose config` debe validar.
- Los servicios PostgreSQL deben tener health check.
- Los tres deployables deben ser identificables en Compose.
- Los servicios de aplicación deben tener un health/liveness mínimo.
- `.env.example` no puede contener secretos reales.
- `.env`, `.secrets` y equivalentes locales deben estar ignorados por Git.
- El entorno de `peopleops-api` no puede contener variables de conexión al HRIS.
- El entorno de `reference-mcp-server` no puede contener variables de PeopleOps DB.
- los comandos de test/lint deben ser reproducibles.
- el repositorio debe poder arrancar desde una clonación limpia siguiendo la documentación del Slice 00.

### Trigger points

No existen eventos de negocio ni entidades derivadas en este slice.

Triggers operativos:

- configuración: manual, al crear `.env`;
- build: manual;
- startup: manual;
- migrations baseline: manual solo si el mecanismo de migraciones queda confirmado;
- tests/lint: manual y repetible;
- health checks: automáticos por Docker una vez levantados los servicios.

No se introduce cron.

No se introduce scheduler.

No se introduce job queue.

### Concurrencia y locking

No existen operaciones de negocio multi-paso ni escrituras concurrentes en tablas de aplicación.

Por tanto:

- no se requieren locks de filas;
- no se requieren transacciones de dominio;
- no se requieren retries de deadlock;
- no aplica unicidad activa.

La concurrencia relevante es operacional: dos instancias/containers no deben compartir accidentalmente credenciales o storage perteneciente al otro ownership.

### Dependencias/sincronizaciones

Antes de cerrar el slice deben estar confirmados:

1. estructura física del monorepo;
2. separación de variables de entorno;
3. Compose válido;
4. health checks;
5. baseline de test/lint;
6. prohibición comprobable de acceso PeopleOps→HRIS.

Los slices 01 y 02 no deben comenzar hasta que este baseline esté en verde.

### Servicios externos y resiliencia

Este slice no debe invocar:

- OpenAI;
- LangSmith;
- S3;
- correo;
- webhooks;
- servicios externos.

Por tanto, las reglas de job/retry para integraciones externas no aplican todavía.

No se debe añadir LocalStack "por si luego usamos S3".

---

## 4. Diseño de datos

### Cambios obligatorios

No se crean tablas de negocio en este slice.

Sí se prepara la infraestructura para dos ownerships separados:

```text
peopleops-db
synthetic-hris-db
```

Los servicios deben ser PostgreSQL.

`peopleops-db` será la futura persistencia de PeopleOps.

`synthetic-hris-db` será la futura persistencia del Synthetic Reference HRIS.

### Tablas nuevas

Ninguna tabla funcional en Slice 00.

No crear todavía:

- Conversation;
- AnalysisInteraction;
- HumanReviewRequest;
- Employee;
- Department;
- Contract;
- Payroll;
- PolicyDocument;
- PolicyVersion;
- IngestionJob.

### Columnas, relaciones, enums y constraints

No aplican en este slice.

No debe inventarse schema de negocio.

### Migrations

El proyecto debe quedar preparado para Alembic porque la especificación
production-oriented lo exige. En este slice no se crean migrations de
entidades funcionales.

En Slice 00 no debe existir una migration que cree entidades de Slice 01 o Slice 02.

### Claves e índices compuestos

No aplican.

### Unicidad activa

No aplica.

### Integridad referencial

No aplica porque no se crean tablas funcionales.

La separación de ownership se garantiza en infraestructura/configuración, no mediante FKs entre bases.

Debe quedar explícitamente prohibido crear FKs cross-database entre PeopleOps Data y Synthetic HRIS.

### Estados/enums persistidos

No se crean enums persistidos.

### Autogeneración de datos

No aplica.

No se generan folios, códigos HR, employee codes, request_id ni IDs de negocio en este slice.

### Multi-tenancy

No está documentado.

No introducir diseño multi-tenant.

### Base de datos de pruebas

Aunque Slice 00 no agrega persistencia funcional, cualquier test que llegue a usar PostgreSQL debe usar PostgreSQL, no SQLite.

Para persistencia futura los tests usarán PostgreSQL, nunca SQLite. Convención: `peopleops_test`/`peopleops_test` y `synthetic_hris_test`/`synthetic_hris_test`, con credenciales separadas por entorno. Tests destructivos contra bases de desarrollo están prohibidos.

### Trazabilidad con procesos anteriores

No existen slices previos.

Este slice se convierte en el baseline que Slice 01 y Slice 02 deben reutilizar.

### Cómo evitar romper slices posteriores

- no cerrar prematuramente el schema HRIS;
- no cerrar el conceptual query contract completo;
- no compartir ORM;
- no acoplar PeopleOps a PostgreSQL HRIS;
- no usar la DB sintética como shortcut de desarrollo;
- no crear un único usuario DB con acceso a ambas bases.

---

## 5. Diseño backend

### Stack confirmado

El stack está confirmado en `AGENTS.md` y debe utilizarse sin introducir
alternativas:

- Python 3.11 + Poetry;
- FastAPI;
- Pydantic v2 + `pydantic-settings`;
- PostgreSQL + pgvector;
- Alembic para migrations;
- Pytest + Ruff;
- Next.js + React + TypeScript + App Router + pnpm;
- LangGraph;
- OpenAI;
- LlamaIndex;
- MCP;
- Docker Compose;
- LangSmith como soporte opcional de tracing/evaluación;
- `Makefile` raíz como interfaz operativa canónica.

No sustituir estos componentes por otro runtime, framework o package
manager sin un ADR aprobado.

### `apps/peopleops-api/`

Responsabilidad en Slice 00:

- scaffold mínimo del deployable;
- configuración por entorno;
- endpoint/liveness mínimo;
- estructura de tests;
- CORS base si el servicio ya se expone para el futuro frontend;
- cero lógica HR;
- cero LangGraph productivo;
- cero OpenAI runtime;
- cero Policy RAG;
- cero conexión al Synthetic HRIS.

No crear todavía handlers de `/analysis`, reviews o policies.

### `apps/reference-mcp-server/`

Responsabilidad en Slice 00:

- scaffold mínimo del deployable;
- configuración propia;
- health/liveness mínimo;
- preparación del boundary;
- posibilidad futura de usar credenciales únicamente del Synthetic HRIS.

No implementar:

- capability discovery;
- schema discovery;
- semantic metadata;
- query validation;
- query execution.

El MCP funcional comienza en slices posteriores.

### `apps/peopleops-web/`

No es backend.

Debe existir como deployable/directorio identificable, pero no se implementa frontend funcional.

### `packages/contracts/`

Debe existir como área para contratos neutrales compartidos.

En Slice 00 puede contener únicamente:

- convenciones base;
- tipos verdaderamente neutrales necesarios para health/config si se justifican.

No debe contener todavía:

- SemanticRequest definitivo;
- ConceptualQuery completo;
- MCP catalog definitivo;
- domain models HR.

### `packages/shared/`

Solo utilidades neutrales comprobablemente compartidas.

No utilizar `shared` como lugar para:

- ORM;
- modelos HR;
- lógica de negocio;
- mapeos físicos;
- acceso DB.

### Configuración

Debe existir configuración separada por deployable.

Variables críticas deben expresar ownership, no ocultarlo.

Ejemplo conceptual de separación — nombres definitivos requieren confirmación:

```text
peopleops-api:
  PEOPLEOPS_DATABASE_*

reference-mcp-server:
  SYNTHETIC_HRIS_DATABASE_*
```

`peopleops-api` no debe disponer de `SYNTHETIC_HRIS_DATABASE_*`.

### CORS

Dado que la arquitectura prevé un frontend desacoplado consumiendo `peopleops-api`, el baseline debe dejar CORS explícito.

Debe contemplar:

- `FRONTEND_URL` o `FRONTEND_URLS` en `.env.example`;
- lista explícita de origins;
- no usar wildcard con credenciales;
- verificación de OPTIONS/preflight cuando el API esté expuesto.

El origen local confirmado es `http://localhost:3000`, configurable
mediante `FRONTEND_URL` o `FRONTEND_URLS`.

### Migrations/models/relationships

No se implementan modelos de dominio en Slice 00.

No se implementan relaciones de dominio.

El tooling de migrations puede prepararse con Alembic, sin crear todavía
migrations de entidades de Slice 01 o Slice 02.

### Validación de entrada

Solo validación de configuración.

No Form Requests, schemas HR ni payloads de análisis.

### Controllers/handlers

Solo health/liveness y, si es necesario, root/info mínimo técnico.

No business endpoints.

### Services/actions

Ninguno de negocio.

Puede existir infraestructura mínima de configuración/health si el framework lo requiere.

### Policies de acceso

No aplica todavía a acciones de negocio.

La separación de credenciales sí es un guardrail obligatorio.

### Routes/endpoints

Como mínimo confirmado por PRD:

```text
GET /api/v1/health
```

No habilitar todavía endpoints de análisis/reviews.

Para `reference-mcp-server`, el health mínimo confirmado es HTTP en
`GET /health` sobre el puerto configurable, con valor local por defecto
`8001`. El transporte MCP funcional queda para slices posteriores.

### Transacciones/locking

No aplica a lógica de dominio en este slice.

### Jobs/listeners

No se crean.

### Logging

Se permite baseline de logging técnico seguro porque la SPEC exige production-oriented logging, pero:

- no LangSmith obligatorio;
- no Phoenix;
- no exporter externo;
- no datos sensibles;
- no chain-of-thought.

---

## 6. Diseño frontend

### Estado del frontend en Slice 00

No se implementa frontend funcional.

El documento del slice lo excluye expresamente.

Debe existir únicamente `apps/peopleops-web/` como deployable identificable y con la mínima estructura necesaria para integrarse después.

### Framework

`peopleops-web` usa Next.js + TypeScript con pnpm y App Router. Slice 00 crea solo el scaffold mínimo verificable; no implementa pantallas funcionales ni adopta todavía un design system específico.

### Pantallas

Ninguna.

### Formularios

Ninguno.

### Componentes

Ninguno.

### Acciones de usuario

Ninguna funcional.

### Datos visibles

Solo un indicador técnico de health si el runtime confirmado lo necesita para demostrar que el deployable arranca.

No crear dashboard, chat, policies ni Human Review.

### Validaciones UI

No aplican.

### Template de UI

No hay template confirmado en `AGENTS.md`.

No incorporar templates UI propietarios por defecto.

### `.env` frontend

Deben existir `apps/peopleops-web/.env.example` y `apps/peopleops-web/.env.local` (ignorado por Git). Variable obligatoria: `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`. El frontend nunca recibe credenciales DB ni URL directa del MCP Server.

### Casi tiempo real

No aplica.

No polling.

No WebSocket.

No SSE.

---

## 7. Secuencia de implementación recomendada

### Fase 1 — análisis de código existente

1. Ejecutar `git status`.
2. Identificar rama base real.
3. Verificar si el repo está vacío o parcialmente inicializado.
4. Leer `AGENTS.md`.
5. Leer documentos BRD/PDD/PRD y baseline técnico en el orden obligatorio.
6. Leer `08-SLICES-PLAN.md`.
7. Leer `slice-00-repository-foundation-guardrails.md`.
8. Clasificar archivos existentes:
   - reutilizar;
   - modificar por integración directa;
   - no tocar.
9. Confirmar que no existen secretos.
10. Verificar que las decisiones confirmadas de Python/package manager/frontend estén reflejadas de forma consistente en los documentos.

**Hito crítico:** antes de implementar, reflejar estas decisiones cerradas también en `AGENTS.md` para que diseño y reglas operativas no diverjan.

### Fase 2 — modelo de datos

1. No crear tablas funcionales.
2. Definir solo infraestructura de `peopleops-db` y `synthetic-hris-db`.
3. Verificar separación de credenciales.
4. Definir variables de entorno independientes.
5. Preparar, si corresponde, mecanismo de migrations sin crear entidades futuras.

**Hito crítico:** no existe ninguna migration de Slice 01/02.

### Fase 3 — lógica de negocio

No implementar lógica de negocio.

Implementar únicamente:

- config validation;
- health/liveness mínimo;
- guardrails de configuración.

**Hito crítico:** no existe semantic routing ni código HR.

### Fase 4 — endpoints / acciones backend

1. Crear health endpoint mínimo de PeopleOps API.
2. Crear health/liveness del Reference MCP Server según runtime confirmado.
3. Configurar CORS base si aplica.
4. No exponer análisis/review/policy endpoints todavía.

**Hito crítico:** PeopleOps API no puede acceder al HRIS.

### Fase 5 — frontend

1. Crear solo el deployable/directorio base.
2. No implementar UI.
3. Usar el scaffold confirmado de Next.js + TypeScript + pnpm + App Router.

**Hito crítico:** no adelantar Slice 14.

### Fase 6 — validaciones

1. Validar `.env.example`.
2. Validar `.gitignore`.
3. Validar Compose.
4. Validar health checks.
5. Validar separación de credenciales.
6. Validar CORS si corresponde.
7. Validar que no se introdujeron servicios extras.

### Fase 7 — pruebas

Ejecutar:

- smoke tests de servicios;
- configuration tests;
- health tests;
- secret/config guardrail tests;
- lint;
- test command reproducible;
- Docker Compose validation.

No se requieren tests de tablas porque este slice no crea persistencia funcional.

### Fase 8 — revisión final contra aceptación

Revisar:

- monorepo;
- deployables;
- Compose;
- ownership;
- no MCP bypass;
- no hardcoding;
- no schema HR prematuro;
- no frontend funcional;
- no servicios extra;
- documentación de comandos realmente probados.

---

## 8. Riesgos y puntos de control

### Riesgos principales

1. Elegir stack frontend sin documentación.
2. Elegir Poetry/uv/pip o versión Python por analogía con otro proyecto.
3. Introducir un único PostgreSQL credential con acceso a ambos ownerships.
4. Permitir a `peopleops-api` conectarse al Synthetic HRIS "solo para desarrollo".
5. Crear ORM compartido entre PeopleOps y HRIS.
6. Implementar MCP discovery anticipadamente.
7. Añadir LangGraph/OpenAI antes del Slice 06.
8. Añadir LlamaIndex/RAG antes de Slice 07.
9. Añadir Redis, LocalStack o Phoenix por copiar Enterprise RAG.
10. Copiar el Docker Compose completo de Enterprise RAG.
11. Crear un cuarto admin service.
12. Copiar un template frontend completo.
13. Agregar comandos/documentación que no hayan sido ejecutados.
14. Mezclar ports/database names hardcodeados sin confirmación.
15. Crear business migrations anticipadas.

### Errores que violarían la documentación

- `peopleops-api` contiene `SYNTHETIC_HRIS_DATABASE_URL`.
- `peopleops-api` importa models del HRIS.
- `reference-mcp-server` contiene `PEOPLEOPS_DATABASE_URL`.
- `peopleops-web` recibe credenciales DB.
- aparece SQL HRIS dentro de PeopleOps.
- se introduce keyword routing.
- existe fallback directo cuando MCP no está disponible.
- se crea Redis/LocalStack/Phoenix sin ADR/justificación.
- se crea frontend MCP.
- se agregan tablas HR en Slice 00.

### Señales de adelanto de slice

- `AnalysisInteraction` ya existe;
- Employee/Contract/Payroll migrations;
- LangGraph graph;
- OpenAI calls;
- LlamaIndex index;
- pgvector ingestion;
- MCP discovery;
- conceptual query translator;
- Human Review;
- dashboard/chat UI;
- evaluation cases funcionales.

### Decisiones cerradas antes de programar

1. Python 3.11 + Poetry.
2. FastAPI + Pydantic v2 + Pytest + Ruff + Alembic.
3. Next.js + TypeScript + pnpm + App Router.
4. Puertos: web 3000, API 8000, MCP 8001, PeopleOps DB 5436, Synthetic HRIS DB 5437.
5. Bases/users: `peopleops`/`peopleops_app` y `synthetic_hris`/`synthetic_hris_app`.
6. `Makefile` raíz como interfaz operativa canónica.
7. Health HTTP para ambos deployables backend.
8. CORS mediante `FRONTEND_URL`/`FRONTEND_URLS`, origen local `http://localhost:3000`.
9. Single-tenant por instancia.
10. Sin Redis, LocalStack ni Phoenix en Slice 00.

---

## 9. Checklist de aceptación

### Repositorio

- [ ] Monorepo creado y documentado.
- [ ] Existe `apps/peopleops-api/`.
- [ ] Existe `apps/peopleops-web/`.
- [ ] Existe `apps/reference-mcp-server/`.
- [ ] Existen áreas `packages/`, `synthetic-hris/`, `policies/`, `evaluation/` y `docs/` según necesidad del baseline.
- [ ] No existe cuarto deployable administrativo.

### Docker / infraestructura

- [ ] `docker-compose.yml` o equivalente versionado.
- [ ] Existe servicio `peopleops-api`.
- [ ] Existe servicio `peopleops-web`.
- [ ] Existe servicio `reference-mcp-server`.
- [ ] Existe servicio `peopleops-db`.
- [ ] Existe servicio `synthetic-hris-db`.
- [ ] `docker compose config` finaliza correctamente.
- [ ] Los servicios de DB tienen health check.
- [ ] Los deployables tienen health/liveness mínimo.
- [ ] No se agregó Redis.
- [ ] No se agregó LocalStack.
- [ ] No se agregó Phoenix.
- [ ] No se agregó cola/scheduler.

### Ownership y seguridad

- [ ] `peopleops-api` no posee credenciales del Synthetic HRIS.
- [ ] `reference-mcp-server` no posee credenciales de PeopleOps DB.
- [ ] `peopleops-web` no posee credenciales DB.
- [ ] No existe conexión directa PeopleOps → Synthetic HRIS.
- [ ] No existe fallback directo a HRIS.
- [ ] `.env.example` no contiene secretos reales.
- [ ] `.env`, `.secrets` y equivalentes están ignorados por Git.
- [ ] Repositorio sin datos reales de empleados/clientes.

### Anti-hardcoding

- [ ] No hay routing por keywords.
- [ ] No hay listas de frases por idioma.
- [ ] No hay functions creadas por wording.
- [ ] No se codificaron preguntas de evaluación como runtime logic.
- [ ] Guardrails están escritos en `AGENTS.md`.

### Datos

- [ ] Slice 00 no crea tablas funcionales.
- [ ] No existen migrations de Employee/Contract/Payroll.
- [ ] No existen migrations de Conversation/AnalysisInteraction.
- [ ] No existen FKs cross-database.
- [ ] Unicidad activa: no aplica.
- [ ] Estados/enums persistidos: no aplica.
- [ ] Integridad referencial funcional: no aplica porque no se crean tablas.
- [ ] Multi-tenancy: no implementado por falta de definición documental.
- [ ] Si algún test usa DB, usa PostgreSQL; no SQLite por conveniencia.

### Concurrencia

- [ ] No existen operaciones críticas de dominio que requieran transacciones/locks.
- [ ] No hay condiciones de carrera de datos de negocio introducidas por el slice.
- [ ] Separación de ownership/config impide accesos cruzados accidentales.

### Backend

- [ ] FastAPI base de `peopleops-api` arranca.
- [ ] Health endpoint de API funciona.
- [ ] Reference MCP Server base arranca según runtime confirmado.
- [ ] No existe MCP discovery funcional todavía.
- [ ] No existe LangGraph productivo.
- [ ] No existe RAG.
- [ ] No existen business endpoints.
- [ ] CORS está configurado si el API ya se expone para frontend desacoplado.
- [ ] Si CORS aplica, preflight fue verificado y no usa wildcard con credenciales.

### Frontend

- [ ] No se implementó frontend funcional.
- [ ] No se eligió template/framework no documentado.
- [ ] No se copiaron fake APIs, MSW, mocks ni páginas demo.
- [ ] Estrategia de refresco UI: no aplica en Slice 00.
- [ ] `NEXT_PUBLIC_API_BASE_URL` está definida en `.env.example` y disponible en `.env.local`.

### Servicios externos

- [ ] OpenAI no es invocado.
- [ ] LangSmith no es requerido.
- [ ] S3 no es integrado.
- [ ] No existen jobs de integración externa.
- [ ] La regla de resiliencia externa no aplica todavía.

### Calidad y pruebas

- [ ] Existe comando reproducible de lint.
- [ ] Existe comando reproducible de test.
- [ ] Smoke tests de arranque pasan.
- [ ] Tests de configuración inválida pasan.
- [ ] Verificación de `.env.example` sin secretos pasa.
- [ ] Verificación de no-acceso PeopleOps→HRIS pasa.
- [ ] Los comandos documentados fueron ejecutados realmente.
- [ ] No se afirma éxito de checks no ejecutados.

### Trigger points

- [ ] Build/start/test son manuales y documentados.
- [ ] Health checks son automáticos al levantar Compose.
- [ ] No existen cron/jobs/eventos de negocio.
- [ ] No hay autogeneración de datos.

### Scope

- [ ] Ningún cambio pertenece a Slice 01 o posterior.
- [ ] No hay refactors cosméticos no relacionados.
- [ ] No se añadieron dependencias especulativas.
- [ ] Definition of Done del slice está completamente en verde antes de marcarlo completo.

---

## 10. Entregable para Codex

### A. Guía de análisis y acompañamiento

Codex debe comenzar inspeccionando el repositorio real, no asumiendo que la estructura diseñada ya existe.

#### Orden de inspección

1. `git status`
2. rama actual y rama base
3. root del repositorio
4. `AGENTS.md`
5. `README.md`
6. `docs/`
7. `08-SLICES-PLAN.md`
8. especificación del Slice 00
9. cualquier `docker-compose*.yml`
10. `.env.example`
11. `.gitignore`
12. estructura `apps/`, `packages/`, `evaluation/`, `policies/`, `synthetic-hris/`
13. cualquier configuración/test preexistente

#### Qué implementar primero

1. resolver únicamente las confirmaciones bloqueantes;
2. crear estructura del monorepo;
3. separar configuración/credenciales;
4. crear Compose base;
5. crear scaffolds mínimos;
6. implementar health/liveness;
7. configurar test/lint;
8. agregar tests de arquitectura/configuración;
9. documentar únicamente comandos ya verificados.

#### Documentos a reconsultar

Durante implementación:

- antes de tocar estructura: `07-CTX.md` + ADR-009;
- antes de tocar DB/config: REQ-PHY-004 + ADR-006;
- antes de tocar acceso HRIS: ADR-001 + REQ-MCP-001/009;
- antes de agregar cualquier router/tool: REQ-SEM-001..005 + ADR-004;
- antes de agregar dependencia: `AGENTS.md` Dependency Discipline;
- antes de declarar terminado: Slice 00 Definition of Done.

#### Qué vigilar

- bypass MCP;
- leak de schema físico;
- credenciales cruzadas;
- secretos;
- dependencia no justificada;
- backend/frontend adelantados;
- migration de slice futuro;
- hardcoding semántico;
- nuevos servicios Docker no autorizados.

#### Preguntas que Codex debe formular solo ante ambigüedad real

- ¿Existe alguna contradicción real con el stack confirmado?
- ¿Qué runtime/transporte MCP funcional requiere un slice posterior?

No preguntar de nuevo cuestiones que ya estén resueltas en el repositorio real.

---

### B. Plan operativo para Codex

#### Rama

```text
codex/slice00
```

#### Archivos autorizados para cambio

La lista exacta debe ajustarse al repo real después de la inspección. Como máximo, Slice 00 puede crear/modificar archivos equivalentes a:

```text
AGENTS.md
README.md
.gitignore
.env.example
docker-compose.yml
apps/peopleops-api/**
apps/peopleops-web/**
apps/reference-mcp-server/**
packages/contracts/**
packages/shared/**
synthetic-hris/
policies/
evaluation/
ops/PLAN-slice00.md
docs/                  # solo docs directamente vinculados a foundation
tests/ o tests por app # solo foundation/health/config/guardrails
```

Cualquier archivo adicional:

**requiere confirmación**.

No están autorizados:

- migrations de Slice 01/02;
- LangGraph;
- RAG;
- payroll/HR domain code;
- frontend funcional;
- MCP discovery/query execution.

#### Estrategia de commits sugerida

Solo si el usuario solicita commits:

1. `chore(slice00): scaffold repository boundaries`
2. `chore(slice00): add docker and environment baseline`
3. `test(slice00): add foundation guardrail checks`
4. `docs(slice00): document verified development workflow`

No mezclar cambios de slices futuros.

#### Verificaciones mínimas

Usar únicamente comandos realmente soportados por el repo para el stack confirmado.

Como mínimo conceptualmente:

```text
git status
docker compose config
docker compose build
docker compose up -d
docker compose ps
health checks
lint
tests
git diff --check
git diff
secret/config scan
docker compose down
```

#### Validación de base de datos

Este slice no crea persistencia funcional.

Por tanto:

- no se requieren assertions de tablas de negocio;
- no se requieren seeders;
- no se crean Employee/AnalysisInteraction;
- no se usa SQLite;
- cualquier prueba de conectividad debe utilizar PostgreSQL;
- cualquier creación de BD/test debe ejecutarse solo después de comprobar conexión y variables correctas.

#### Validación backend/frontend

- `peopleops-web` solo conoce URL del API;
- no conoce MCP/DB;
- `peopleops-api` no conoce HRIS DB;
- `reference-mcp-server` no conoce PeopleOps DB;
- el frontend no implementa todavía flujo funcional;
- CORS, si se activa, usa origins explícitos.

#### Validación documental

Antes de PR, comparar diff contra:

- REQ-PHY-001..006;
- REQ-SEC-001..003;
- REQ-SEM-001..005;
- ADR-001;
- ADR-004;
- ADR-006;
- ADR-009;
- ADR-010;
- Slice 00 Definition of Done.

#### Git / PR

Rama:

```bash
git switch -c codex/slice00
```

Push, únicamente cuando el trabajo esté validado y el usuario haya autorizado esa acción:

```bash
git push --set-upstream origin codex/slice00
```

PR hacia la rama base real del repo, no asumir `main` sin verificar.

Título sugerido:

```text
Slice 00: Repository Foundation & Guardrails
```

Etiquetas sugeridas, solo si existen en el repo:

```text
architecture
infrastructure
slice-00
```

No crear PR hasta que la checklist esté en verde.

---

## Runbook

Guardar la versión ejecutable en:

```text
ops/PLAN-slice00.md
```

El runbook siguiente es deliberadamente conservador: usa únicamente el
stack confirmado y no adelanta comportamiento de slices posteriores.

```bash
# 1. Inspección inicial
git status
git branch --show-current
git remote -v
find . -maxdepth 3 -type f | sort | sed -n '1,240p'

# 2. Crear rama de trabajo solo si todavía no existe y la rama base es correcta.
git switch -c codex/slice00

# 3. Releer instrucciones y diseño antes de editar.
sed -n '1,260p' AGENTS.md
sed -n '1,220p' docs/08-SLICES-PLAN.md 2>/dev/null || true
find . -iname '*slice-00*' -o -iname '*slice00*'

# 4. Inspeccionar infraestructura existente.
find . -maxdepth 3 \( \
  -name 'docker-compose*.yml' -o \
  -name 'compose*.yml' -o \
  -name '.env.example' -o \
  -name '.gitignore' -o \
  -name 'pyproject.toml' -o \
  -name 'package.json' -o \
  -name 'Makefile' \
\) -print

# 5. Después de implementar el foundation con el stack CONFIRMADO:
docker compose config
docker compose build
docker compose up -d
docker compose ps

# 6. Ejecutar health checks con las URLs/commands realmente confirmadas
# en el repositorio. No inventar puertos.

# 7. Ejecutar lint/tests usando los comandos canónicos que queden
# documentados para el stack confirmado.
# <canonical-lint-command>
# <canonical-test-command>

# 8. Verificar alcance y calidad.
git status
git diff --check
git diff --stat
git diff

# 9. Verificar que no aparecieron credenciales o rutas HRIS en peopleops-api.
grep -RniE 'SYNTHETIC_HRIS|HRIS_DATABASE|password|secret|token' \
  apps/peopleops-api .env.example 2>/dev/null || true

# 10. Verificar que reference-mcp-server no tenga credenciales PeopleOps DB.
grep -RniE 'PEOPLEOPS_DATABASE|password|secret|token' \
  apps/reference-mcp-server .env.example 2>/dev/null || true

# 11. Verificar que no se adelantaron slices.
grep -RniE 'AnalysisInteraction|EmployeePayroll|LangGraph|LlamaIndex|HumanReview' \
  apps packages synthetic-hris 2>/dev/null || true

# 12. Detener entorno.
docker compose down

# 13. Solo si la checklist está totalmente en verde Y existe autorización:
# git add <archivos-autorizados>
# git commit -m "chore(slice00): scaffold repository foundation"
# git push --set-upstream origin codex/slice00

# 14. Solo con checklist verde, autorización y rama base real verificada:
# gh pr create \
#   --base <rama-base-real> \
#   --head codex/slice00 \
#   --title "Slice 00: Repository Foundation & Guardrails" \
#   --body-file ops/PLAN-slice00.md
```
