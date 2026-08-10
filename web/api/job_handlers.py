"""Handlers for each registered job kind.

Imported for side effects from main.py — the @register decorator wires each
function into the jobs module's dispatch table.
"""
from __future__ import annotations

from jobs import register, JobContext


# ── sync ───────────────────────────────────────────────────────────────────


@register("sync")
def _h_sync(job_id: int, params: dict, ctx: JobContext) -> dict:
    from db import get_default_account_id
    from imap_sync import sync_inbox

    account_id = params.get("account_id") or get_default_account_id()
    full_resync = bool(params.get("full_resync", False))

    def progress_fn(phase: str, done: int, total: int) -> None:
        ctx.progress(done, total, phase)

    rep = sync_inbox(account_id, full_resync=full_resync, progress_fn=progress_fn)
    return {
        "account_id": rep.account_id,
        "mailbox": rep.mailbox,
        "full_resync": rep.full_resync,
        "total_in_mailbox": rep.total_in_mailbox,
        "new_messages": rep.new_messages,
        "seen_state_changed": rep.seen_state_changed,
        "removed": rep.removed,
        "elapsed_ms": rep.elapsed_ms,
        "uidvalidity": rep.uidvalidity,
        "last_uid": rep.last_uid,
    }


# ── classify (LLM) ─────────────────────────────────────────────────────────


@register("classify")
def _h_classify(job_id: int, params: dict, ctx: JobContext) -> dict:
    from db import get_default_account_id
    from routes.audit import _build_audit_view
    from llm_classifier import classify_domains_llm

    _CATEGORY_DEFAULT_ACTION = {
        "newsletter": "review",
        "promotion": "archive",
        "receipt": "archive",
        "notification": "keep",
        "personal": "keep",
        "unknown": "review",
    }

    account_id = params.get("account_id") or get_default_account_id()
    unseen_only = bool(params.get("unseen_only", True))
    cache = _build_audit_view(account_id, unseen_only)

    unknown_domains = [
        d for d in cache["domains"]
        if not d.get("classification") or d["classification"]["category"] == "unknown"
    ]
    domain_subjects = {
        d["domain"]: [e["subject"] for e in d.get("emails", []) if e.get("subject")]
        for d in unknown_domains
    }

    total = len(domain_subjects)
    ctx.progress(0, total, "classifying", force=True)
    if total == 0:
        return {"classified": 0, "results": {}}

    # Surface "warming up" state so UI can show a hint while MLX cold-starts.
    from llm_classifier import signal_warming, check_status
    status = check_status(probe=True)
    if not status.get("up") or status.get("last_latency_ms") is None:
        signal_warming()

    completed = 0

    def on_batch_done(batch_results: dict):
        nonlocal completed
        completed += len(batch_results)
        ctx.progress(completed, total, "classifying")

    raw = classify_domains_llm(domain_subjects, on_batch_done=on_batch_done, account_id=account_id)

    results = {}
    for domain, r in raw.items():
        category = r.get("category", "unknown")
        results[domain] = {
            "category": category,
            "confidence": r.get("confidence", 0),
            "reasoning": r.get("reasoning", ""),
            "tier": None,
            "suggested_action": _CATEGORY_DEFAULT_ACTION.get(category, "review"),
            "source": "llm",
        }

    newly_classified = sum(1 for r in results.values() if r["category"] != "unknown")
    return {"classified": newly_classified, "results": results}


# ── auto-archive apply ─────────────────────────────────────────────────────


@register("auto_archive_apply")
def _h_auto_archive(job_id: int, params: dict, ctx: JobContext) -> dict:
    from routes.autoarchive import _do_apply
    threshold = int(params.get("threshold", 70))
    account_id = params.get("account_id")
    ctx.progress(0, 1, "starting", force=True)
    result = _do_apply(threshold, account_id)
    ctx.progress(1, 1, "done", force=True)
    return result
