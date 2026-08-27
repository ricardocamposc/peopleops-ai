"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "../../components/AppShell";
import { apiUrl, displayValue, formatDate, requestJson, statusLabel } from "../../components/api";

type Job = { id: string; policy_version_id: string; status: string; chunk_count: number; error_type?: string | null; error_detail?: string | null };
type Version = { id: string; version: string; effective_from: string; effective_to?: string | null; status: string; original_filename: string; metadata?: Record<string, unknown>; created_at: string };
type Policy = { id: string; document_key: string; title: string; document_type: string; department?: string | null; confidentiality: string; status: string; created_at: string; versions: Version[] };
type UploadResponse = { document: Policy; version: Version; ingestion: Job; idempotent: boolean };

function PolicyCard({ policy, onReindex }: { policy: Policy; onReindex: (version: Version) => void }) {
  const [expanded, setExpanded] = useState(false);
  return <article className="policy-card"><div className="policy-card__header"><div><span className="eyebrow">{policy.document_type} · {policy.confidentiality}</span><h2>{policy.title}</h2><p className="muted">{policy.document_key}{policy.department ? ` · ${policy.department}` : ""}</p></div><span className={`status status--${policy.status}`}>{statusLabel(policy.status)}</span></div><div className="policy-versions"><div className="section-heading"><strong>{policy.versions.length} versión{policy.versions.length === 1 ? "" : "es"}</strong><button className="text-button" onClick={() => setExpanded(!expanded)}>{expanded ? "Ocultar historial" : "Ver historial"}</button></div>{(expanded ? policy.versions : policy.versions.slice(-1)).map((version) => <VersionRow key={version.id} version={version} onReindex={onReindex} />)}</div></article>;
}

function VersionRow({ version, onReindex }: { version: Version; onReindex: (version: Version) => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const reindex = async () => { try { const next = await requestJson<Job>(`/api/v1/policies/versions/${version.id}/reindex`, { method: "POST" }); setJob(next); } catch { onReindex(version); } };
  return <div className="version-row"><div><strong>v{version.version}</strong><p className="muted">Vigente {formatDate(version.effective_from)}{version.effective_to ? ` — ${formatDate(version.effective_to)}` : " en adelante"} · {version.original_filename}</p><span className={`status status--${job?.status ?? version.status}`}>{statusLabel(job?.status ?? version.status)}</span>{job?.error_detail && <p className="error-copy">{job.error_detail}</p>}</div><div className="version-actions"><a className="text-button" href={apiUrl(`/api/v1/policies/versions/${version.id}/original`)} target="_blank" rel="noreferrer">Ver PDF ↗</a>{(job?.status === "failed" || version.status === "failed") && <button className="secondary-button" onClick={reindex}>Reindexar</button>}</div></div>;
}

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<Policy[]>([]); const [query, setQuery] = useState(""); const [status, setStatus] = useState("all"); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null); const [showUpload, setShowUpload] = useState(false); const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(async () => { try { setPolicies(await requestJson<Policy[]>("/api/v1/policies")); setError(null); } catch (err) { setError(err instanceof Error ? err.message : "No pudimos cargar las policies."); } finally { setLoading(false); } }, []);
  useEffect(() => { void load(); }, [load]);
  const filtered = useMemo(() => policies.filter((policy) => `${policy.title} ${policy.document_key} ${policy.department ?? ""}`.toLowerCase().includes(query.toLowerCase()) && (status === "all" || policy.status === status)), [policies, query, status]);
  return <AppShell><section className="page-hero"><div><span className="eyebrow">KNOWLEDGE BASE · {policies.length} DOCUMENTOS</span><h1>Policies que <em>guían</em> las decisiones</h1><p>Gestiona documentos fuente, versiones y el estado de su indexación para mantener la evidencia vigente.</p></div><button className="primary-button" onClick={() => setShowUpload(!showUpload)}>{showUpload ? "Cerrar upload" : "+ Subir policy"}</button></section>
    {showUpload && <UploadForm onComplete={(result) => { setMessage(result.idempotent ? "La versión ya existía; se mantuvo la existente." : "Policy subida y enviada a ingestión."); setShowUpload(false); void load(); }} />}
    {message && <div className="notice notice--success" role="status">{message}</div>}
    <section className="toolbar"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar por título, clave o departamento…" aria-label="Buscar policies" /><select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filtrar status"><option value="all">Todos los estados</option><option value="active">Activas</option><option value="failed">Con fallos</option></select><button className="refresh-button" onClick={() => { setLoading(true); void load(); }} aria-label="Actualizar policies">↻</button></section>
    {error && <div className="notice notice--error" role="alert">{error}</div>}{loading ? <div className="loading-panel">Cargando policies…</div> : filtered.length ? <div className="policy-list">{filtered.map((policy) => <PolicyCard key={policy.id} policy={policy} onReindex={() => setMessage("No pudimos reindexar esta versión. Inténtalo de nuevo.")} />)}</div> : <div className="empty-state panel"><span>◌</span><p>No encontramos policies con esos filtros.</p></div>}
  </AppShell>;
}

function UploadForm({ onComplete }: { onComplete: (result: UploadResponse) => void }) {
  const [submitting, setSubmitting] = useState(false); const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); setSubmitting(true); setError(null); const form = new FormData(event.currentTarget); try { const result = await requestJson<UploadResponse>("/api/v1/policies/upload", { method: "POST", body: form }); onComplete(result); } catch (err) { setError(err instanceof Error ? err.message : "No pudimos subir el PDF."); } finally { setSubmitting(false); } };
  return <form className="upload-panel" onSubmit={submit}><div className="section-heading"><div><span className="eyebrow">NUEVA VERSIÓN</span><h2>Subir documento PDF</h2></div><span className="muted">El PDF original es la fuente de autoridad.</span></div><div className="form-grid"><label>Clave del documento<input name="document_key" required placeholder="vacation-policy" /></label><label>Título<input name="title" required placeholder="Política de vacaciones" /></label><label>Versión<input name="version" required placeholder="2026.1" /></label><label>Tipo<input name="document_type" defaultValue="policy" required /></label><label>Vigente desde<input name="effective_from" type="date" required /></label><label>Vigente hasta<input name="effective_to" type="date" /></label><label>Departamento<input name="department" placeholder="People" /></label><label>Confidencialidad<select name="confidentiality" defaultValue="internal"><option>internal</option><option>confidential</option><option>restricted</option></select></label><label className="full-width">PDF<input name="file" type="file" accept="application/pdf,.pdf" required /></label><label className="full-width">Metadata JSON<input name="metadata" defaultValue="{}" /></label></div>{error && <div className="notice notice--error" role="alert">{error}</div>}<div className="form-footer"><span className="muted">Solo PDF. Se validará tamaño y contenido en la API.</span><button className="primary-button" disabled={submitting}>{submitting ? "Subiendo…" : "Subir y procesar"}</button></div></form>;
}
