import type {
  AuditResult,
  AutoArchivePlan,
  ApplyResult,
  ActionResult,
  DomainDecision,
  ClassifyResult,
  Classification,
  Job,
  LlmStatus,
  SyncReport,
} from "./types";

export const BASE = "http://localhost:45100";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),

  runAudit: (unseenOnly = true) =>
    request<AuditResult>(`/api/audit?unseen_only=${unseenOnly}`, { method: "POST" }),

  getCachedAudit: () =>
    request<AuditResult>("/api/audit/cached"),

  getAutoArchivePlan: (threshold = 70) =>
    request<AutoArchivePlan>(`/api/autoarchive/plan?threshold=${threshold}`),

  applyAutoArchive: (threshold = 70) =>
    request<ApplyResult>("/api/autoarchive/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ threshold }),
    }),

  clearDomains: (domains: string[]) =>
    request<{ results: ActionResult[] }>("/api/domains/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains }),
    }),

  archiveDomains: (domains: string[]) =>
    request<{ results: ActionResult[] }>("/api/domains/archive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains }),
    }),

  unsubscribeDomains: (domains: string[], mode = "auto") =>
    request<{ results: ActionResult[] }>("/api/domains/unsubscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains, mode }),
    }),

  keepDomains: (domains: string[]) =>
    request<{ ok: boolean; domains: string[] }>("/api/domains/keep", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains }),
    }),

  unkeepDomains: (domains: string[]) =>
    request<{ ok: boolean; domains: string[] }>("/api/domains/un-keep", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains }),
    }),

  noUnsubDomains: (domains: string[]) =>
    request<{ ok: boolean; domains: string[] }>("/api/domains/no-unsub", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains }),
    }),

  unNoUnsubDomains: (domains: string[]) =>
    request<{ ok: boolean; domains: string[] }>("/api/domains/un-no-unsub", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains }),
    }),

  getDecisions: () =>
    request<Record<string, DomainDecision>>("/api/decisions"),

  getDecisionsSummary: () =>
    request<Record<string, number>>("/api/decisions/summary"),

  classifyUnknown: () =>
    request<ClassifyResult>("/api/classify/unknown", { method: "POST" }),

  getClassifyProgress: () =>
    request<{ running: boolean; total: number; completed: number; results_so_far: Record<string, Classification> }>("/api/classify/progress"),

  classifyDomainManual: (domain: string, category: string) =>
    request<Classification & { ok: boolean; domain: string }>("/api/domains/classify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain, category }),
    }),

  clearDomainClassification: (domain: string) =>
    request<{ ok: boolean; domain: string }>(`/api/domains/classify/${encodeURIComponent(domain)}`, {
      method: "DELETE",
    }),

  // ── New (T2/T3/T4): SQLite-backed cache, jobs, LLM status ──────────────
  getCachedAuditUnseen: (unseenOnly = true) =>
    request<AuditResult>(`/api/audit/cached?unseen_only=${unseenOnly}`),

  syncInbox: (full = false) =>
    request<SyncReport>("/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_resync: full }),
    }),

  enqueueJob: (kind: string, params: Record<string, unknown> = {}) =>
    request<{ id: number; kind: string }>("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, params }),
    }),

  getJob: (id: number) =>
    request<Job>(`/api/jobs/${id}`),

  getLatestJob: (kind: string) =>
    request<Job>(`/api/jobs/latest?kind=${encodeURIComponent(kind)}`),

  llmStatus: (probe = true) =>
    request<LlmStatus>(`/api/llm/status?probe=${probe}`),

  resetUnknownCache: (domains?: string[]) =>
    request<{ deleted: number }>("/api/llm/cache/reset-unknowns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains: domains ?? null }),
    }),
};
