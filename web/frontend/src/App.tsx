import { useState, useCallback, useEffect, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AuditResult, CategoryName, ActionResult, Domain, DomainDecision, DecisionState, Classification } from "./types";
import { api } from "./api";
import { AuditTable } from "./components/AuditTable";
import { DecisionsPanel } from "./components/DecisionsPanel";
import { AutoArchiveModal } from "./components/AutoArchiveModal";
import { Tooltip, InfoTip } from "./components/Tooltip";
import { useAudit, useDecisions, useEnqueueJob, useJob } from "./hooks";
import { useEventStream, type AppEvent } from "./useEvents";
import { qk } from "./queryClient";

type Tab = "all" | CategoryName | "impact" | "decisions";

const CATEGORY_TABS: { id: Tab; label: string }[] = [
  { id: "all",          label: "All" },
  { id: "receipt",      label: "Receipts" },
  { id: "newsletter",   label: "Newsletters" },
  { id: "promotion",    label: "Promotions" },
  { id: "notification", label: "Notifications" },
  { id: "unknown",      label: "Unknown" },
  { id: "impact",       label: "⚡ Impact" },
  { id: "decisions",    label: "Decisions" },
];

/** Domains on the Impact tab: unblocked, not keep-listed, actionable, sorted by count */
function impactDomains(domains: Domain[]): Domain[] {
  return domains
    .filter(
      (d) =>
        !d.archived &&
        !d.keep &&
        d.classification?.suggested_action !== "keep" &&
        d.classification?.category !== "receipt" &&
        d.classification?.category !== "notification"
    )
    .sort((a, b) => b.count - a.count);
}

interface Toast {
  id: number;
  message: string;
  type: "success" | "error";
}

function Spinner({ size = "sm" }: { size?: "sm" | "lg" }) {
  const cls = size === "lg" ? "w-8 h-8 border-2" : "w-4 h-4 border-2";
  return (
    <div className={`${cls} border-current border-t-transparent rounded-full animate-spin opacity-60`} />
  );
}

export function App() {
  const qc = useQueryClient();
  const [unseenOnly, setUnseenOnly]     = useState(true);
  const [tab, setTab]                   = useState<Tab>("all");
  const [selected, setSelected]         = useState<Set<string>>(new Set());
  const [showAutoArchive, setShowAutoArchive] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError]               = useState<string | null>(null);
  const [toasts, setToasts]             = useState<Toast[]>([]);

  // Active background-job ids for sync and classify. Polling each via useJob
  // gives us live progress without a manual setInterval.
  const [syncJobId, setSyncJobId] = useState<number | null>(null);
  const [classifyJobId, setClassifyJobId] = useState<number | null>(null);

  const auditQuery = useAudit(unseenOnly);
  const audit: AuditResult | undefined = auditQuery.data;
  const decisionsQuery = useDecisions();
  const allDecisions: Record<string, DomainDecision> = (decisionsQuery.data as Record<string, DomainDecision>) ?? {};
  const enqueueJob = useEnqueueJob();
  const syncJob = useJob(syncJobId);
  const classifyJob = useJob(classifyJobId);
  const loading = auditQuery.isFetching || syncJob.data?.status === "running";
  const classifyLoading = classifyJob.data ? (classifyJob.data.status === "running" || classifyJob.data.status === "pending") : false;
  const classifyProgress = useMemo(() => {
    const j = classifyJob.data;
    if (!j) return null;
    return { total: j.progress_total, completed: j.progress_done };
  }, [classifyJob.data]);

  // Subscribe to SSE — invalidates queries and lets us react inline if needed.
  useEventStream(useCallback((event: AppEvent) => {
    if (event.kind === "job.done") {
      const k = event.job_kind;
      const id = event.id as number | undefined;
      if (k === "sync" && id === syncJobId) {
        setSyncJobId(null);
      }
      if (k === "classify" && id === classifyJobId) {
        // Final results live on the job's `result` payload; useJob will re-fetch
        // and the audit will refresh via the SSE-triggered invalidation.
        setClassifyJobId(null);
      }
    }
  }, [syncJobId, classifyJobId]));

  // Surface sync job errors as toasts.
  useEffect(() => {
    if (syncJob.data?.status === "error" && syncJob.data.error) {
      setError(`Sync failed: ${syncJob.data.error.split("\n")[0]}`);
    }
  }, [syncJob.data?.status, syncJob.data?.error]);

  // Cache empty (404)? auto-trigger a sync so first-time users see something.
  useEffect(() => {
    if (auditQuery.error && !syncJobId) {
      // first-run convenience — don't surface as a hard error.
      setError(null);
      enqueueJob.mutate({ kind: "sync" }, {
        onSuccess: (d) => setSyncJobId(d.id),
      });
    }
  }, [auditQuery.error, syncJobId]); // eslint-disable-line react-hooks/exhaustive-deps

  const addToast = useCallback(
    (message: string, type: Toast["type"] = "success") => {
      const id = Date.now();
      setToasts((t) => [...t, { id, message, type }]);
      setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
    },
    []
  );

  /** Mutate the cached audit immutably without an extra GET. */
  const updateAudit = useCallback(
    (mut: (prev: AuditResult) => AuditResult) => {
      qc.setQueryData<AuditResult>(qk.audit(unseenOnly), (prev) => prev ? mut(prev) : prev);
    },
    [qc, unseenOnly]
  );

  const runAudit = useCallback(
    async (_forceUnseenOnly?: boolean) => {
      setError(null);
      setSelected(new Set());
      try {
        const { id } = await api.enqueueJob("sync", {});
        setSyncJobId(id);
        setTab("all");
        // The audit cache will refresh automatically when the SSE job.done event fires.
      } catch (e) {
        setError(e instanceof Error ? e.message : "Sync failed");
      }
    },
    []
  );

  /** Optimistically write decisions to the decisions cache and (optionally) domain.decision in audit */
  const applyDecisionOptimistic = useCallback(
    (
      domains: string[],
      state: DecisionState,
      updateAuditDomains: boolean,
      countMap?: Map<string, number>
    ) => {
      const today = new Date().toISOString().split("T")[0];
      qc.setQueryData<Record<string, DomainDecision>>(qk.decisions(), (prev) => {
        const next = { ...(prev ?? {}) };
        for (const domain of domains) {
          next[domain] = { state, decided_at: today, email_count: countMap?.get(domain) ?? 0 };
        }
        return next;
      });
      if (updateAuditDomains) {
        const domainSet = new Set(domains);
        updateAudit((prev) => ({
          ...prev,
          domains: prev.domains.map((d) =>
            domainSet.has(d.domain)
              ? { ...d, decision: { state, decided_at: today, email_count: d.count } }
              : d
          ),
        }));
      }
    },
    [qc, updateAudit]
  );

  const handleClear = useCallback(
    async (domains: string[]) => {
      if (domains.length === 0) return;
      setActionLoading(true);
      try {
        const { results } = await api.clearDomains(domains);
        const countMap = new Map(results.map((r) => [r.domain, r.count ?? 0]));
        const succeeded = results.filter((r) => r.success).map((r) => r.domain);
        applyInboxRemovalToState(results);
        applyDecisionOptimistic(succeeded, "seen", false, countMap);
        const total = results.reduce((s, r) => s + (r.count ?? 0), 0);
        const ok = succeeded.length;
        const fail = results.filter((r) => !r.success).length;
        addToast(`Cleared ${total} emails from ${ok} domain(s)${fail ? ` (${fail} failed)` : ""}`);
      } catch (e) {
        addToast(e instanceof Error ? e.message : "Clear failed", "error");
      } finally {
        setActionLoading(false);
      }
    },
    [addToast] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const handleArchive = useCallback(
    async (domains: string[]) => {
      if (domains.length === 0) return;
      setActionLoading(true);
      try {
        const { results } = await api.archiveDomains(domains);
        const countMap = new Map(results.map((r) => [r.domain, r.count ?? 0]));
        const succeeded = results.filter((r) => r.success).map((r) => r.domain);
        applyInboxRemovalToState(results);
        applyDecisionOptimistic(succeeded, "archived", false, countMap);
        const total = results.reduce((s, r) => s + (r.count ?? 0), 0);
        const ok = succeeded.length;
        const fail = results.filter((r) => !r.success).length;
        addToast(`Archived ${total} emails from ${ok} domain(s)${fail ? ` (${fail} failed)` : ""}`);
      } catch (e) {
        addToast(e instanceof Error ? e.message : "Archive failed", "error");
      } finally {
        setActionLoading(false);
      }
    },
    [addToast] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const handleUnsubscribe = useCallback(
    async (domains: string[]) => {
      if (domains.length === 0) return;
      setActionLoading(true);
      try {
        const { results } = await api.unsubscribeDomains(domains, "auto");
        for (const r of results) {
          if (r.method === "browser" && r.url) {
            window.open(r.url, "_blank", "noopener,noreferrer");
          }
        }
        const succeeded = results.filter((r) => r.success).map((r) => r.domain);
        applyDecisionOptimistic(succeeded, "unsub_pending", true);
        applyUnsubToState(results);
        const ok = succeeded.length;
        addToast(`Unsubscribed from ${ok} domain(s)`);
      } catch (e) {
        addToast(e instanceof Error ? e.message : "Unsubscribe failed", "error");
      } finally {
        setActionLoading(false);
      }
    },
    [addToast] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const handleBoth = useCallback(
    async (domains: string[]) => {
      if (domains.length === 0) return;
      setActionLoading(true);
      try {
        const [archiveRes, unsubRes] = await Promise.all([
          api.archiveDomains(domains),
          api.unsubscribeDomains(domains, "auto"),
        ]);
        for (const r of unsubRes.results) {
          if (r.method === "browser" && r.url) {
            window.open(r.url, "_blank", "noopener,noreferrer");
          }
        }
        const archiveCountMap = new Map(archiveRes.results.map((r) => [r.domain, r.count ?? 0]));
        const archiveSucceeded = archiveRes.results.filter((r) => r.success).map((r) => r.domain);
        applyInboxRemovalToState(archiveRes.results);
        // Archive wins over unsub for the decision state (most committed action)
        applyDecisionOptimistic(archiveSucceeded, "archived", false, archiveCountMap);
        const total = archiveRes.results.reduce((s, r) => s + (r.count ?? 0), 0);
        const unsubOk = unsubRes.results.filter((r) => r.success).length;
        addToast(`Archived ${total} emails; unsubscribed from ${unsubOk} domain(s)`);
      } catch (e) {
        addToast(e instanceof Error ? e.message : "Action failed", "error");
      } finally {
        setActionLoading(false);
      }
    },
    [addToast] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const handleKeep = useCallback(
    async (domains: string[]) => {
      if (domains.length === 0) return;
      setActionLoading(true);
      try {
        await api.keepDomains(domains);
        const keepSet = new Set(domains);
        updateAudit((prev) => ({ ...prev, domains: prev.domains.map((d) => keepSet.has(d.domain) ? { ...d, keep: true } : d) }));
        applyDecisionOptimistic(domains, "keep", true);
        setSelected((prev) => {
          const next = new Set(prev);
          for (const d of domains) next.delete(d);
          return next;
        });
        addToast(`${domains.length} domain(s) set to never auto-archive`);
      } catch (e) {
        addToast(e instanceof Error ? e.message : "Failed to update keep list", "error");
      } finally {
        setActionLoading(false);
      }
    },
    [addToast] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const handleUnkeep = useCallback(
    async (domains: string[]) => {
      if (domains.length === 0) return;
      setActionLoading(true);
      try {
        await api.unkeepDomains(domains);
        const set = new Set(domains);
        updateAudit((prev) => ({ ...prev, domains: prev.domains.map((d) => set.has(d.domain) ? { ...d, keep: false } : d) }));
        qc.setQueryData<Record<string, DomainDecision>>(qk.decisions(), (prev) => {
          const next = { ...(prev ?? {}) };
          for (const d of domains) {
            if (next[d]?.state === "keep") next[d] = { ...next[d], state: "seen" };
          }
          return next;
        });
        addToast(`${domains.length} domain(s) removed from never auto-archive list`);
      } catch (e) {
        addToast(e instanceof Error ? e.message : "Failed to update keep list", "error");
      } finally {
        setActionLoading(false);
      }
    },
    [addToast]
  );

  const handleNoUnsub = useCallback(
    async (domains: string[]) => {
      if (domains.length === 0) return;
      setActionLoading(true);
      try {
        await api.noUnsubDomains(domains);
        const noUnsubSet = new Set(domains);
        updateAudit((prev) => ({ ...prev, domains: prev.domains.map((d) => noUnsubSet.has(d.domain) ? { ...d, no_unsub: true } : d) }));
        setSelected((prev) => {
          const next = new Set(prev);
          for (const d of domains) next.delete(d);
          return next;
        });
        addToast(`${domains.length} domain(s) set to skip unsub`);
      } catch (e) {
        addToast(e instanceof Error ? e.message : "Failed to update no-unsub list", "error");
      } finally {
        setActionLoading(false);
      }
    },
    [addToast]
  );

  const handleUnNoUnsub = useCallback(
    async (domains: string[]) => {
      if (domains.length === 0) return;
      setActionLoading(true);
      try {
        await api.unNoUnsubDomains(domains);
        const set = new Set(domains);
        updateAudit((prev) => ({ ...prev, domains: prev.domains.map((d) => set.has(d.domain) ? { ...d, no_unsub: false } : d) }));
        addToast(`${domains.length} domain(s) removed from skip-unsub list`);
      } catch (e) {
        addToast(e instanceof Error ? e.message : "Failed to update no-unsub list", "error");
      } finally {
        setActionLoading(false);
      }
    },
    [addToast]
  );

  const handleClassifyUnknown = useCallback(async () => {
    try {
      const { id } = await api.enqueueJob("classify", { unseen_only: unseenOnly });
      setClassifyJobId(id);
    } catch (e) {
      addToast(e instanceof Error ? e.message : "Classification failed", "error");
    }
  }, [addToast, unseenOnly]);

  const handleForceReclassify = useCallback(async () => {
    try {
      const { deleted } = await api.resetUnknownCache();
      if (deleted > 0) addToast(`Cleared ${deleted} cached unknown(s) — re-classifying…`);
      const { id } = await api.enqueueJob("classify", { unseen_only: unseenOnly });
      setClassifyJobId(id);
    } catch (e) {
      addToast(e instanceof Error ? e.message : "Force reclassify failed", "error");
    }
  }, [addToast, unseenOnly]);

  // When classify finishes, splice its results into the audit cache without a refetch.
  useEffect(() => {
    const j = classifyJob.data;
    if (!j || j.status !== "done") return;
    const results = (j.result as { results?: Record<string, Classification>; classified?: number } | null)?.results;
    if (!results) return;
    updateAudit((prev) => ({
      ...prev,
      domains: prev.domains.map((d) => {
        const r = results[d.domain];
        if (!r) return d;
        if (d.classification?.source === "manual") return d;
        return { ...d, classification: r };
      }),
    }));
    const classified = (j.result as { classified?: number } | null)?.classified ?? 0;
    addToast(classified > 0 ? `Classified ${classified} domains` : "No new classifications — unknowns remain unknown");
  }, [classifyJob.data?.id, classifyJob.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleClassifyManual = useCallback(
    async (domain: string, category: CategoryName) => {
      try {
        const result = await api.classifyDomainManual(domain, category);
        updateAudit((prev) => ({
          ...prev,
          domains: prev.domains.map((d) =>
            d.domain === domain ? { ...d, classification: result as Classification } : d
          ),
        }));
      } catch (e) {
        addToast(e instanceof Error ? e.message : "Manual classification failed", "error");
      }
    },
    [addToast, updateAudit]
  );

  const applyInboxRemovalToState = useCallback((results: ActionResult[]) => {
    const removed = new Set(results.filter((r) => r.success).map((r) => r.domain));
    const emailsCleared = results.filter((r) => r.success).reduce((s, r) => s + (r.count ?? 0), 0);
    updateAudit((prev) => ({
      ...prev,
      total_unread: Math.max(0, prev.total_unread - emailsCleared),
      domains: prev.domains.filter((d) => !removed.has(d.domain)),
    }));
    setSelected((prev) => {
      const next = new Set(prev);
      for (const d of removed) next.delete(d);
      return next;
    });
  }, [updateAudit]);

  const applyUnsubToState = useCallback((results: ActionResult[]) => {
    const today = new Date().toISOString().split("T")[0];
    const unsubbed = new Set(results.filter((r) => r.success).map((r) => r.domain));
    updateAudit((prev) => ({
      ...prev,
      domains: prev.domains.map((d) => unsubbed.has(d.domain) ? { ...d, unsubscribed_date: today } : d),
    }));
    setSelected((prev) => {
      const next = new Set(prev);
      for (const d of unsubbed) next.delete(d);
      return next;
    });
  }, [updateAudit]);

  // Derived counts
  const filteredDomains = (() => {
    if (!audit) return [];
    if (tab === "impact")    return impactDomains(audit.domains);
    if (tab === "decisions") return [];
    if (tab === "all")       return audit.domains;
    return audit.domains.filter((d) => d.classification?.category === tab);
  })();

  const tabCounts = audit?.domains.reduce<Record<string, number>>((acc, d) => {
    const cat = d.classification?.category ?? "unknown";
    acc[cat] = (acc[cat] ?? 0) + 1;
    return acc;
  }, {});

  const impactCount = audit ? impactDomains(audit.domains).length : 0;
  const impactEmailCount = audit
    ? impactDomains(audit.domains).reduce((s, d) => s + d.count, 0)
    : 0;

  const recidivistCount = audit
    ? audit.domains.filter((d) => d.decision?.state === "recidivist").length
    : 0;

  const autoArchiveReadyCount = audit
    ? audit.domains.filter((d) => d.archived).length
    : 0;

  const unknownCount = audit
    ? audit.domains.filter((d) => !d.classification || d.classification.category === "unknown").length
    : 0;

  const selectedDomains = [...selected];

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-200 px-6 py-3 flex items-center gap-4 shrink-0 bg-white">
        <h1 className="text-sm font-semibold tracking-wide text-gray-800 uppercase">
          Gmail Classifier
        </h1>
        {audit && (
          <span className="text-gray-400 text-xs">
            {audit.total_unread.toLocaleString()} {unseenOnly ? "unread" : "inbox"} · {audit.domains.length} domains
          </span>
        )}

        <div className="ml-auto flex items-center gap-4">
          {/* Unread-only toggle */}
          <Tooltip
            side="bottom"
            content="When checked, only fetches UNSEEN (unread) emails. Uncheck to scan your entire INBOX including read emails — useful for catching domains that marked messages read automatically."
          >
            <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={unseenOnly}
                onChange={(e) => setUnseenOnly(e.target.checked)}
                className="accent-indigo-600"
              />
              Unread only
            </label>
          </Tooltip>

          {/* Classify unknowns button + progress */}
          {audit && unknownCount > 0 && (
            classifyLoading && classifyProgress ? (
              <div className="flex items-center gap-2 text-xs text-gray-600">
                <Spinner />
                <div className="flex flex-col gap-0.5">
                  <span className="tabular-nums">
                    {classifyProgress.completed} / {classifyProgress.total} domains
                  </span>
                  <div className="w-32 h-1 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 rounded-full transition-all duration-700"
                      style={{ width: `${classifyProgress.total > 0 ? Math.round((classifyProgress.completed / classifyProgress.total) * 100) : 0}%` }}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-1">
                <Tooltip
                  side="bottom"
                  content="Sends unknown domains to your local LiteLLM MLX stack (Qwen2.5-Coder-7B) for classification. Results are cached in config.json and applied as batches finish."
                >
                  <button
                    onClick={handleClassifyUnknown}
                    disabled={classifyLoading || loading}
                    className="btn-ghost text-xs flex items-center gap-1.5"
                  >
                    {classifyLoading && <Spinner />}
                    {classifyLoading ? "Classifying…" : "Classify unknowns"}
                    <span className="px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500 text-[10px] font-medium tabular-nums">
                      {unknownCount}
                    </span>
                  </button>
                </Tooltip>
                <Tooltip
                  side="bottom"
                  content="Force reclassify: clears cached 'unknown' results then re-runs the LLM. Use when the LLM previously returned unknown for a domain and you want to retry."
                >
                  <button
                    onClick={handleForceReclassify}
                    disabled={classifyLoading || loading}
                    className="btn-ghost text-xs px-1.5"
                    aria-label="Force reclassify unknowns"
                  >
                    ↺
                  </button>
                </Tooltip>
              </div>
            )
          )}

          {/* Auto-archive button */}
          <Tooltip
            side="bottom"
            content="Runs the full classification pipeline on your inbox and builds an archive plan. Shows a preview of which domains will be archived and why before anything is applied. Targets: promotions above the confidence threshold, low-quality newsletters, and domains in your auto-archive list."
          >
            <button
              onClick={() => setShowAutoArchive(true)}
              disabled={!audit || loading}
              className="btn-ghost text-xs flex items-center gap-1.5"
            >
              Auto-archive
              {autoArchiveReadyCount > 0 && (
                <span className="px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-medium tabular-nums">
                  {autoArchiveReadyCount} ready
                </span>
              )}
            </button>
          </Tooltip>

          <button onClick={() => runAudit()} disabled={loading} className="btn-primary text-xs">
            {loading && <Spinner />}
            {loading ? "Auditing…" : "Run Audit"}
          </button>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 border-b border-red-200 px-6 py-2 text-red-700 text-xs">
          {error}
        </div>
      )}

      {/* Empty state */}
      {!audit && !loading && (
        <div className="flex flex-col items-center justify-center flex-1 gap-4">
          <p className="text-gray-500 text-sm">Connect to Gmail and classify your inbox.</p>
          <button onClick={() => runAudit()} className="btn-primary">Run Audit</button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex flex-col items-center justify-center flex-1 gap-4">
          <Spinner size="lg" />
          <p className="text-gray-600 text-sm">Fetching and classifying {unseenOnly ? "unread" : "all inbox"} mail…</p>
          <p className="text-gray-400 text-xs">Connects via IMAP — takes 20–60 s depending on inbox size.</p>
        </div>
      )}

      {audit && !loading && (
        <>
          {/* Category tabs */}
          <div className="border-b border-gray-200 px-4 flex gap-0 shrink-0 overflow-x-auto bg-white">
            {CATEGORY_TABS.map(({ id, label }) => {
              const count =
                id === "all"       ? audit.domains.length :
                id === "impact"    ? impactCount :
                id === "decisions" ? Object.keys(allDecisions).length :
                (tabCounts?.[id] ?? 0);

              const isDecisions = id === "decisions";

              return (
                <button
                  key={id}
                  onClick={() => { setTab(id); setSelected(new Set()); }}
                  className={`px-3 py-2.5 text-xs whitespace-nowrap border-b-2 -mb-px transition-colors ${
                    tab === id
                      ? "border-indigo-600 text-gray-900"
                      : "border-transparent text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {label}
                  {isDecisions && recidivistCount > 0 ? (
                    <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-red-500 text-white text-[10px] font-medium tabular-nums">
                      {recidivistCount}
                    </span>
                  ) : (
                    <span className={`ml-1.5 ${tab === id ? "text-gray-500" : "text-gray-400"}`}>
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Impact banner */}
          {tab === "impact" && impactDomains(audit.domains).length > 0 && (
            <div className="px-4 py-2.5 bg-amber-50 border-b border-amber-200 flex items-center gap-2 text-xs text-amber-800 shrink-0">
              <span>⚡</span>
              <span>
                Archiving these{" "}
                <span className="font-semibold">{impactCount} domains</span> would clear{" "}
                <span className="font-semibold">{impactEmailCount.toLocaleString()} emails</span> from your inbox.
              </span>
              <InfoTip
                content="Impact surfaces unblocked, actionable domains sorted by email count — the highest-ROI targets for cleanup. Excludes receipts, notifications, and senders already in your keep list."
                side="bottom"
              />
              <div className="ml-auto flex gap-2">
                <button
                  onClick={() => {
                    setSelected(new Set(impactDomains(audit.domains).map((d) => d.domain)));
                  }}
                  className="text-xs px-2 py-1 rounded bg-amber-100 hover:bg-amber-200 text-amber-800 border border-amber-300"
                >
                  Select all
                </button>
              </div>
            </div>
          )}

          {/* Recidivist banner — shown on impact tab when recidivists present */}
          {tab === "impact" && recidivistCount > 0 && (
            <div className="px-4 py-2.5 bg-red-50 border-b border-red-200 flex items-center gap-2 text-xs text-red-800 shrink-0">
              <span>⚠</span>
              <span>
                <span className="font-semibold">{recidivistCount} domain{recidivistCount !== 1 ? "s" : ""}</span> ignored your unsubscribe request and are still emailing you. Consider archiving them.
              </span>
              <button
                onClick={() => setTab("decisions")}
                className="ml-auto text-xs px-2 py-1 rounded bg-red-100 hover:bg-red-200 text-red-700 border border-red-200"
              >
                View in Decisions
              </button>
            </div>
          )}

          {/* Sticky action bar — hidden on decisions tab */}
          {selected.size > 0 && tab !== "decisions" && (
            <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-gray-200 px-4 py-2 flex items-center gap-3 shrink-0 shadow-sm">
              <span className="text-xs text-gray-600">{selected.size} selected</span>

              <Tooltip content="Removes all emails from selected domains from INBOX right now — one-time cleanup. Does not add to any list; future mail is unaffected.">
                <button onClick={() => handleClear(selectedDomains)} disabled={actionLoading} className="btn-ghost text-xs">
                  Clear
                </button>
              </Tooltip>

              <Tooltip content="Removes all emails from INBOX AND adds each domain to your auto-archive list. Future mail from these domains will be caught by Auto-archive.">
                <button onClick={() => handleArchive(selectedDomains)} disabled={actionLoading} className="btn-archive text-xs">
                  Archive
                </button>
              </Tooltip>

              <Tooltip content="For each domain, finds the List-Unsubscribe header in the most recent email. Sends a one-click HTTP POST (RFC 8058) where supported. Otherwise opens the unsubscribe URL in your browser.">
                <button onClick={() => handleUnsubscribe(selectedDomains)} disabled={actionLoading} className="btn-unsub text-xs">
                  Unsubscribe
                </button>
              </Tooltip>

              <Tooltip content="Archives emails AND unsubscribes for all selected domains simultaneously.">
                <button onClick={() => handleBoth(selectedDomains)} disabled={actionLoading} className="btn-both text-xs">
                  Both
                </button>
              </Tooltip>

              <div className="w-px h-4 bg-gray-200 mx-1" />

              <Tooltip content="Adds selected domains to your keep_senders list. Future mail from these domains bypasses classification and is never auto-archived.">
                <button onClick={() => handleKeep(selectedDomains)} disabled={actionLoading} className="text-xs px-2.5 py-1 rounded border border-emerald-300 text-emerald-700 hover:bg-emerald-50 disabled:opacity-40">
                  Never auto-archive
                </button>
              </Tooltip>

              <Tooltip content="Adds selected domains to your no_unsub list. Unsubscribe actions will be skipped for these domains — useful for accounts you want to archive but can't unsubscribe from.">
                <button onClick={() => handleNoUnsub(selectedDomains)} disabled={actionLoading} className="text-xs px-2.5 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-40">
                  Skip unsub
                </button>
              </Tooltip>

              {actionLoading && <Spinner />}
              <button onClick={() => setSelected(new Set())} className="ml-auto text-xs text-gray-400 hover:text-gray-600">
                Clear
              </button>
            </div>
          )}

          {/* Content area */}
          <div className="flex-1 overflow-auto">
            {tab === "decisions" ? (
              <DecisionsPanel decisions={allDecisions} currentDomains={audit.domains} />
            ) : (
              <AuditTable
                domains={filteredDomains}
                selected={selected}
                onToggle={(domain) =>
                  setSelected((prev) => {
                    const next = new Set(prev);
                    next.has(domain) ? next.delete(domain) : next.add(domain);
                    return next;
                  })
                }
                onToggleAll={() =>
                  setSelected(
                    selected.size === filteredDomains.length
                      ? new Set()
                      : new Set(filteredDomains.map((d) => d.domain))
                  )
                }
                allSelected={filteredDomains.length > 0 && selected.size === filteredDomains.length}
                onClear={(domain) => handleClear([domain])}
                onArchive={(domain) => handleArchive([domain])}
                onUnsubscribe={(domain) => handleUnsubscribe([domain])}
                onBoth={(domain) => handleBoth([domain])}
                onKeep={(domain) => handleKeep([domain])}
                onUnkeep={(domain) => handleUnkeep([domain])}
                onNoUnsub={(domain) => handleNoUnsub([domain])}
                onUnNoUnsub={(domain) => handleUnNoUnsub([domain])}
                onClassifyManual={handleClassifyManual}
                actionLoading={actionLoading}
              />
            )}
          </div>
        </>
      )}

      {/* Auto-archive modal */}
      {showAutoArchive && (
        <AutoArchiveModal
          onClose={() => setShowAutoArchive(false)}
          onApplied={(result) => {
            addToast(
              `Archived ${result.total_archived} emails from ${Object.keys(result.domains).length} domain(s). ${result.newly_blocked.length} added to block list.`
            );
            setShowAutoArchive(false);
            runAudit();
          }}
        />
      )}

      {/* Toasts */}
      <div className="fixed bottom-4 right-4 flex flex-col gap-2 z-50 max-w-sm">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`px-4 py-2.5 rounded shadow-lg text-xs border bg-white ${
              t.type === "success"
                ? "border-emerald-300 text-emerald-800"
                : "border-red-300 text-red-800"
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>
    </div>
  );
}
