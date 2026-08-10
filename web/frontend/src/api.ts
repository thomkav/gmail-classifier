import type {
  Account,
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

  getAccounts: () => request<Account[]>("/api/accounts"),

  runAudit: (unseenOnly = true, accountId?: number) =>
    request<AuditResult>(`/api/audit?unseen_only=${unseenOnly}${qsAccount(accountId)}`, { method: "POST" }),

  getCachedAudit: (accountId?: number) =>
    request<AuditResult>(`/api/audit/cached${qsAccount(accountId, true)}`),

  getAutoArchivePlan: (threshold = 70, accountId?: number) =>
    request<AutoArchivePlan>(`/api/autoarchive/plan?threshold=${threshold}${qsAccount(accountId)}`),

  applyAutoArchive: (threshold = 70, accountId?: number) =>
    request<ApplyResult>("/api/autoarchive/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ threshold, account_id: accountId ?? null }),
    }),

  clearDomains: (domains: string[], accountId?: number) =>
    request<{ results: ActionResult[] }>("/api/domains/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains, account_id: accountId ?? null }),
    }),

  archiveDomains: (domains: string[], accountId?: number) =>
    request<{ results: ActionResult[] }>("/api/domains/archive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains, account_id: accountId ?? null }),
    }),

  unsubscribeDomains: (domains: string[], mode = "auto", accountId?: number) =>
    request<{ results: ActionResult[] }>("/api/domains/unsubscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains, mode, account_id: accountId ?? null }),
    }),

  setAutoArchiveDomains: (domains: string[], accountId?: number) =>
    request<{ ok: boolean; domains: string[] }>("/api/domains/set-auto-archive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains, account_id: accountId ?? null }),
    }),

  unsetAutoArchiveDomains: (domains: string[], accountId?: number) =>
    request<{ ok: boolean; domains: string[] }>("/api/domains/unset-auto-archive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains, account_id: accountId ?? null }),
    }),

  keepDomains: (domains: string[], accountId?: number) =>
    request<{ ok: boolean; domains: string[] }>("/api/domains/keep", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains, account_id: accountId ?? null }),
    }),

  unkeepDomains: (domains: string[], accountId?: number) =>
    request<{ ok: boolean; domains: string[] }>("/api/domains/un-keep", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains, account_id: accountId ?? null }),
    }),

  noUnsubDomains: (domains: string[], accountId?: number) =>
    request<{ ok: boolean; domains: string[] }>("/api/domains/no-unsub", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains, account_id: accountId ?? null }),
    }),

  unNoUnsubDomains: (domains: string[], accountId?: number) =>
    request<{ ok: boolean; domains: string[] }>("/api/domains/un-no-unsub", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains, account_id: accountId ?? null }),
    }),

  getDecisions: (accountId?: number) =>
    request<Record<string, DomainDecision>>(`/api/decisions${qsAccount(accountId, true)}`),

  getDecisionsSummary: (accountId?: number) =>
    request<Record<string, number>>(`/api/decisions/summary${qsAccount(accountId, true)}`),

  classifyUnknown: (accountId?: number) =>
    request<ClassifyResult>(`/api/classify/unknown${qsAccount(accountId, true)}`, { method: "POST" }),

  getClassifyProgress: () =>
    request<{ running: boolean; total: number; completed: number; results_so_far: Record<string, Classification> }>("/api/classify/progress"),

  classifyDomainManual: (domain: string, category: string, accountId?: number) =>
    request<Classification & { ok: boolean; domain: string }>("/api/domains/classify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain, category, account_id: accountId ?? null }),
    }),

  clearDomainClassification: (domain: string, accountId?: number) =>
    request<{ ok: boolean; domain: string }>(`/api/domains/classify/${encodeURIComponent(domain)}${qsAccount(accountId, true)}`, {
      method: "DELETE",
    }),

  // ── New (T2/T3/T4): SQLite-backed cache, jobs, LLM status ──────────────
  getCachedAuditUnseen: (unseenOnly = true, accountId?: number) =>
    request<AuditResult>(`/api/audit/cached?unseen_only=${unseenOnly}${qsAccount(accountId)}`),

  syncInbox: (full = false, accountId?: number) =>
    request<SyncReport>("/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_resync: full, account_id: accountId ?? null }),
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

  resetUnknownCache: (domains?: string[], accountId?: number) =>
    request<{ deleted: number }>("/api/llm/cache/reset-unknowns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains: domains ?? null, account_id: accountId ?? null }),
    }),
};

/** Query-string fragment for an optional account_id — "" (omitted) picks the
 * server's default account. `first` controls whether it's the first param (?) or an
 * additional one (&). */
function qsAccount(accountId: number | undefined, first = false): string {
  if (accountId == null) return "";
  return `${first ? "?" : "&"}account_id=${accountId}`;
}
