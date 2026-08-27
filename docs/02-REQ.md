# PeopleOps AI — Requirements (REQ)

**Deriva de:** `01-SPEC.md`

## Convenciones
- **MUST** obligatorio MVP.
- **SHOULD** importante salvo justificación documentada.
- **MAY** extensión permitida.

# 1. Product
- REQ-PROD-001 MUST aceptar preguntas HR en lenguaje natural.
- REQ-PROD-002 MUST soportar múltiples idiomas sin routing hardcodeado.
- REQ-PROD-003 MUST resolver nuevas formulaciones componiendo capacidades existentes.
- REQ-PROD-004 MUST asociar evidencia a hechos y reglas.
- REQ-PROD-005 MUST reconocer datos/policies insuficientes.

# 2. Semantic / anti-hardcoding
- REQ-SEM-001 MUST NOT detectar intención mediante keywords.
- REQ-SEM-002 MUST NOT mantener listas de frases por idioma.
- REQ-SEM-003 MUST NOT crear una función únicamente por wording nuevo.
- REQ-SEM-004 MUST usar structured outputs/typed contracts.
- REQ-SEM-005 guardrails MUST validar estructura, seguridad, permisos e invariantes; no interpretar lenguaje libre.

# 3. MCP boundary
- REQ-MCP-001 peopleops-api MUST NOT acceder directamente al Synthetic Reference HRIS.
- REQ-MCP-002 MVP MUST implementar MCP Client real.
- REQ-MCP-003 MVP MUST implementar Reference MCP Server real.
- REQ-MCP-004 Reference MCP Server MUST ser la única puerta integrada al HRIS sintético.
- REQ-MCP-005 MCP Client MUST usar contratos tipados.
- REQ-MCP-006 MUST soportar timeout.
- REQ-MCP-007 MUST normalizar errores.
- REQ-MCP-008 MUST correlacionar request_id end-to-end.
- REQ-MCP-009 MUST NOT existir fallback silencioso a DB directa.

# 4. MCP discovery
- REQ-DISC-001 MUST exponer capabilities.
- REQ-DISC-002 MUST exponer entidades/tablas relevantes.
- REQ-DISC-003 MUST exponer campos/columnas y tipos.
- REQ-DISC-004 MUST exponer relaciones.
- REQ-DISC-005 SHOULD exponer PK/FK/constraints relevantes cuando la fuente sea relacional.
- REQ-DISC-006 MUST exponer semantic metadata suficiente.
- REQ-DISC-007 MUST identificar sensibilidad/clasificación.
- REQ-DISC-008 MUST indicar operaciones soportadas.
- REQ-DISC-009 MUST disponer de catálogo versionado/fingerprint.

# 5. Conceptual query
- REQ-QRY-001 MUST existir contrato conceptual/provider-neutral.
- REQ-QRY-002 MUST soportar entidades.
- REQ-QRY-003 MUST soportar filtros.
- REQ-QRY-004 MUST soportar períodos.
- REQ-QRY-005 MUST soportar métricas/agregaciones cuando la capability lo permita.
- REQ-QRY-006 MUST soportar relaciones.
- REQ-QRY-007 MUST soportar comparaciones entre períodos.
- REQ-QRY-008 MUST validarse antes de ejecutar.
- REQ-QRY-009 PeopleOps MUST NOT depender de dialectos SQL físicos.

# 6. Translation / execution
- REQ-EXEC-001 MCP Server MUST traducir la consulta conceptual al origen.
- REQ-EXEC-002 Reference MCP Server MUST traducir a PostgreSQL controlado.
- REQ-EXEC-003 consulta física MUST validarse antes de ejecutar.
- REQ-EXEC-004 MUST ser read-only.
- REQ-EXEC-005 MUST aplicar row limit.
- REQ-EXEC-006 MUST aplicar timeout.
- REQ-EXEC-007 SHOULD aplicar límites de costo/estimación cuando el DBMS lo permita.
- REQ-EXEC-008 MUST devolver evidence provider-neutral.
- REQ-EXEC-009 MUST normalizar errores físicos.

# 7. Policy ingestion
- REQ-RAG-ING-001 PeopleOps Web/API MUST permitir upload.
- REQ-RAG-ING-002 MUST soportar PDF.
- REQ-RAG-ING-003 SHOULD soportar DOCX si no agrega complejidad desproporcionada.
- REQ-RAG-ING-004 MUST producir chunks + metadata + embeddings.
- REQ-RAG-ING-005 MUST conservar archivos originales.
- REQ-RAG-ING-006 MUST admitir versiones y vigencia.
- REQ-RAG-ING-007 MUST registrar estado/error de ingestión.

# 8. Policy retrieval
- REQ-RAG-RET-001 MUST usar LlamaIndex.
- REQ-RAG-RET-002 MUST persistir embeddings con PostgreSQL/pgvector.
- REQ-RAG-RET-003 MUST soportar metadata filtering.
- REQ-RAG-RET-004 MUST seleccionar versión vigente por fecha.
- REQ-RAG-RET-005 MUST devolver documento+versión+fragmento/página/sección.
- REQ-RAG-RET-006 MUST verificar evidencia antes de citar.
- REQ-RAG-RET-007 MUST abstenerse con evidencia insuficiente.
- REQ-RAG-RET-008 MUST distinguir conflicto de ausencia.

# 9. Agentic workflow
- REQ-AGT-001 MUST usar LangGraph.
- REQ-AGT-002 MUST mantener state tipado.
- REQ-AGT-003 MUST permitir branching.
- REQ-AGT-004 MUST permitir replan/revisión limitada ante validación fallida.
- REQ-AGT-005 MUST limitar loops/retries.
- REQ-AGT-006 MUST NOT crear agente por módulo HR.
- REQ-AGT-007 capabilities MCP y RAG MUST ser seleccionables dinámicamente.
- REQ-AGT-008 MUST combinar structured data + policy evidence.

# 10. AnalysisInteraction
- REQ-AUD-001 MUST crearse antes de LangGraph.
- REQ-AUD-002 MUST generar request_id único.
- REQ-AUD-003 MUST persistir conversation_id cuando aplique.
- REQ-AUD-004 MUST persistir current_stage.
- REQ-AUD-005 MUST persistir stage_history.
- REQ-AUD-006 stage_history MUST ser lógicamente append-only.
- REQ-AUD-007 MUST persistir errores con stage/tipo/detalle seguro.
- REQ-AUD-008 MUST persistir provider/catalog version.
- REQ-AUD-009 MUST persistir evidence auditable.
- REQ-AUD-010 MUST NOT almacenar chain-of-thought.
- REQ-AUD-011 LangSmith MUST NOT ser dependencia funcional.

# 11. Human Review
- REQ-HITL-001 MUST entrar en pending_human_review.
- REQ-HITL-002 MUST persistir durablemente.
- REQ-HITL-003 MUST poder reanudarse.
- REQ-HITL-004 MUST conservar evidence snapshot.
- REQ-HITL-005 MUST auditar decisión humana.
- REQ-HITL-006 MUST soportar approve/reject/needs_information.
- REQ-HITL-007 MUST NOT ejecutar efectos laborales transaccionales en MVP.

# 12. Payroll
- REQ-PAY-001 MUST consultar payroll por empleado/período.
- REQ-PAY-002 MUST comparar períodos.
- REQ-PAY-003 MUST explicar cambios por concepto.
- REQ-PAY-004 MUST cruzar overtime registrado vs pagado.
- REQ-PAY-005 SHOULD cruzar leave/absence si dataset lo soporta.
- REQ-PAY-006 MUST soportar análisis agregado por área/cost center.
- REQ-PAY-007 payroll MUST clasificarse como sensible.

# 13. HR domains
- REQ-HR-001 MUST consultar empleados/estructura.
- REQ-HR-002 MUST consultar contratos/vencimientos.
- REQ-HR-003 MUST consultar attendance/tardanzas/ausencias.
- REQ-HR-004 MUST consultar overtime.
- REQ-HR-005 MUST consultar vacation balance/requests.
- REQ-HR-006 MUST consultar leave requests.
- REQ-HR-007 MUST combinar dominios cuando la pregunta lo exija.

# 14. Conversation
- REQ-CONV-001 MUST soportar conversation_id.
- REQ-CONV-002 cada follow-up MUST generar nuevo request_id.
- REQ-CONV-003 MAY reutilizar contexto relevante.
- REQ-CONV-004 contexto MUST NOT sustituir evidencia actual.

# 15. UI
- REQ-UI-001 MUST existir interfaz web.
- REQ-UI-002 MUST mostrar respuesta.
- REQ-UI-003 MUST mostrar findings/evidence.
- REQ-UI-004 MUST diferenciar data evidence y policy evidence.
- REQ-UI-005 MUST existir administración/carga de policies.
- REQ-UI-006 MUST existir Human Review inbox.
- REQ-UI-007 MUST existir history/status.
- REQ-UI-008 Reference MCP Server MUST NOT requerir frontend en MVP.

# 16. Security
- REQ-SEC-001 repo público MUST usar datos sintéticos.
- REQ-SEC-002 secrets MUST ir por entorno.
- REQ-SEC-003 MUST existir .env.example.
- REQ-SEC-004 MUST aplicar least privilege.
- REQ-SEC-005 MUST controlar payroll.
- REQ-SEC-006 MUST minimizar sensitive logs.
- REQ-SEC-007 policy docs MUST tratarse como contenido no confiable.
- REQ-SEC-008 documentos MUST NOT sobrescribir instrucciones del sistema.
- REQ-SEC-009 MCP Server MUST validar scope/autorización.

# 17. Evaluation
- REQ-EVAL-001 MUST existir dataset versionado.
- REQ-EVAL-002 MUST incluir casos multilingües.
- REQ-EVAL-003 MUST incluir casos negativos.
- REQ-EVAL-004 MUST evaluar structured query correctness.
- REQ-EVAL-005 MUST evaluar Policy RAG retrieval.
- REQ-EVAL-006 MUST evaluar citation/evidence validity.
- REQ-EVAL-007 MUST evaluar abstention.
- REQ-EVAL-008 MUST evaluar HITL routing.
- REQ-EVAL-009 MUST evaluar unsupported claims.
- REQ-EVAL-010 MUST ejecutar MCP contract tests.
- REQ-EVAL-011 MUST demostrar schema independence.
- REQ-EVAL-012 LLM judge MAY complementar, no sustituir, baseline determinista.

# 18. Physical architecture
- REQ-PHY-001 MUST existir peopleops-api.
- REQ-PHY-002 MUST existir peopleops-web.
- REQ-PHY-003 MUST existir reference-mcp-server.
- REQ-PHY-004 PeopleOps data y HRIS data MUST tener ownership lógico separado.
- REQ-PHY-005 MUST existir levantamiento reproducible con Docker/Compose o equivalente.
- REQ-PHY-006 monorepo SHOULD permitir despliegue independiente de los tres deployables.

# 19. Definition of Compliance
No cumple si:
- responde bien pero bypassa MCP;
- usa keywords;
- crea función por pregunta;
- conoce tablas físicas desde PeopleOps;
- no persiste Human Review;
- usa LangSmith como única auditoría;
- cita documentos no verificados;
- no prueba schema independence.
