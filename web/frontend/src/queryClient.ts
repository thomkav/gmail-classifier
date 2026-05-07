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
export const qk = {
  audit: (unseenOnly: boolean) => ["audit", { unseenOnly }] as const,
  decisions: () => ["decisions"] as const,
  decisionsSummary: () => ["decisions", "summary"] as const,
  llmStatus: () => ["llm", "status"] as const,
  job: (id: number) => ["job", id] as const,
  latestJob: (kind: string) => ["job", "latest", kind] as const,
};
