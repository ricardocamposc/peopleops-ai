# Slice 17 — Security & Failure Hardening

**Estado:** Especificación de slice  
**Objetivo:** Endurecer la solución frente a permisos, datos sensibles, fallos de red/modelo/MCP, prompt injection documental y errores de workflow.  
**Dependencias:** Slice 16.

## 1. Requisitos trazados

- REQ-SEC-001..009
- REQ-MCP-006..009
- REQ-AGT-005
- REQ-AUD-007

## 2. Alcance

- Revisar least privilege por servicio.
- Controlar acceso a payroll.
- Propagar scopes al MCP Server.
- Validar uploads y tratar documentos como untrusted.
- Aplicar defensa contra prompt injection en Policy RAG.
- Revisar logs/redaction.
- Configurar timeouts/retries/circuit behavior razonable.
- Normalizar errores de modelo, MCP, RAG y DB.
- Agregar tests de fallos y security regression.

## 3. Fuera de alcance

- Certificaciones enterprise.
- SSO productivo completo.
- Regulación específica de un país.
- Pentest formal.

## 4. Diseño descriptivo esperado

- Security no depende del prompt.
- PeopleOps API no recibe credenciales HRIS.
- Reference MCP usa credenciales read-only.
- Payroll scope debe verificarse en backend y MCP cuando corresponda.
- Errores al auditar no deben filtrar datos ni causar cascadas.

## 5. Pruebas mínimas

- Unauthorized payroll.
- Prompt injection en policy.
- MCP timeout.
- MCP unavailable.
- OpenAI timeout/error.
- Malformed conceptual query.
- DB timeout.
- Logging redaction.
- Secrets scan.

## 6. Impacto en evaluación

- Agregar tasa de recovery/failure classification.
- Ejecutar negative evaluation suite completa.

## 7. Definition of Done

- Security checklist aprobado.
- Fallos principales cubiertos por tests.
- No secrets.
- Safe errors/logs.
- Retries limitados.
- Negative regression estable.

## 8. Guardrails y riesgos

- No afirmar production-ready.
- No implementar regulación específica sin contexto real.
- No usar prompt-only security.
- No degradar silenciosamente a respuestas sin evidencia.
