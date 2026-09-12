"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { requestJson } from "../components/api";

type StageEvent = {
  stage: string;
  status: string;
  at: string;
  error_type?: string | null;
  graph_node?: string | null;
};

type TraceStep = {
  sequence: number;
  kind: string;
  title: string;
  status?: string | null;
  stage?: string | null;
  graph_node?: string | null;
  tool_name?: string | null;
  at?: string | null;
  summary?: string | null;
  details: string[];
  metrics: Record<string, unknown>;
  payload?: Record<string, unknown> | null;
};

type DetailTrace = {
  request_id: string;
  status: string;
  current_stage: string;
  steps: TraceStep[];
  summary: Record<string, unknown>;
};

type Analysis = {
  id: string;
  request_id: string;
  conversation_id?: string | null;
  question: string;
  status: string;
  current_stage: string;
  stage_history: StageEvent[];
  provider_type?: string | null;
  provider_catalog_version?: string | null;
  structured_result?: Record<string, unknown> | unknown[] | null;
  evidence?: Evidence[] | null;
  response?: ResponsePayload | null;
  warnings?: string[] | null;
  human_review_status?: string | null;
  human_review_id?: string | null;
  error_type?: string | null;
  error_detail?: string | null;
  latency_ms?: number | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
};

type ResponsePayload = {
  answer?: string;
  key_findings?: string[];
  facts?: Record<string, unknown>[];
  policies?: Record<string, unknown>[];
  inference?: string[];
  warnings?: string[];
};

type Evidence = Record<string, unknown> & { type?: string };

const TERMINAL_STATUSES = new Set([
  "completed",
  "failed",
  "insufficient_data",
  "permission_denied",
  "policy_not_found",
  "policy_conflict",
]);

function statusLabel(status?: string | null) {
  if (!status) return "Sin estado";
  const labels: Record<string, string> = {
    received: "Recibido",
    running: "En analisis",
    pending_human_review: "Revision requerida",
    completed: "Completado",
    failed: "Fallido",
    insufficient_data: "Datos insuficientes",
    permission_denied: "Sin permiso",
    policy_not_found: "Politica no encontrada",
    policy_conflict: "Conflicto de politica",
    approve: "Aprobado",
    reject: "Rechazado",
    needs_information: "Falta informacion",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("es-BR", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function EvidenceCard({ item }: { item: Evidence }) {
  const title = String(item.title ?? item.document_key ?? item.provider ?? "Evidencia");
  const rows =
    item.result && typeof item.result === "object"
      ? (item.result as Record<string, unknown>).rows
      : null;

  return (
    <article className="evidence-card">
      <div className="evidence-card__heading">
        <div>
          <span className="eyebrow">{item.type === "policy" ? "POLICY" : "DATA"}</span>
          <h4>{title}</h4>
        </div>
        {item.verified !== undefined && (
          <span className={`verification ${item.verified ? "verification--ok" : ""}`}>
            {item.verified ? "Fuente verificada" : "No verificada"}
          </span>
        )}
      </div>
      {item.type === "policy" ? (
        <>
          <p className="evidence-meta">
            Version {displayValue(item.version)} · Vigencia {displayValue(item.effective_from)}
            {item.effective_to ? ` - ${item.effective_to}` : " en adelante"}
          </p>
          <p className="evidence-fragment">{displayValue(item.fragment ?? item.text)}</p>
          <p className="evidence-meta">
            {item.page ? `Pagina ${item.page}` : ""}
            {item.page && item.section ? " · " : ""}
            {item.section ? `Seccion ${item.section}` : ""}
          </p>
          {typeof item.source_uri === "string" && (
            <a href={item.source_uri} target="_blank" rel="noreferrer" className="source-link">
              Abrir fuente original
            </a>
          )}
        </>
      ) : (
        <>
          <p className="evidence-meta">
            Proveedor: {displayValue(item.provider)} · Entidades: {displayValue(item.entities)}
          </p>
          {Array.isArray(rows) && rows.length > 0 ? (
            <div className="table-wrap">
              <table>
                <tbody>
                  {rows.slice(0, 12).map((row, index) => (
                    <tr key={index}>
                      {Object.entries((row ?? {}) as Record<string, unknown>).map(([key, value]) => (
                        <td key={key}>
                          <span className="table-key">{key}</span>
                          {displayValue(value)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <pre className="data-preview">{JSON.stringify(item.result ?? item, null, 2)}</pre>
          )}
        </>
      )}
    </article>
  );
}

function TraceTimeline({ trace, loading }: { trace: DetailTrace | null; loading: boolean }) {
  const [openStep, setOpenStep] = useState<number | null>(null);

  if (loading) return <div className="loading-panel">Cargando detalle de auditoria...</div>;
  if (!trace?.steps.length) {
    return <EmptyState text="Este analisis aun no tiene detalle de flujo disponible." />;
  }

  return (
    <div className="trace-panel">
      <div className="trace-summary">
        {Object.entries(trace.summary).map(([key, value]) => (
          <span key={key}>
            <strong>{displayValue(value)}</strong>
            {key.replaceAll("_", " ")}
          </span>
        ))}
      </div>
      <div className="timeline timeline--interactive">
        {trace.steps.map((step) => {
          const isOpen = openStep === step.sequence;
          return (
            <button
              className={`timeline-item timeline-item--${step.kind} ${isOpen ? "timeline-item--open" : ""}`}
              key={step.sequence}
              onClick={() => setOpenStep(isOpen ? null : step.sequence)}
              type="button"
            >
              <span className="timeline-dot" />
              <span className="timeline-content">
                <span className="timeline-heading">
                  <strong>{step.title}</strong>
                  <em>{statusLabel(step.status)}</em>
                </span>
                <span>{step.summary ?? `${step.kind} · ${step.graph_node ?? step.stage ?? "workflow"}`}</span>
                <small>
                  {step.tool_name ? `${step.tool_name} · ` : ""}
                  {step.graph_node ?? step.stage ?? "workflow"}
                  {step.at ? ` · ${formatDate(step.at)}` : ""}
                </small>
                {isOpen && (
                  <span className="trace-expanded">
                    {step.details.length > 0 && (
                      <span className="trace-lines">
                        {step.details.map((detail) => (
                          <span key={detail}>{detail}</span>
                        ))}
                      </span>
                    )}
                    {Object.keys(step.metrics ?? {}).length > 0 && (
                      <pre className="data-preview">{JSON.stringify(step.metrics, null, 2)}</pre>
                    )}
                    {step.payload && (
                      <pre className="data-preview">{JSON.stringify(step.payload, null, 2)}</pre>
                    )}
                  </span>
                )}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function AnalysisDetail({
  analysis,
  trace,
  traceLoading,
  onRetryApproved,
}: {
  analysis: Analysis;
  trace: DetailTrace | null;
  traceLoading: boolean;
  onRetryApproved: (reviewId: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<"data" | "policy" | "details">("data");
  const response = analysis.response;
  const persistedEvidence = analysis.evidence ?? [];
  const dataEvidence = persistedEvidence.filter((item) => item.type !== "policy");
  const responsePolicies = (response?.policies ?? []).map((item) => ({ ...item, type: "policy" }));
  const policyEvidence = persistedEvidence.some((item) => item.type === "policy")
    ? persistedEvidence.filter((item) => item.type === "policy")
    : responsePolicies;
  const running = analysis.status === "running" || analysis.status === "received";

  return (
    <section className="detail-column" aria-live="polite">
      <div className="detail-header">
        <div>
          <span className={`status status--${analysis.status}`}>{statusLabel(analysis.status)}</span>
          <h2>{response?.answer ? "Analisis listo" : "Seguimiento del analisis"}</h2>
        </div>
        <span className="request-id">{analysis.request_id}</span>
      </div>
      {running ? (
        <div className="progress">
          <span />
          <p>Procesando etapa: {analysis.current_stage.replaceAll("_", " ")}</p>
        </div>
      ) : null}
      {response?.answer && (
        <div className="answer-card">
          <span className="eyebrow">RESPUESTA</span>
          <p>{response.answer}</p>
        </div>
      )}
      {response?.key_findings?.length ? (
        <div className="findings">
          <span className="eyebrow">HALLAZGOS CLAVE</span>
          {response.key_findings.map((finding) => (
            <p key={finding}>{finding}</p>
          ))}
        </div>
      ) : null}
      {analysis.error_detail && <div className="notice notice--error">{analysis.error_detail}</div>}
      {analysis.human_review_status === "approve" &&
      analysis.status !== "completed" &&
      analysis.human_review_id ? (
        <div className="notice notice--warning">
          <strong>Revisión aprobada</strong>
          <p>La aprobación ya fue registrada, pero el análisis no terminó correctamente.</p>
          <button
            className="secondary-button"
            onClick={() => void onRetryApproved(analysis.human_review_id as string)}
            type="button"
          >
            Reanudar análisis aprobado
          </button>
        </div>
      ) : null}
      {analysis.warnings?.length ? (
        <div className="notice notice--warning">
          <strong>Advertencias</strong>
          {analysis.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      ) : null}
      <div className="tabs" role="tablist" aria-label="Contenido del analisis">
        {(
          [
            ["data", `Data Evidence (${dataEvidence.length})`],
            ["policy", `Policy Evidence (${policyEvidence.length})`],
            ["details", `Detalles (${trace?.steps.length ?? analysis.stage_history.length})`],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            className={tab === value ? "tab tab--active" : "tab"}
            onClick={() => setTab(value)}
            role="tab"
            aria-selected={tab === value}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "data" && (
        <div className="evidence-list">
          {dataEvidence.length ? (
            dataEvidence.map((item, index) => <EvidenceCard item={item} key={index} />)
          ) : (
            <EmptyState text="Este analisis no produjo evidencia estructurada." />
          )}
        </div>
      )}
      {tab === "policy" && (
        <div className="evidence-list">
          {policyEvidence.length ? (
            policyEvidence.map((item, index) => <EvidenceCard item={item} key={index} />)
          ) : (
            <EmptyState text="No se encontro evidencia de politica aplicable." />
          )}
        </div>
      )}
      {tab === "details" && <TraceTimeline trace={trace} loading={traceLoading} />}
    </section>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="empty-state">
      <span>○</span>
      <p>{text}</p>
    </div>
  );
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<Analysis[]>([]);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Analysis | null>(null);
  const [detailTrace, setDetailTrace] = useState<DetailTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await requestJson<Analysis[]>("/api/v1/analysis?limit=50"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pudimos cargar el historial.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSelected = useCallback(
    async (requestId: string, options?: { quiet?: boolean }) => {
      if (!options?.quiet) setDetailLoading(true);
      try {
        const [analysis, trace] = await Promise.all([
          requestJson<Analysis>(`/api/v1/analysis/${requestId}`),
          requestJson<DetailTrace>(`/api/v1/analysis/${requestId}/details`),
        ]);
        setSelected(analysis);
        setDetailTrace(trace);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "No pudimos cargar el analisis.");
      } finally {
        if (!options?.quiet) setDetailLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (!selectedRequestId) return;
    void loadSelected(selectedRequestId);
  }, [selectedRequestId, loadSelected]);

  const selectedStatus = selected?.status;

  useEffect(() => {
    if (!selectedRequestId || !selectedStatus || TERMINAL_STATUSES.has(selectedStatus)) return;
    const timer = window.setInterval(() => {
      void loadSelected(selectedRequestId, { quiet: true });
      void loadHistory();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [selectedRequestId, selectedStatus, loadSelected, loadHistory]);

  const submitAnalysis = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!question.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await requestJson<Analysis>("/api/v1/analysis", {
        method: "POST",
        body: JSON.stringify({ question: question.trim() }),
      });
      setSelected(created);
      setSelectedRequestId(created.request_id);
      setQuestion("");
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pudimos iniciar el analisis.");
    } finally {
      setSubmitting(false);
    }
  };

  const retryApprovedAnalysis = async (reviewId: string) => {
    setError(null);
    try {
      await requestJson(`/api/v1/human-review/${reviewId}/decision`, {
        method: "POST",
        body: JSON.stringify({
          decision: "approve",
          reviewed_by: "reviewer@example.test",
          comments: "Retry approved analysis resume from analysis screen.",
        }),
      });
      if (selectedRequestId) await loadSelected(selectedRequestId);
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pudimos reanudar el analisis aprobado.");
    }
  };

  const recentCount = useMemo(
    () => history.filter((item) => item.status === "completed").length,
    [history],
  );

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark">
          P<span>·</span>
        </div>
        <div>
          <p className="brand-name">
            PeopleOps <em>AI</em>
          </p>
          <p className="brand-subtitle">HR intelligence copilot</p>
        </div>
        <div className="topbar-spacer" />
        <span className="connection">
          <i /> API conectada
        </span>
      </header>
      <div className="workspace">
        <aside className="sidebar">
          <div className="sidebar-label">ESPACIO DE TRABAJO</div>
          <Link className="nav-item nav-item--active" href="/">
            <span aria-hidden="true">⌁</span>
            <span>Analisis</span>
          </Link>
          <button
            className="nav-item"
            onClick={() =>
              document.getElementById("history")?.scrollIntoView({ behavior: "smooth" })
            }
            type="button"
          >
            <span aria-hidden="true">◷</span>
            <span>Historial</span>
          </button>
          <Link className="nav-item" href="/policies">
            <span aria-hidden="true">▣</span>
            <span>Policies</span>
          </Link>
          <Link className="nav-item" href="/human-review">
            <span aria-hidden="true">◇</span>
            <span>Human Review</span>
          </Link>
          <div className="sidebar-footer">
            <span className="eyebrow">ESTADO DEL SISTEMA</span>
            <p>Datos y politicas con trazabilidad.</p>
          </div>
        </aside>
        <div className="content">
          <section className="hero">
            <div>
              <span className="eyebrow">ANALISIS HR · {recentCount} COMPLETADOS</span>
              <h1>
                Que quieres <em>entender</em>?
              </h1>
              <p>
                Pregunta en lenguaje natural. PeopleOps combina datos estructurados y politicas
                vigentes con evidencia verificable.
              </p>
            </div>
          </section>
          <form className="question-form" onSubmit={submitAnalysis}>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ej.: Que areas concentran mas horas extra este trimestre?"
              aria-label="Pregunta para el analisis"
              rows={3}
            />
            <div className="form-footer">
              <span>La respuesta incluira fuentes y advertencias relevantes.</span>
              <button
                className={`primary-button ${submitting ? "primary-button--loading" : ""}`}
                disabled={submitting || !question.trim()}
                type="submit"
              >
                {submitting && <span className="button-spinner" aria-hidden="true" />}
                {submitting ? "Analizando" : "Analizar"}
              </button>
            </div>
          </form>
          {error && (
            <div className="notice notice--error" role="alert">
              {error}
            </div>
          )}
          <div className="analysis-layout">
            {selected ? (
              <AnalysisDetail
                analysis={selected}
                trace={detailTrace}
                traceLoading={detailLoading}
                onRetryApproved={retryApprovedAnalysis}
              />
            ) : (
              <div className="welcome-panel">
                <span className="welcome-icon">◇</span>
                <h2>Tu espacio de analisis</h2>
                <p>
                  Escribe una pregunta para empezar. Podras revisar el estado, la respuesta y cada
                  fuente utilizada.
                </p>
              </div>
            )}
            <section className="history-panel" id="history">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">REGISTRO</span>
                  <h2>Historial reciente</h2>
                </div>
                <button
                  className="refresh-button"
                  onClick={() => void loadHistory()}
                  aria-label="Actualizar historial"
                  type="button"
                >
                  ↻
                </button>
              </div>
              {loading ? (
                <p className="muted">Cargando historial...</p>
              ) : history.length ? (
                <div className="history-list" role="list">
                  {history.map((item) => (
                    <button
                      className={`history-item ${
                        selectedRequestId === item.request_id ? "history-item--active" : ""
                      }`}
                      key={item.request_id}
                      onClick={() => setSelectedRequestId(item.request_id)}
                      type="button"
                    >
                      <span className={`status-dot status-dot--${item.status}`} />
                      <span className="history-copy">
                        <strong>{item.question}</strong>
                        <small>
                          {formatDate(item.created_at)} · {item.current_stage.replaceAll("_", " ")}
                        </small>
                      </span>
                      <span className="history-status">{statusLabel(item.status)}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <EmptyState text="Aun no hay analisis guardados." />
              )}
            </section>
          </div>
        </div>
      </div>
    </main>
  );
}
