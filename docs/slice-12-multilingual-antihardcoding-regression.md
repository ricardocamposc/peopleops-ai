# Slice 12 — Multilingual & Anti-Hardcoding Regression

**Estado:** Especificación de slice  
**Objetivo:** Demostrar empíricamente que la arquitectura resuelve variaciones lingüísticas y nuevas formulaciones sin reglas por strings ni nuevas functions.  
**Dependencias:** Slices 06, 09 y 11.

## 1. Requisitos trazados

- REQ-PROD-002..003
- REQ-SEM-001..004
- REQ-EVAL-002
- REQ-EVAL-009

## 2. Alcance

- Ampliar dataset con equivalentes en español, inglés y portugués.
- Agregar paráfrasis deliberadamente diferentes.
- Incluir consultas cross-domain y payroll.
- Crear checks de repositorio para detectar patrones de keyword routing cuando sea viable.
- Comparar consistency de semantic request, plan y resultados.
- Documentar excepciones legítimas: enums, aliases técnicos, metadata semántica.

## 3. Fuera de alcance

- Traducción UI completa.
- Localización del producto.
- Nuevas capabilities.

## 4. Diseño descriptivo esperado

- Mismo significado debe producir comportamiento equivalente aunque cambie wording.
- No exigir intent label idéntico si el resultado funcional correcto se conserva.
- Los synonyms pueden existir como metadata de negocio del servidor, no como árbol de routing del cliente.

## 5. Pruebas mínimas

- Casos ES/EN/PT equivalentes.
- Paráfrasis sin keywords originales.
- Typo moderado si es razonable.
- Cross-domain.
- Policy-aware.
- Payroll.
- Scan/review de anti-patterns.

## 6. Impacto en evaluación

- Medir multilingual consistency y semantic correctness.
- Registrar regressions por idioma.

## 7. Definition of Done

- Dataset multilingüe ejecutable.
- Resultados funcionalmente equivalentes en casos objetivo.
- No se agregaron reglas lingüísticas para hacer pasar tests.
- Anti-hardcoding checklist aprobado.

## 8. Guardrails y riesgos

- No optimizar prompts con listas de frases del dataset.
- No crear language-specific routers.
- No confundir metadata synonyms con routing.
