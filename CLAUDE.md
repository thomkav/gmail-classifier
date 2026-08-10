# Gmail Classifier — CLAUDE.md

## What This Is

A Claude Code plugin for inbox management. Connects to Gmail via IMAP, audits senders, archives bulk mail, and manages unsubscribes. Lives at `~/.claude/plugins/gmail-classifier/` (this repo is symlinked/copied there).

**Auth**: Gmail app passwords live in the `gmail-classifier` 1Password vault (`my.1password.com` account), one login item per account. `task` targets inject them via `op run --account my.1password.com --env-file=.env.op -- <cmd>` (see `.env.op` at repo root for the `op://` references — safe to commit, no secret values). Multi-account: `web/api/db.py`'s `accounts` table maps each account to its own `GMAIL_APP_PASSWORD_<SLUG>` var; `.env.op` also carries a legacy unsuffixed `GMAIL_APP_PASSWORD`/`GMAIL_EMAIL` pair (pointed at the default account, `thomkav@gmail.com`) for the older `scripts/*.py` CLI tools that predate multi-account support.

**Primary interface**: web app (`task web`). The interactive TUI (`scripts/inbox_audit.py`) is being deprecated — use the web UI for archive/unsubscribe flows.

**Workflow runner**: `task` (Taskfile.yml). The Makefile is a thin shim during migration; do not add new targets there.

---

## Directory Map

```
scripts/
  sender_audit.py       # Fetch FROM headers for all unread → top senders/domains JSON
  inbox_audit.py        # Interactive TUI: classify → archive → unsubscribe flow
  mass_archive.py       # Mark read + archive all emails from a domain list
  extract_unsubscribe.py # Extract List-Unsubscribe links; --auto (RFC 8058 POST), --open (browser)
  classify_logic.py     # EmailClassifier class: receipt/newsletter/promotion/notification/unknown
  cli_ui.py             # ANSI color helpers, tables, progress bars
  preference_learner.py # (minimal) preference update helpers

commands/               # Claude slash commands: /classify, /review-suggestions, /organize-config, /auto-archive
agents/                 # email-organizer agent
skills/                 # email-organization skill
.local.md               # Config + state: categories, learned_preferences, archived_domains
.unsubscribe_log.json   # Machine-managed: {domain: {date, method, status, url}}
data/                   # SQLite cache (gitignored): gmail_classifier.sqlite
Taskfile.yml            # Canonical workflow runner — `task --list` for menu
Makefile                # Thin shim forwarding to `task` (deprecated)
web/api/                # FastAPI backend (port 8000)
web/frontend/           # React + Vite frontend (port 5173)
```

---

## State Files

### `.local.md` (human-edited YAML frontmatter)
- `archived_domains`: domains to archive/ignore — **grows over time**, currently 100+ entries across dated rounds
- `learned_preferences.keep_senders`: bypass classification entirely
- `learned_preferences.keep_newsletters`: always keep in inbox
- `categories`: receipt/newsletter/promotion pattern config

### `.unsubscribe_log.json` (machine-managed)
- Tracks unsubscribe attempts per domain: `{date, method, status, url}`
- `status` values: `success` (one-click POST worked), `opened` (browser opened), `failed`, `no_link`
- Currently sparse — only 4 entries, all `no_link` — so recidivist tracking is weak

---

## Task targets

```bash
task --list                 # full menu
task web                    # API on :8000 + frontend on :5173
task web:api                # backend only
task web:frontend           # frontend only
task audit:quick            # JSON snapshot (no UI, no actions)
task auto-archive:dry-run   # preview the auto-archive plan
task auto-archive:apply     # apply it
task db:migrate             # apply SQLite schema migrations
task recidivists            # report ignored-unsubscribe domains
```

Always use `task` targets, not raw `python3` calls — they source `~/.zsh_secrets`.

---

## Key Scripts

### `sender_audit.py`
- IMAP → INBOX UNSEEN → batch fetch FROM headers
- Returns JSON: `{total_unread, top_senders[50], top_domains[50]}`
- Called by `inbox_audit.py` internally via import

### `inbox_audit.py`
Full TUI flow:
1. Fetch unread senders (with subjects)
2. Classify domains → group by category (receipt/newsletter/promotion/notification/unknown)
3. Dashboard → select category → domain table with status markers
4. Actions: [a]rchive, [u]nsubscribe, [b]oth
5. Archive: calls `mass_archive.archive_domain()`, adds archived domains to `archived_domains` in `.local.md`
6. Unsubscribe: calls `extract_unsubscribe_for_domain()`, saves to `.unsubscribe_log.json`
7. Status markers: `[blocked]` (in archived_domains), `[unsub'd MM-DD]` (in unsub log), `*` (new/unprocessed)

### `extract_unsubscribe.py`
- Searches All Mail for most recent email from domain
- Tries `List-Unsubscribe` header first, falls back to HTML body link scan
- `--auto`: HTTP POST to one-click URL (RFC 8058)
- `--open`: open in browser
- Logs results to `.unsubscribe_log.json`

### `auto_archive.py`
Non-interactive pipeline for bulk cleanup:
1. Fetches all unread senders (with subjects)
2. Classifies every domain via `classify_logic.py`
3. Auto-archives: archived_domains (re-archive), promotions ≥ threshold%, low-quality newsletters
4. Skips: receipts, notifications, keep_senders, unknown/low confidence
- `--dry-run` (default): print plan table, no inbox changes
- `--apply`: archive + update `archived_domains` in `.local.md`
- `--threshold=N`: confidence cutoff (default 70)
- `--json`: machine-readable output for Claude to parse
- Entry point: `/auto-archive` command

### `classify_logic.py`
`EmailClassifier.classify(email)` — priority order:
1. `learned_preferences` (keep_senders → keep_newsletters → archive_newsletters → archived_domains)
2. Personal/conversational detection (re: threads, non-automated senders)
3. Notification (security alerts, account notices)
4. Receipt / Newsletter / Promotion (pattern matching + confidence scoring)

---

## Common Workflows

| Task | Command |
|------|---------|
| Quick inbox snapshot | `make audit-email-quick` |
| Full interactive audit | `make audit-email` |
| Auto-archive inbox (agent) | `/auto-archive` → agent runs dry-run, presents summary, confirms, applies |
| Auto-archive (CLI dry run) | `make auto-archive-dry-run` |
| Auto-archive (CLI apply) | `make auto-archive` |
| Unsubscribe from specific domains | `python3 scripts/extract_unsubscribe.py --auto domain1 domain2` |
| Mass archive domains | `python3 scripts/mass_archive.py domain1 domain2` (add `--dry-run` first) |

---

## Known Gaps / Improvement Areas

- **Recidivist tracking**: `.unsubscribe_log.json` is not cross-referenced against incoming mail. We have no automated way to detect "I unsubscribed from X but they're still emailing me." This requires: checking if a domain appears in the inbox AND has a prior `success`/`opened` unsubscribe log entry.
- **Unsubscribe log sparseness**: Most unsubscribes happen via `inbox_audit.py` browser flow, but the log only has 4 entries. The `archived_domains` list is the de facto record of "dealt with" senders.
- **Makefile coverage**: `auto-archive` and `auto-archive-dry-run` now added. No target for mass-unsubscribe yet.
