{{CHATGPT_SLICE_DESIGN}}

# Tareas a ejecutar

En la  sección inicial se encuentra el diseño de implementación del slice {{SLICE}}, quiero que lo conviertas en una guía de ejecución real sobre este repositorio para Codex CLI, espetando estrictamente la documentación del proyecto y el alcance del slice {{SLICE}}.

## Lo que debes hacer:

1. Contrasta el diseño con el código real del repositorio.
2. Indica qué partes del diseño ya están implementadas y cuáles faltan.
3. Detecta inconsistencias entre el diseño y la estructura real del proyecto.
4. Ajusta el plan para que encaje con las convenciones existentes del repo.
5. Tradúcelo a un plan operativo ejecutable para Codex CLI en Ubuntu.
6. No inventes comportamiento ni modelo de datos fuera de la documentación.
7. No adelantes slices futuros.
8. El resultado final debe ser un prompt en forma de guía de ejecución para Codex CLI que considere el diseño de la implementación propuesto.
9. Si el slice modifica persistencia, el prompt final debe exigir entorno de test, migraciones/seeders cuando correspondan y validaciones reales sobre base de datos; si no toca BD, indícalo explícitamente.

## Tu respuesta debe ser entregada considerando lo siguiente:

### 1. Alcance confirmado del slice
- Qué sí entra
- Qué no entra
- Riesgos de adelantar otros slices

### 2. Contraste con el repo real
- Qué ya existe en el código relacionado con este slice
- Qué piezas reutilizables existen
- Qué falta implementar
- Qué archivos o módulos son el punto de entrada más probable
- Si el slice toca frontend o interfaz, revisar primero `vuexy-full-template/docs/GUIA-USO-COMPONENTES.md` y la plantilla completa en `vuexy-full-template/` antes de definir componentes o layout, prestando atención a su comportamiento responsive y adaptación a mobile.

### 3. Ajustes al diseño original
- Qué partes del diseño deben mantenerse igual
- Qué partes deben adaptarse a la realidad del repo
- Qué puntos requieren confirmación antes de tocar código

### 4. Plan de trabajo para Codex
- Orden recomendado de inspección
- Orden recomendado de implementación
- Documentos que deben reconsultarse en cada fase
- Riesgos que deben vigilarse durante los cambios

### 5. Instrucciones para la creación del Prompt para Codex CLI del bloque final
El `Prompt para Codex CLI` debe construirse a partir del contenido del diseño (sección inicial de este documento) e incluir, sin resumir, las siguientes secciones alineadas con la plantilla de diseño (`design-slice-template.md`):

- Objetivo del slice (1): qué resuelve, qué cubre y qué queda fuera.
- Documentos que gobiernan (2): lista de docs REQ/ADR/DATA/PROC/SLICE relevantes y su aporte.
- Impacto funcional (3): flujo operativo, entradas, salidas, estados, reglas de negocio, validaciones obligatorias y ambigüedades explícitas.
- Diseño de datos (4):
  - tablas nuevas/cambiadas con columnas mínimas, PK/FK, índices y unicidades;
  - relaciones y enums/estados;
  - cambios obligatorios, opcionales y no permitidos;
  - trazabilidad con procesos previos y cómo evitar romper slices ya implementados.
- Diseño backend Laravel (5): migrations, models, relationships, form requests, controllers, services/actions, policies (si aplica) y routes, con responsabilidades claras.
- Diseño frontend (6): pantallas/formularios/componentes, acciones del usuario, datos a mostrar, validaciones de UI y consistencia con el sistema existente; además debe indicar que se consultó la guía `vuexy-full-template/docs/GUIA-USO-COMPONENTES.md` y la referencia completa en `vuexy-full-template/` cuando aplique UI, incluyendo sus patrones responsive y mobile.
- Secuencia de implementación recomendada (7): fases 1→8 tal como en el diseño.
- Riesgos y puntos de control (8): riesgos, errores comunes, señales de adelanto de slice y decisiones a confirmar.
- Checklist de aceptación (9): completo (modelo de datos, reglas, flujo UI/API, validaciones, trazabilidad y criterios de completitud).
- Pruebas sobre persistencia: si el slice toca BD, exigir `RefreshDatabase` o equivalente, migraciones/seeders de test y aserciones sobre la base de datos; si no toca BD, declararlo explícitamente.
- Guardrails de “no hacer”: explícitos para evitar adelantar slices o introducir entidades/logic no documentadas.

Además, el prompt debe incluir:
- Tipos de archivos a crear/editar (migraciones, modelos, requests, controllers, services/actions, rutas, vistas/componentes, tests).
- Validaciones y verificaciones a ejecutar (`php artisan route:list`, `php artisan migrate --pretend`, `php artisan test`, linters si aplica).
- Cómo comprobar consistencia backend/frontend y no romper slices previos.
- Flujo Git/PR:
  - Rama: `codex/{{slice-slug}}`
  - Mensajes de commit claros por fase
  - `git push --set-upstream origin codex/{{slice-slug}}`
  - PR con `gh pr create` (título, cuerpo, etiquetas) hacia la rama base real del repo
  - Solo abrir PR si checklist de aceptación está en verde

Consideraciones operativas transversales (aplican a cualquier slice y deben quedar explícitas en el prompt):
- Disparadores/trigger points: cuándo se ejecutan acciones derivadas (al confirmar/cerrar/cron/command). Si no está definido en el diseño, márcalo como “requiere confirmación” y propone un fallback manual seguro (acción/command idempotente).
- Concurrencia y locking: envolver operaciones críticas en transacciones; definir qué registros se bloquean (y con qué orden) para evitar condiciones de carrera; opcionalmente reintentos/backoff si aplica al dominio.
- Estados/enums: fijar el formato de persistencia (string/enum/tinyint) y los valores canónicos a usar de forma consistente (DB + casts Eloquent + validaciones).
- Unicidad activa: cuando se permita sólo un registro “activo” por ámbito, especificar cómo se garantiza (constraint/índice compuesto si es viable y validación de aplicación cuando no lo sea), y la semántica de “activo”.
- Autogeneración de datos: declarar qué entidades/atributos se autogeneran (códigos, posiciones, secuencias) y en qué fase. Si es incierto, indícalo como “requiere confirmación” y usa vía manual por defecto.
- UI casi tiempo real: elegir estrategia por defecto de polling (intervalo sugerido) y reservar WebSocket/SSE sólo cuando el diseño lo documente o esté aprobado; indicar estados de carga/errores.
- Reuso de patrones del repo: indicar qué componentes/estilos/utilidades existentes deben reutilizarse para no introducir patrones ad hoc; para frontend Vuexy, usar como referencia obligatoria `vuexy-full-template/docs/GUIA-USO-COMPONENTES.md` y `vuexy-full-template/`, incluyendo patrones responsive y mobile.
- Integridad referencial: detallar FKs y reglas ON DELETE/UPDATE consistentes con el proceso (RESTRICT/SET NULL/CASCADE) y justificarlas según el diseño.
- Alcance de archivos y edición mínima:
  - Codex CLI sólo debe crear o modificar archivos estrictamente necesarios para implementar el slice actual.
  - No debe editar archivos no relacionados con el slice, aunque detecte oportunidades de mejora.
  - No debe reformatear, reindentar, reordenar imports, normalizar espacios, traducir textos, cambiar comillas ni aplicar cambios cosméticos en archivos fuera del alcance directo.
  - Si un archivo existente requiere modificación, el cambio debe ser mínimo, localizado y justificado por una necesidad explícita del slice.
  - Si durante la implementación detecta problemas ajenos al slice, debe reportarlos como observaciones y no corregirlos en la misma ejecución.
  - Debe evitar cambios masivos en archivos compartidos, plantillas globales, componentes base, estilos globales, configuración general o documentación no vinculada al slice, salvo que el diseño del slice los exija de forma directa.
  - Antes de proponer un archivo a modificar, debe clasificarlo como: crear, modificar por integración directa, o no tocar.
  - En el plan y en el prompt final debe incluir una sección llamada `Archivos autorizados para cambio`, listando únicamente los archivos nuevos y los archivos existentes estrictamente necesarios para el slice.
  - Cualquier archivo no listado en `Archivos autorizados para cambio` debe considerarse fuera de alcance.
  - Si para completar el slice cree que necesita tocar un archivo adicional no previsto, debe marcarlo como `requiere confirmación` antes de incorporarlo al plan final.

### 6. Bloque final
Quiero que cierres con un bloque llamado `Prompt para Codex CLI` que yo pueda copiar y pegar en Codex CLI para ejecutar el trabajo.
Ese bloque debe terminar con un `Runbook` en Markdown (bloques ```bash) para guardarlo en `ops/PLAN-{{slice-slug}}.md` y ejecutarlo con `ops/run-runbook.sh`.

## Reglas
- Responde en español
- No escribas código todavía, salvo comandos si son realmente necesarios para inspección
- Si detectas ambigüedad documental, márcala como "requiere confirmación"
- Sé concreto y orientado a ejecución
- No autorices cambios fuera del alcance del slice
- No permitas refactors cosméticos o masivos no requeridos por el slice
