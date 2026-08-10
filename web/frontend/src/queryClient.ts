import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// Single source of truth for query keys so SSE handlers can invalidate them.
// accountId is threaded through every account-scoped key so switching accounts
// never shows another mailbox's cached data.
export const qk = {
  accounts: () => ["accounts"] as const,
  audit: (unseenOnly: boolean, accountId: number | null) => ["audit", { unseenOnly, accountId }] as const,
  decisions: (accountId: number | null) => ["decisions", { accountId }] as const,
  decisionsSummary: (accountId: number | null) => ["decisions", "summary", { accountId }] as const,
  llmStatus: () => ["llm", "status"] as const,
  job: (id: number) => ["job", id] as const,
  latestJob: (kind: string) => ["job", "latest", kind] as const,
};
