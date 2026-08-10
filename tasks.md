# Gmail Classifier — Maturity Upgrade Plan

Tracking the holistic upgrade: persistent state, process resilience, real-time UI,
`task` CLI workflows, and groundwork for multi-account.

Status legend: ☐ pending · ◐ in progress · ☑ done · ⊘ deferred

---

## T1 ☐ Migrate Make → Taskfile (`task` CLI)

Replace `Makefile` with `Taskfile.yml`. Mirror existing targets, add `web:*` group,
mark TUI targets `deprecated:` namespace.

**Outputs:** `Taskfile.yml`, updated `README.md`, `CLAUDE.md`. Keep `Makefile`
as thin shim invoking `task` for one cycle, then delete in T7.

---

## T2 ☐ SQLite cache + IMAP UID incremental sync

The hot path today re-fetches FROM/Subject for every unread message on every audit.
With SQLite + IMAP UID semantics we keep that data and only fetch newly-arrived UIDs.

- `web/api/db.py` — connection helper, schema migrations
- Schema:
  - `accounts(id, email, created_at)`
  - `mailbox_state(account_id, mailbox, uidvalidity, last_uid, updated_at)` — per-mailbox sync cursor
  - `messages(account_id, uidvalidity, uid, mailbox, sender, sender_addr, domain, subject, internal_date, flags, fetched_at, removed_at)`
  - `jobs(...)` — see T3
- Sync algorithm:
  1. SELECT mailbox; if `UIDVALIDITY` mismatched → wipe and full resync
  2. `UID SEARCH UID <last_uid+1>:*` → only new messages
  3. Periodic (or on-demand) `UID SEARCH 1:* UNSEEN` to detect read-state changes for cached rows
- Audit endpoint reads from SQLite, not from a fresh IMAP scan; re-sync is a separate explicit action (or a job).

**DB location:** `gmail-classifier/data/gmail_classifier.sqlite` (gitignored).

---

## T3 ☐ Persisted jobs layer

Replace ad-hoc module globals (`routes/audit.py::_cache`,
`routes/classify.py::_progress`) with persisted jobs.

- `jobs(id, kind, status, progress_total, progress_done, started_at, finished_at, result_json, error)`
- `kinds`: `audit`, `classify`, `auto_archive_plan`, `auto_archive_apply`, `unsubscribe`
- API:
  - `POST /api/jobs/audit` → `{job_id}` (kicks off in background thread)
  - `GET  /api/jobs/{id}` → status, progress, result if done
  - `GET  /api/jobs?kind=audit&latest=1` → most recent of a kind
- Old endpoints (`/audit`, `/classify/unknown`) become thin wrappers that create a job and return its id.
- Survives server restart: on startup, mark `running` jobs as `interrupted` so UI can show "needs retry".

---

## T4 ☐ LLM process management

`web/api/llm_classifier.py` currently:
- Hardcodes 45s timeout, no health check, no concurrency control, raw `urllib`
- A second classify request will overlap and double-load the MLX subprocess

Improvements:
- `/api/llm/status` — `{up, model, warming_up, last_latency_ms}` polling endpoint
- Module-level `asyncio.Semaphore(1)` (or threading.Semaphore) so only one batch is in-flight
- Configurable timeout (env `LLM_TIMEOUT`, default 60s)
- Exponential backoff on 5xx/timeout (3 retries, jitter)
- "Warming up" detection: first request after idle hits a longer timeout and emits `llm.warming` SSE
- Surface model identity in API response so UI shows which tier ran the classify

---

## T5 ☐ SSE event stream

Single `/api/events` Server-Sent Events endpoint, in-memory pub/sub broker.

Events emitted:
- `job.created`, `job.progress`, `job.done`, `job.error`
- `audit.delta` (when sync finds new messages)
- `llm.status` (warming up, idle, errored)
- `domain.archived`, `domain.unsubscribed`, `decision.changed`

Frontend subscribes once on mount and routes events to local state /
TanStack Query cache invalidation.

---

## T6 ☐ Frontend state restoration & TanStack Query

- Add `@tanstack/react-query`
- Queries:
  - `useAudit()` → `/api/audit/cached` (now backed by SQLite)
  - `useDecisions()`, `useLlmStatus()`, `useJob(id)`
- SSE event handler invalidates relevant query keys
- App.tsx shrinks dramatically (manual setState plumbing → query mutations)

---

## T7 ☐ Deprecate TUI scripts

After web parity verified end-to-end:
- Extract pure helpers from `scripts/inbox_audit.py`
  (`load_config_for_classifier`, `load_archived_domains`, `classify_domains`,
  `append_archived_domains`, `load_unsubscribe_log`, `save_unsubscribe_log`)
  into `scripts/email_state.py` (a non-TUI module)
- Delete:
  - `scripts/inbox_audit.py` (interactive entry)
  - `scripts/cli_ui.py`
  - `audit-email` task target
- Update API imports

Keep as library: `sender_audit.py`, `mass_archive.py`, `extract_unsubscribe.py`,
`auto_archive.py`, `classify_logic.py`, new `email_state.py`.

---

## T8 ☐ Multi-account groundwork

Even before OAuth, plumb `account_id` everywhere so swapping is additive.
- `accounts(id, email, created_at, last_synced_at, default INTEGER)`
- Single seed row on first migration: `(1, $GMAIL_EMAIL, ..., 1)`
- `current_account` dependency injection in FastAPI; reads from request header
  `X-Account-Id` or falls back to default
- All new tables FK to `accounts(id)`

OAuth + UI account switcher: deferred (later PR).

---

## Order of execution

Recommended sequence (lowest blast radius first):

1. **T1** Taskfile (warmup)
2. **T2** SQLite + UID sync (unblocks everything)
3. **T3** Jobs layer
4. **T4** LLM hardening
5. **T5** SSE
6. **T6** Frontend rewire
7. **T7** TUI deprecation
8. **T8** Multi-account groundwork (interleaved with T2 schema)
