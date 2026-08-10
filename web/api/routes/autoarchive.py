import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Dry-run counts require one IMAP search per candidate domain. Gmail's concurrent
# connection cap is shared with every other client on the account (Mail app, phone,
# browser tab, sync) — stay modest, and degrade gracefully rather than fail the
# whole plan if a batch can't get a connection.
_DRY_RUN_WORKERS = 4


def _dry_run_counts(account_id: int, domains: list[str]) -> dict[str, int]:
    """Exact per-domain INBOX counts via a small pool of IMAP connections, each
    reused across its whole batch — one login per worker, not per domain. A
    batch that fails (e.g. Gmail's connection limit) is dropped, not raised —
    callers fall back to the already-fetched estimate for those domains."""
    from imap_sync import connect_account
    from mass_archive import archive_domain

    n_workers = min(_DRY_RUN_WORKERS, len(domains) or 1)
    batches = [domains[i::n_workers] for i in range(n_workers)]
    results: dict[str, int] = {}

    def worker(batch: list[str]) -> dict[str, int]:
        try:
            mail = connect_account(account_id)
        except Exception as e:
            print(f"[autoarchive] dry-run batch connect failed, falling back to estimates: {e}")
            return {}
        try:
            mail.select("INBOX", readonly=True)
            out = {}
            for domain in batch:
                try:
                    out[domain] = archive_domain(mail, domain, dry_run=True)
                except Exception as e:
                    print(f"[autoarchive] dry-run search failed for {domain}, using estimate: {e}")
            return out
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        for batch_result in pool.map(worker, batches):
            results.update(batch_result)

    return results


class ApplyRequest(BaseModel):
    threshold: int = 70
    account_id: int | None = None


@router.get("/autoarchive/plan")
async def get_plan(threshold: int = 70, account_id: int | None = None):
    try:
        return await asyncio.to_thread(_do_plan, threshold, account_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/autoarchive/apply")
async def apply_plan(req: ApplyRequest):
    try:
        return await asyncio.to_thread(_do_apply, req.threshold, req.account_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _do_plan(threshold: int, account_id: int | None = None) -> dict:
    from constants import config_json_for
    from db import get_default_account_id
    from sender_audit import fetch_unread_senders
    from inbox_audit import load_config_for_classifier, load_archived_domains, classify_domains
    from auto_archive import build_archive_plan

    account_id = account_id or get_default_account_id()
    config_path = config_json_for(account_id)
    config = load_config_for_classifier(config_path)
    archived_set = set(load_archived_domains(config_path))

    # Always scan ALL inbox mail (read + unread) — auto-archive cleans the inbox
    # regardless of read status, and archived_domain slip-throughs are often already read.
    _, domain_counter, _, total, domain_emails = fetch_unread_senders(
        include_subjects=True, unseen_only=False
    )
    classifications = classify_domains(domain_emails, config)
    to_archive, to_skip = build_archive_plan(dict(domain_counter), classifications, archived_set, threshold)

    # Replace fetched counts with a dry-run archive search (parallel IMAP
    # connections) so the plan shows exactly how many emails will be removed
    # per domain, without paying 150ms+ x len(to_archive) sequentially.
    if to_archive:
        counts = _dry_run_counts(account_id, [entry["domain"] for entry in to_archive])
        for entry in to_archive:
            entry["count"] = counts.get(entry["domain"], entry["count"])

    return {
        "dry_run": True,
        "total_unread": total,
        "threshold": threshold,
        "to_archive": to_archive,
        "to_skip": to_skip,
    }


def _do_apply(threshold: int, account_id: int | None = None) -> dict:
    from constants import config_json_for
    from db import get_default_account_id
    from imap_sync import connect_account
    from sender_audit import fetch_unread_senders
    from inbox_audit import (
        load_config_for_classifier,
        load_archived_domains,
        classify_domains,
        append_archived_domains,
    )
    from auto_archive import build_archive_plan
    from mass_archive import archive_domain

    account_id = account_id or get_default_account_id()
    config_path = config_json_for(account_id)
    config = load_config_for_classifier(config_path)
    archived_set = set(load_archived_domains(config_path))

    _, domain_counter, _, total, domain_emails = fetch_unread_senders(
        include_subjects=True, unseen_only=False
    )
    classifications = classify_domains(domain_emails, config)
    to_archive, _ = build_archive_plan(dict(domain_counter), classifications, archived_set, threshold)

    if not to_archive:
        return {"total_archived": 0, "domains": {}, "newly_blocked": []}

    mail = connect_account(account_id)
    mail.select("INBOX")

    archived_counts: dict[str, int] = {}
    newly_blocked: list[str] = []

    for entry in to_archive:
        domain = entry["domain"]
        count = archive_domain(mail, domain, dry_run=False)
        archived_counts[domain] = count
        if count > 0 and domain not in archived_set:
            newly_blocked.append(domain)
        if count > 0:
            time.sleep(0.3)

    try:
        mail.close()
        mail.logout()
    except Exception:
        pass

    if newly_blocked:
        append_archived_domains(newly_blocked, config_path)

    return {
        "total_archived": sum(archived_counts.values()),
        "domains": archived_counts,
        "newly_blocked": newly_blocked,
    }
