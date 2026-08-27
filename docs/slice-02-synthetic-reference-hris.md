# Slice 02 — Synthetic Reference HRIS

**Estado:** Especificación de slice  
**Objetivo:** Construir un HRIS sintético coherente que sirva de fuente controlada, demo y ground truth sin convertirse en contrato de PeopleOps.  
**Dependencias:** Slice 00.

## 1. Requisitos trazados

- REQ-HR-001..007
- REQ-PAY-001..007
- REQ-SEC-001
- REQ-PHY-004

## 2. Alcance

- Crear base/migraciones del Synthetic Reference HRIS.
- Implementar Employee, Department, Position, Contract, Attendance, Overtime, Vacation, Leave, PayrollPeriod, EmployeePayroll, PayrollConcept y PayrollItem.
- Crear seeds deterministas con escenarios deliberados.
- Incluir ground truth para contratos, vacaciones, asistencia, payroll y discrepancias overtime↔payroll.
- Separar físicamente/lógicamente credenciales respecto de PeopleOps DB.
- Documentar que el schema es fixture de referencia.

## 3. Fuera de alcance

- Acceso directo desde PeopleOps.
- MCP discovery.
- Policy documents.
- Schema alternativo de independence test.
- Datos reales de clientes.

## 4. Diseño descriptivo esperado

- Los datos deben contar historias coherentes, no ser ruido aleatorio.
- Debe existir al menos un caso por escenario insignia estructurado.
- Payroll debe permitir comparar períodos y conceptos.
- Attendance/overtime debe permitir reconciliación con payroll.
- IDs/códigos deben ser sintéticos y reproducibles.

## 5. Pruebas mínimas

- Migraciones desde cero.
- Seed determinista.
- Tests de integridad referencial.
- Tests de ground truth conocido.
- Checks de coherencia: gross/deductions/net, fechas contractuales, balances de vacaciones, overtime.

## 6. Impacto en evaluación

- Crea el ground truth estructurado para evaluation posterior.
- Debe producir expected facts verificables sin LLM.

## 7. Definition of Done

- DB sintética reproducible.
- Seeds versionados.
- Ground truth documentado.
- Escenarios insignia presentes.
- PeopleOps API sigue sin credenciales a esta DB.

## 8. Guardrails y riesgos

- No ajustar el schema para facilitar una pregunta concreta.
- No codificar semántica de negocio en nombres que luego PeopleOps requiera.
- No mezclar tablas de auditoría PeopleOps con HRIS.
- No usar PII real.
