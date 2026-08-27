"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

type StageEvent = {
  stage: string;
  status: string;
  at: string;
  error_type?: string | null;
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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TERMINAL_STATUSES = new Set([
  "completed",
  "failed",
  "insufficient_data",
  "permission_denied",
  "policy_not_found",
  "policy_conflict",
]);

function apiUrl(path: string) {
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw new Error("No pudimos comunicarnos con PeopleOps API.");
  return response.json() as Promise<T>;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    received: "Recibido",
    running: "En análisis",
    pending_human_review: "Revisión requerida",
    completed: "Completado",
    failed: "Fallido",
    insufficient_data: "Datos insuficientes",
    permission_denied: "Sin permiso",
    policy_not_found: "Política no encontrada",
    policy_conflict: "Conflicto de política",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("es-BR", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function EvidenceCard({ item }: { item: Evidence }) {
  const title = String(item.title ?? item.document_key ?? item.provider ?? "Evidencia");
  const rows = item.result && typeof item.result === "object" ? (item.result as Record<string, unknown>).rows : null;
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
            Versión {displayValue(item.version)} · Vigencia {displayValue(item.effective_from)}
            {item.effective_to ? ` — ${item.effective_to}` : " en adelante"}
          </p>
          <p className="evidence-fragment">“{displayValue(item.fragment ?? item.text)}”</p>
          <p className="evidence-meta">
            {item.page ? `Página ${item.page}` : ""}{item.page && item.section ? " · " : ""}
            {item.section ? `Sección ${item.section}` : ""}
          </p>
          {typeof item.source_uri === "string" && (
            <a href={item.source_uri} target="_blank" rel="noreferrer" className="source-link">
              Abrir fuente original ↗
            </a>
          )}
        </>
      ) : (
        <>
          <p className="evidence-meta">
            Proveedor: {displayValue(item.provider)} · Entidades: {displayValue(item.entities)}
          </p>
          {Array.isArray(rows) && rows.length > 0 ? (
            <div className="table-wrap"><table><tbody>{rows.slice(0, 12).map((row, index) => (
              <tr key={index}>{Object.entries((row ?? {}) as Record<string, unknown>).map(([key, value]) => (
                <td key={key}><span className="table-key">{key}</span>{displayValue(value)}</td>
              ))}</tr>
            ))}</tbody></table></div>
          ) : <pre className="data-preview">{JSON.stringify(item.result ?? item, null, 2)}</pre>}
        </>
      )}
    </article>
  );
}

function AnalysisDetail({ analysis }: { analysis: Analysis }) {
  const [tab, setTab] = useState<"data" | "policy" | "details">("data");
  const dataEvidence = (analysis.evidence ?? []).filter((item) => item.type !== "policy");
  const policyEvidence = (analysis.evidence ?? []).filter((item) => item.type === "policy");
  const response = analysis.response;
  return (
    <section className="detail-column" aria-live="polite">
      <div className="detail-header">
        <div><span className={`status status--${analysis.status}`}>{statusLabel(analysis.status)}</span><h2>{response?.answer ? "Análisis listo" : "Seguimiento del análisis"}</h2></div>
        <span className="request-id">{analysis.request_id}</span>
      </div>
      {analysis.status === "running" || analysis.status === "received" ? <div className="progress"><span /><p>Procesando etapa: {analysis.current_stage.replaceAll("_", " ")}</p></div> : null}
      {response?.answer && <div className="answer-card"><span className="eyebrow">RESPUESTA</span><p>{response.answer}</p></div>}
      {response?.key_findings?.length ? <div className="findings"><span className="eyebrow">HALLAZGOS CLAVE</span>{response.key_findings.map((finding) => <p key={finding}>↳ {finding}</p>)}</div> : null}
      {analysis.error_detail && <div className="notice notice--error">{analysis.error_detail}</div>}
      {analysis.warnings?.length ? <div className="notice notice--warning"><strong>Advertencias</strong>{analysis.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div> : null}
      <div className="tabs" role="tablist" aria-label="Contenido del análisis">
        {([["data", `Data Evidence (${dataEvidence.length})`], ["policy", `Policy Evidence (${policyEvidence.length})`], ["details", "Detalles"]] as const).map(([value, label]) => <button key={value} className={tab === value ? "tab tab--active" : "tab"} onClick={() => setTab(value)} role="tab" aria-selected={tab === value}>{label}</button>)}
      </div>
      {tab === "data" && <div className="evidence-list">{dataEvidence.length ? dataEvidence.map((item, index) => <EvidenceCard item={item} key={index} />) : <EmptyState text="Este análisis no produjo evidencia estructurada." />}</div>}
      {tab === "policy" && <div className="evidence-list">{policyEvidence.length ? policyEvidence.map((item, index) => <EvidenceCard item={item} key={index} />) : <EmptyState text="No se encontró evidencia de política aplicable." />}</div>}
      {tab === "details" && <div className="timeline">{analysis.stage_history?.map((event, index) => <div className="timeline-item" key={`${event.stage}-${index}`}><span className="timeline-dot" /><div><strong>{event.stage.replaceAll("_", " ")}</strong><p>{statusLabel(event.status)} · {formatDate(event.at)}</p>{event.error_type && <small>{event.error_type}</small>}</div></div>)}</div>}
    </section>
  );
}

function EmptyState({ text }: { text: string }) { return <div className="empty-state"><span>◌</span><p>{text}</p></div>; }

export default function Home() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<Analysis[]>([]);
  const [selected, setSelected] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try { setHistory(await requestJson<Analysis[]>("/api/v1/analysis?limit=50")); setError(null); }
    catch (err) { setError(err instanceof Error ? err.message : "No pudimos cargar el historial."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void loadHistory(); }, [loadHistory]);

  useEffect(() => {
    if (!selected || TERMINAL_STATUSES.has(selected.status)) return;
    const timer = window.setInterval(async () => {
      try { setSelected(await requestJson<Analysis>(`/api/v1/analysis/${selected.request_id}`)); void loadHistory(); }
      catch { /* The next polling cycle can recover from a transient API error. */ }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [selected, loadHistory]);

  const submitAnalysis = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (!question.trim()) return;
    setSubmitting(true); setError(null);
    try { const created = await requestJson<Analysis>("/api/v1/analysis", { method: "POST", body: JSON.stringify({ question: question.trim() }) }); setSelected(created); setQuestion(""); await loadHistory(); }
    catch (err) { setError(err instanceof Error ? err.message : "No pudimos iniciar el análisis."); }
    finally { setSubmitting(false); }
  };

  const recentCount = useMemo(() => history.filter((item) => item.status === "completed").length, [history]);
  return (
    <main className="app-shell">
      <header className="topbar"><div className="brand-mark">P<span>·</span></div><div><p className="brand-name">PeopleOps <em>AI</em></p><p className="brand-subtitle">HR intelligence copilot</p></div><div className="topbar-spacer" /><span className="connection"><i /> API conectada</span></header>
      <div className="workspace">
        <aside className="sidebar"><div className="sidebar-label">ESPACIO DE TRABAJO</div><Link className="nav-item nav-item--active" href="/">⌁ <span>Análisis</span></Link><button className="nav-item" onClick={() => document.getElementById("history")?.scrollIntoView({ behavior: "smooth" })}>◷ <span>Historial</span></button><Link className="nav-item" href="/policies">▣ <span>Policies</span></Link><Link className="nav-item" href="/human-review">◈ <span>Human Review</span></Link><div className="sidebar-footer"><span className="eyebrow">ESTADO DEL SISTEMA</span><p>Datos y políticas con trazabilidad.</p></div></aside>
        <div className="content"><section className="hero"><div><span className="eyebrow">ANÁLISIS HR · {recentCount} COMPLETADOS</span><h1>¿Qué quieres <em>entender</em>?</h1><p>Pregunta en lenguaje natural. PeopleOps combina datos estructurados y políticas vigentes con evidencia verificable.</p></div><div className="hero-orb">✦</div></section>
          <form className="question-form" onSubmit={submitAnalysis}><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ej.: ¿Qué áreas concentran más horas extra este trimestre?" aria-label="Pregunta para el análisis" rows={3} /><div className="form-footer"><span>La respuesta incluirá fuentes y advertencias relevantes.</span><button className="primary-button" disabled={submitting || !question.trim()}>{submitting ? "Analizando…" : "Iniciar análisis  →"}</button></div></form>
          {error && <div className="notice notice--error">{error}</div>}
          <div className="analysis-layout">{selected ? <AnalysisDetail analysis={selected} /> : <div className="welcome-panel"><span className="welcome-icon">✦</span><h2>Tu espacio de análisis</h2><p>Escribe una pregunta para empezar. Podrás revisar el estado, la respuesta y cada fuente utilizada.</p></div>}
            <section className="history-panel" id="history"><div className="section-heading"><div><span className="eyebrow">REGISTRO</span><h2>Historial reciente</h2></div><button className="refresh-button" onClick={() => void loadHistory()} aria-label="Actualizar historial">↻</button></div>{loading ? <p className="muted">Cargando historial…</p> : history.length ? <div className="history-list">{history.map((item) => <button className={`history-item ${selected?.request_id === item.request_id ? "history-item--active" : ""}`} key={item.request_id} onClick={() => setSelected(item)}><span className={`status-dot status-dot--${item.status}`} /><span className="history-copy"><strong>{item.question}</strong><small>{formatDate(item.created_at)} · {item.current_stage.replaceAll("_", " ")}</small></span><span className="history-status">{statusLabel(item.status)}</span></button>)}</div> : <EmptyState text="Aún no hay análisis guardados." />}</section>
          </div>
        </div>
      </div>
    </main>
  );
}
