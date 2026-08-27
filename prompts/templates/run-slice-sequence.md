# Prompt maestro para ejecutar la secuencia completa de un slice

Usa la rama por defecto del repositorio `ricardocamposc/mcmes` en GitHub.

Parámetro de entrada único:
- `SLICE={{SLICE}}`

Deriva automáticamente:
- `slice-slug=slice{{SLICE}}`

Objetivo general:
Ejecutar la secuencia completa del slice `{{SLICE}}` en una sola operación, respetando estrictamente este orden:

1. generar `prompts/design-slice-{{SLICE}}.md`
2. generar `prompts/handoff-to-codex-slice-{{SLICE}}.md`
3. ejecutar `prompts/handoff-to-codex-slice-{{SLICE}}.md`
4. generar como resultado de la fase 3:
   - `prompts/handoff-to-codex-slice-{{SLICE}}-responde.md`
   - `prompts/prompt-codex-cli-slice-{{SLICE}}.md`
   - `ops/PLAN-slice{{SLICE}}.md`
5. ejecutar `prompts/prompt-codex-cli-slice-{{SLICE}}.md` siguiendo el runbook `ops/PLAN-slice{{SLICE}}.md` para implementar el slice en este repositorio
6. validar la implementación completa contra `prompts/design-slice-{{SLICE}}.md`
7. corregir con cambios mínimos todo desvío respecto al diseño validado
8. volver a validar hasta que la implementación quede conforme o exista un bloqueo documentado
9. cerrar el slice en la documentación operativa correspondiente

## Validación previa obligatoria

Primero verifica que existan estos archivos base:
- `prompts/templates/design-slice-template.md`
- `prompts/templates/handoff-to-codex.md`

Si alguno no existe, cancela toda la operación y no hagas nada.

Además:
- si durante cualquier fase falta algún archivo requerido por la plantilla o por el prompt generado en la fase anterior, cancela toda la operación y no hagas nada más
- si cancelas, indícalo claramente y especifica qué archivo faltó

## Fase 1. Generar diseño del slice

1. Usa la plantilla `prompts/templates/design-slice-template.md`
2. Reemplaza:
   - `SLICE={{SLICE}}`
   - `slice-slug=slice{{SLICE}}`
3. Consulta y usa únicamente los documentos fuente mencionados en la plantilla
4. Ejecuta la plantilla resuelta
5. Genera el archivo:
   - `prompts/design-slice-{{SLICE}}.md`
6. La salida debe estar en formato markdown puro

## Fase 2. Generar handoff a Codex

1. Verifica que exista:
   - `prompts/design-slice-{{SLICE}}.md`
2. Si no existe, cancela toda la operación y no hagas nada
3. Usa la plantilla `prompts/templates/handoff-to-codex.md`
4. Reemplaza:
   - `SLICE={{SLICE}}`
   - `slice-slug=slice{{SLICE}}`
   - `CHATGPT_SLICE_DESIGN` con el contenido completo de `prompts/design-slice-{{SLICE}}.md`
5. Genera el archivo:
   - `prompts/handoff-to-codex-slice-{{SLICE}}.md`

## Fase 3. Ejecutar handoff a Codex

1. Verifica que exista:
   - `prompts/handoff-to-codex-slice-{{SLICE}}.md`
2. Si no existe, cancela toda la operación y no hagas nada
3. Ejecuta `prompts/handoff-to-codex-slice-{{SLICE}}.md` siguiendo todas sus instrucciones
4. Como resultado final, deben generarse exactamente estos 3 archivos:
   - `prompts/handoff-to-codex-slice-{{SLICE}}-responde.md`
   - `prompts/prompt-codex-cli-slice-{{SLICE}}.md`
   - `ops/PLAN-slice{{SLICE}}.md`

## Fase 4. Ejecutar prompt Codex CLI del slice

1. Verifica que existan:
   - `prompts/prompt-codex-cli-slice-{{SLICE}}.md`
   - `ops/PLAN-slice{{SLICE}}.md`
2. Si falta alguno, cancela toda la operación y no hagas nada
3. Ejecuta el prompt contenido en `prompts/prompt-codex-cli-slice-{{SLICE}}.md`
4. Sigue también el runbook `ops/PLAN-slice{{SLICE}}.md`
5. Implementa todo en este repo, validando con los comandos indicados
6. No te salgas del alcance del slice

## Fase 5. Validar contra el diseño

1. Verifica que exista:
   - `prompts/design-slice-{{SLICE}}.md`
2. Si no existe, cancela toda la operación y no hagas nada
3. Usa `prompts/design-slice-{{SLICE}}.md` como fuente de verdad para validar la implementación
4. Revisa que la implementación cumpla:
   - alcance
   - modelo de datos
   - backend
   - frontend
   - validaciones
   - permisos
   - auditoría
   - pruebas
   - documentación
5. Registra explícitamente cualquier desviación, vacío o ambigüedad que impida declarar el slice conforme

## Fase 6. Corregir y revalidar

1. Si la validación detecta desvíos, corrige únicamente lo mínimo necesario para alinear la implementación con `prompts/design-slice-{{SLICE}}.md`
2. No amplíes el alcance del slice para resolver un desvío
3. No cambies decisiones documentadas sin autorización explícita
4. Repite la validación de la fase 5 después de cada corrección
5. Si la corrección queda bloqueada por una dependencia o vacío documental, detén la operación y reporta el bloqueo

## Fase 7. Cierre del slice

1. Cuando la implementación quede conforme, actualiza la documentación operativa de cierre si corresponde
2. Deja trazabilidad clara de:
   - archivos modificados
   - pruebas ejecutadas
   - validación realizada contra `prompts/design-slice-{{SLICE}}.md`
   - correcciones aplicadas
3. Si el flujo requiere pausa por validación humana, detente aquí y espera la confirmación del usuario antes de continuar con otro slice

## Reglas de salida

Antes de guardar archivos en el repositorio:
- dame opción para descargar directamente desde este chat todos los archivos generados en la secuencia

Archivos que debes dejar disponibles para descarga:
- `prompts/design-slice-{{SLICE}}.md`
- `prompts/handoff-to-codex-slice-{{SLICE}}.md`
- `prompts/handoff-to-codex-slice-{{SLICE}}-responde.md`
- `prompts/prompt-codex-cli-slice-{{SLICE}}.md`
- `ops/PLAN-slice{{SLICE}}.md`

Después de eso, guarda los archivos en estas rutas exactas del repositorio:
- `prompts/design-slice-{{SLICE}}.md`
- `prompts/handoff-to-codex-slice-{{SLICE}}.md`
- `prompts/handoff-to-codex-slice-{{SLICE}}-responde.md`
- `prompts/prompt-codex-cli-slice-{{SLICE}}.md`
- `ops/PLAN-slice{{SLICE}}.md`

## Reglas estrictas

- no uses otra rama
- no cambies nombres ni rutas de salida
- no inventes archivos adicionales
- no inventes documentos fuente fuera de los exigidos por cada plantilla
- no alteres el contenido de las plantillas salvo los reemplazos indicados y la ejecución normal de sus instrucciones
- mantén el orden exacto de las cuatro fases
- si una fase falla, no continúes con la siguiente
- si cancelas, indícalo claramente
- minimiza accesos repetidos al repositorio dentro de la misma ejecución
- reutiliza en memoria los contenidos ya leídos durante la secuencia
- no releas un archivo ya obtenido en la misma ejecución salvo que sea estrictamente necesario
