export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function apiUrl(path: string) {
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: { ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...init?.headers },
  });
  if (!response.ok) {
    let detail = "No pudimos comunicarnos con PeopleOps API.";
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch { /* Keep a safe generic error for non-JSON responses. */ }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function formatDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("es-BR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function statusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: "En cola", running: "Procesando", completed: "Disponible", failed: "Fallido",
    pending: "Pendiente", approve: "Aprobado", reject: "Rechazado", needs_information: "Falta información",
    active: "Vigente", processing: "Procesando", superseded: "Reemplazado", inactive: "No vigente",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

export function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
