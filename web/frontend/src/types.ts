export type CategoryName =
  | "receipt"
  | "newsletter"
  | "promotion"
  | "notification"
  | "unknown";

export type SuggestedAction = "keep" | "review" | "archive";

export interface EmailSample {
  sender: string;
  subject: string;
}

export interface Classification {
  category: CategoryName;
  confidence: number;
  tier: "high" | "medium" | "low" | null;
  reasoning: string;
  suggested_action: SuggestedAction;
  source?: "manual" | "llm" | "programmatic";
}

export type DecisionState = "seen" | "keep" | "archived" | "unsub_pending" | "recidivist";

export interface DomainDecision {
  state: DecisionState;
  decided_at: string;   // YYYY-MM-DD
  email_count: number;  // inbox count at time of decision
}

export interface Domain {
  domain: string;
  count: number;
  emails: EmailSample[];
  classification: Classification | null;
  archived: boolean;
  keep: boolean;
  no_unsub: boolean;
  unsubscribed_date: string | null;
  decision: DomainDecision | null;
}

export interface AuditResult {
  total_unread: number;
  domains: Domain[];
  last_synced_at?: string | null;
}

export interface Job {
  id: number;
  account_id: number | null;
  kind: string;
  status: "pending" | "running" | "done" | "error" | "interrupted";
  progress_total: number;
  progress_done: number;
  phase: string | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  params: Record<string, unknown> | null;
  result: unknown;
}

export interface SyncReport {
  account_id: number;
  mailbox: string;
  full_resync: boolean;
  total_in_mailbox: number;
  new_messages: number;
  seen_state_changed: number;
  removed: number;
  elapsed_ms: number;
  uidvalidity: number | null;
  last_uid: number;
}

export interface LlmStatus {
  up: boolean | null;
  model: string | null;
  warming_up: boolean;
  last_latency_ms: number | null;
  last_checked: number;
  error: string | null;
  base_url: string;
}

export interface AutoArchiveEntry {
  domain: string;
  count: number;
  reason: string;
  confidence: number;
  category: string;
}

export interface AutoArchivePlan {
  dry_run: boolean;
  total_unread: number;
  threshold: number;
  to_archive: AutoArchiveEntry[];
  to_skip: AutoArchiveEntry[];
}

export interface ApplyResult {
  total_archived: number;
  domains: Record<string, number>;
  newly_blocked: string[];
}

export interface ClassifyResult {
  classified: number;
  results: Record<string, Classification>;
}

export interface ActionResult {
  domain: string;
  success: boolean;
  count?: number;
  url?: string;
  method?: string;
  one_click?: boolean;
  error?: string;
}
