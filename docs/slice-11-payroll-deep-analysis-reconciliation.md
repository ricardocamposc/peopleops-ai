# Slice 11 — Payroll Deep Analysis & Reconciliation

**Estado:** Especificación de slice  
**Objetivo:** Profundizar payroll a nivel individual y demostrar explicación de variaciones y reconciliación Attendance/Overtime ↔ Payroll.  
**Dependencias:** Slices 06 y 09.

## 1. Requisitos trazados

- REQ-PAY-001..007
- REQ-HR-003..004
- REQ-SEC-005

## 2. Alcance

- Implementar consultas conceptuales necesarias para payroll individual/período.
- Comparar período actual vs anterior.
- Desglosar variaciones por PayrollConcept.
- Relacionar overtime registrado con overtime pagado.
- Relacionar leave/absence si el modelo lo soporta.
- Agregar análisis agregado por department/cost center.
- Utilizar policy procedure solo cuando corresponda.
- Tratar payroll como capability sensible.

## 3. Fuera de alcance

- Edición de payroll.
- Decisiones disciplinarias.
- Accounting/ERP analytics general.
- Reglas laborales legales no documentadas.

## 4. Diseño descriptivo esperado

- Los cálculos de diferencias deben ser determinísticos.
- El LLM explica resultados, no redefine totales.
- El caso `overtime no pagado` debe resolverse por query conceptual dinámica, no tool específica.
- Autorización/scope debe aplicarse antes de exponer datos individuales.

## 5. Pruebas mínimas

- Payroll por empleado.
- Comparación de períodos.
- Variación por concepto.
- Overtime matching.
- Overtime discrepancy.
- Análisis agregado.
- Unauthorized payroll query.

## 6. Impacto en evaluación

- Agregar expected calculations, expected facts y discrepancy cases.
- Medir cálculo correcto y unsupported quantitative claims.

## 7. Definition of Done

- Scenario Payroll Explanation aprobado.
- Scenario Attendance↔Payroll aprobado.
- Cálculos deterministas testeados.
- Scope sensible aplicado.
- Sin función específica por wording.

## 8. Guardrails y riesgos

- No usar LLM para sumar/calcular cuando puede hacerse determinísticamente.
- No exponer payroll individual sin scope.
- No expandir a People Analytics/performance.
