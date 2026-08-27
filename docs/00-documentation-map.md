# PeopleOps AI — Documentation Map

**Estado:** Baseline técnico pre-implementación  
**Objetivo:** Punto de entrada obligatorio para Codex.

## Fuentes de verdad
Leer primero:
1. `proyecto-03-peopleops-ai-BRD.md`
2. `proyecto-03-peopleops-ai-PDD.md`
3. `proyecto-03-peopleops-ai-PRD.md`

Luego:
1. `01-SPEC.md`
2. `02-REQ.md`
3. `03-ADR.md`
4. `04-PROC.md`
5. `05-DATA.md`
6. `06-UI.md`
7. `07-CTX.md`
8. `08-SLICES-PLAN.md`

## Precedencia
BRD → PDD → PRD → SPEC → REQ → ADR/PROC/DATA/UI → CTX → SLICES.

Un documento inferior no puede reducir un requisito obligatorio de uno superior.

## Principios no negociables
1. No semantic hardcoding: sin keywords, listas de frases por idioma ni una función por wording.
2. MCP es obligatorio: `PeopleOps API → MCP Client → Reference MCP Server → Synthetic Reference HRIS`.
3. PeopleOps no accede directamente al HRIS sintético.
4. El HRIS sintético es fixture de referencia, no contrato del producto.
5. PeopleOps crea consultas conceptuales; el MCP Server valida, traduce y ejecuta.
6. MCP debe descubrir capabilities, entidades, campos, relaciones y metadata semántica.
7. Policy RAG pertenece a PeopleOps, no al MCP como fuente primaria.
8. Human-in-the-loop debe persistir y reanudarse.
9. `AnalysisInteraction` se crea antes de LangGraph; LangSmith no lo sustituye.
10. Separar Facts, Policies e Inference.
11. Reutilizar los patrones probados de Enterprise RAG para Policy RAG.
12. El Reference MCP Server no requiere frontend en el MVP.

## Aplicaciones mínimas
- `peopleops-api`
- `peopleops-web`
- `reference-mcp-server`

## Persistencias
- PeopleOps Application Data
- Synthetic Reference HRIS Data

## Regla para Codex
Antes de crear una tool, función de routing, provider, tabla o dependencia:
- comprobar si representa una capacidad real;
- comprobar si rompe MCP;
- comprobar si introduce conocimiento del schema físico en PeopleOps;
- comprobar si duplica algo ya validado;
- comprobar si está respaldado por REQ/SPEC.

Si compromete estos principios, no implementar sin ADR aprobado.
