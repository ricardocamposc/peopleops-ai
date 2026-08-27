Necesito que diseñes la implementación del siguiente slice del proyecto:

## Slice a diseñar
{{SLICE}}

## Qué necesito de ti

Diseña la implementación completa del slice elegido y organiza la respuesta en este formato exacto:

### 1. Objetivo del slice
- Explica qué resuelve este slice
- Explica qué procesos cubre y cuáles NO cubre
- Indica explícitamente qué queda fuera para no adelantar slices futuros

### 2. Documentos que gobiernan este slice
- Lista los documentos más relevantes para este slice
- Para cada uno, explica brevemente qué decisión o restricción aporta

### 3. Impacto funcional
- Describe el flujo operativo del usuario
- Describe entradas, salidas y estados esperados
- Lista reglas de negocio obligatorias
- Lista validaciones obligatorias
- Señala ambigüedades o vacíos documentales
- Si algo no está documentado, dilo explícitamente y no lo inventes
 - Declara disparadores/trigger points de eventos del slice (por ejemplo, cuándo se crean entidades derivadas: al confirmar una acción, al cerrar un ciclo, por comando manual, cron, etc.). Si no está definido, márcalo como "requiere confirmación" y propone un fallback operativo seguro (acción/command manual).
 - Explica la estrategia de concurrencia y bloqueo para operaciones críticas (transacciones, locks, reintentos, orden de actualización) para evitar condiciones de carrera.
 - Indica dependencias/sincronizaciones con otros procesos (qué debe estar confirmado/cerrado antes de avanzar).

### 4. Diseño de datos
- Indica qué tablas nuevas serían necesarias, si aplica
- Indica qué columnas, relaciones, enums o constraints serían necesarias
- Diferencia claramente:
  - cambios obligatorios
  - cambios opcionales
  - cambios no permitidos por falta de soporte documental
- Explica la trazabilidad con procesos anteriores
- Explica cómo evitar romper slices ya implementados
 - Define claves e índices compuestos necesarios (incluida "unicidad activa" cuando aplique, por ejemplo, una única asignación activa por entidad/posición), y cómo se materializa: constraint/índice + validación de aplicación.
 - Especifica la política de integridad referencial (FKs, ON DELETE/UPDATE) y justifica valores (RESTRICT/SET NULL/CASCADE) según el proceso.
 - Declara el formato de enums/estados persistidos (string con casts Eloquent o enum/tinyint), y lista valores exactos a usar de forma consistente.
 - Si hay autogeneración de datos derivados (p. ej., posiciones, folios, códigos): define si corresponde en este slice; si no, indícalo como "requiere confirmación" y propone una alternativa manual.

### 5. Diseño backend Laravel
- Propón los componentes backend a implementar o modificar:
  - migrations
  - models
  - relationships
  - form requests / validation
  - controllers
  - services/actions
  - policies si aplica
  - routes
- Para cada componente, indica su responsabilidad exacta
 - Declara explícitamente la estrategia de transacciones/locking en services/actions para operaciones que deban ser atómicas.
 - Especifica el formato y casts de estados/enums en los modelos (y valida coherencia con la base de datos).
 - Si hay eventos/commands programáticos (jobs, listeners), indícalos y ubícalos (nombres y responsabilidades).

### 6. Diseño frontend
- Explica qué pantallas, formularios, vistas o componentes hacen falta
- Indica qué acciones podrá hacer el usuario
- Indica qué datos debe ver
- Indica validaciones de UI
- Explica qué debe mantenerse consistente con el sistema existente
- Antes de definir la interfaz, consulta y reutiliza cuando corresponda la guía de referencia de Vuexy Full en `vuexy-full-template/docs/GUIA-USO-COMPONENTES.md` y la plantilla completa en `vuexy-full-template/`, considerando explícitamente sus patrones responsive y su adaptación a mobile.
- Antes de crear un componente visual nuevo, verifica primero si existe un equivalente en `vuexy-full-template/`; si existe, reutilízalo. Si no existe, márcalo como `requiere confirmación` antes de inventarlo.
- Los errores devueltos por el backend en acciones de guardar/actualizar/eliminar deben mostrarse en un snackbar reutilizando `VSnackbar` o un patrón ya validado en `vuexy-full-template/`.
 - Define la estrategia de actualización "casi tiempo real" si aplica (polling con intervalo sugerido por defecto; WebSocket/SSE sólo si está documentado o aprobado) y el manejo de estados de carga/errores.
 - Indica qué componentes/estilos/patrones existentes deben reutilizarse según el repositorio.

### 7. Secuencia de implementación recomendada
Quiero un orden de ejecución detallado, por fases:
1. análisis de código existente
2. modelo de datos
3. lógica de negocio
4. endpoints / acciones backend
5. frontend
6. validaciones
7. pruebas
8. revisión final contra aceptación del slice
 - Dentro de cada fase, señala hitos críticos (por ejemplo, definir índices/constraints antes de lógica; instrumentar transacciones/locks antes de exponer endpoints; confirmar triggers antes de automatizar).

### 8. Riesgos y puntos de control
- Lista riesgos de implementación
- Lista errores comunes que podrían violar la documentación
- Lista señales de que alguien se está adelantando a otro slice
- Lista decisiones que deben confirmarse antes de programar

### 9. Checklist de aceptación
- Dame una checklist clara y verificable
- Debe cubrir modelo de datos, reglas de negocio, flujo UI/API, validaciones y trazabilidad
- No marques el slice como completo si solo hay migraciones o backend parcial
 - Concurrencia: operaciones críticas protegidas con transacciones/locks; sin condiciones de carrera conocidas.
 - Estados/enums persistidos con formato consistente y valores documentados.
 - Unicidad activa garantizada (constraint/índice + validación) donde aplique.
 - Política de integridad referencial definida (FKs, ON DELETE/UPDATE) y comprobada.
 - Estrategia de refresco UI definida y operativa (polling o alternativa aprobada).
 - Disparadores/trigger points documentados o fallback manual claro si requieren confirmación.
 - Si el slice modifica persistencia, las pruebas deben ejecutarse sobre entorno de test con migraciones/seeders correspondientes y validar la base de datos con aserciones como `assertDatabaseHas` / `assertDatabaseMissing` o equivalentes.
 - Si el slice no toca base de datos, deja explícito que esa regla no aplica.

### 10. Entregable para Codex

#### A. Guía para Codex (análisis y acompañamiento)
Redacta instrucciones para que Codex revise el repo real y me acompañe. Debe incluir:
- qué carpetas y archivos inspeccionar primero
- qué implementar o modificar primero
- qué referencia visual consultar antes de diseñar frontend (`vuexy-full-template/docs/GUIA-USO-COMPONENTES.md` y `vuexy-full-template/`), incluyendo sus patrones responsive y mobile
- qué documentos volver a consultar durante la implementación
- qué debe vigilar para no romper slices previos
- qué preguntas debería hacer si detecta ambigüedad real

#### B. Plan operativo para Codex CLI (Ubuntu)
Redacta un plan que Codex CLI pueda ejecutar en el entorno real del proyecto. Debe incluir:
- secuencia de trabajo concreta
- tipos de archivos a crear o editar
- verificaciones a correr
- cómo validar que el slice no se salió de alcance
- cómo comprobar que backend y frontend quedaron consistentes
- cómo revisar que se respetó la documentación
- flujo Git completo (rama, commits, push y PR):
  - nombre de rama con este patrón: `codex/{{slice-slug}}`
  - estrategia de commits (mensajes claros por fase)
  - comandos `git` necesarios
  - comandos `gh` para crear PR (título, cuerpo y etiquetas sugeridas)
  - condición de apertura de PR: solo cuando checklist de aceptación esté en verde

Formato de ejecución del plan:
- incluye un bloque final de `Runbook` con los comandos `bash` en bloques de código para ejecución secuencial
- sugiere guardar el runbook en la carpeta "codex" de google drive  `ops/PLAN-{{slice-slug}}.md`
