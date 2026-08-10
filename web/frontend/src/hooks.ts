import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { qk } from "./queryClient";
import type { Account, AuditResult, Job, LlmStatus } from "./types";

export function useAccounts() {
  return useQuery<Account[]>({
    queryKey: qk.accounts(),
    queryFn: () => api.getAccounts(),
    staleTime: 60_000,
  });
}

/** Cached audit (no IMAP roundtrip). Hydrates instantly from /api/audit/cached. */
export function useAudit(unseenOnly: boolean, accountId: number | null) {
  return useQuery<AuditResult>({
    queryKey: qk.audit(unseenOnly, accountId),
    queryFn: () => api.getCachedAuditUnseen(unseenOnly, accountId ?? undefined),
    enabled: accountId != null,
    staleTime: 60_000,
    retry: false,
  });
}

export function useDecisions(accountId: number | null) {
  return useQuery({
    queryKey: qk.decisions(accountId),
    queryFn: () => api.getDecisions(accountId ?? undefined),
    enabled: accountId != null,
  });
}

export function useLlmStatus() {
  return useQuery<LlmStatus>({
    queryKey: qk.llmStatus(),
    queryFn: () => api.llmStatus(true),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

/** Poll a specific job until it reaches a terminal state. */
export function useJob(id: number | null | undefined) {
  return useQuery<Job>({
    queryKey: qk.job(id ?? -1),
    queryFn: () => api.getJob(id as number),
    enabled: id != null,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 1000;
      return data.status === "running" || data.status === "pending" ? 1000 : false;
    },
  });
}

/** Latest job of a given kind — useful for hydrating UI on mount. */
export function useLatestJob(kind: string) {
  return useQuery<Job | null>({
    queryKey: qk.latestJob(kind),
    queryFn: async () => {
      try {
        return await api.getLatestJob(kind);
      } catch {
        return null;
      }
    },
  });
}

// ── Mutations ──────────────────────────────────────────────────────────────

export function useEnqueueJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, params }: { kind: string; params?: Record<string, unknown> }) =>
      api.enqueueJob(kind, params ?? {}),
    onSuccess: (data) => {
      qc.setQueryData(qk.latestJob(data.kind), { id: data.id, kind: data.kind });
    },
  });
}

export function useSyncInbox() {
  return useMutation({
    mutationFn: ({ full, accountId }: { full: boolean; accountId?: number }) =>
      api.syncInbox(full, accountId),
  });
}
