import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { BASE } from "./api";
import { qk } from "./queryClient";

export interface AppEvent {
  kind: string;
  [k: string]: unknown;
}

/**
 * Subscribe to /api/events and route incoming events to React Query cache
 * invalidations. Also exposes a hook for component-level reactivity.
 *
 * Reconnects with exponential backoff if the stream drops.
 */
export function useEventStream(onEvent?: (e: AppEvent) => void): void {
  const qc = useQueryClient();
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    let es: EventSource | null = null;
    let cancelled = false;
    let backoff = 500;

    const connect = () => {
      if (cancelled) return;
      es = new EventSource(`${BASE}/api/events`);

      es.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data) as AppEvent;
          handlerRef.current?.(event);

          switch (event.kind) {
            case "domain.archived":
            case "domain.unsubscribed":
              qc.invalidateQueries({ queryKey: ["audit"] });
              qc.invalidateQueries({ queryKey: ["decisions"] });
              break;
            case "job.done": {
              const k = (event as Record<string, unknown>).job_kind as string | undefined;
              if (k === "sync") qc.invalidateQueries({ queryKey: ["audit"] });
              if (k === "classify") qc.invalidateQueries({ queryKey: ["audit"] });
              if (k === "auto_archive_apply") {
                qc.invalidateQueries({ queryKey: ["audit"] });
                qc.invalidateQueries({ queryKey: ["decisions"] });
              }
              break;
            }
            case "llm.status":
              qc.setQueryData(qk.llmStatus(), event);
              break;
          }
        } catch {
          /* malformed event — ignore */
        }
      };

      es.onopen = () => {
        backoff = 500;
      };

      es.onerror = () => {
        es?.close();
        es = null;
        if (!cancelled) {
          setTimeout(connect, backoff);
          backoff = Math.min(backoff * 2, 15_000);
        }
      };
    };

    connect();
    return () => {
      cancelled = true;
      es?.close();
    };
  }, [qc]);
}
