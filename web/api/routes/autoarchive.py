import asyncio
import imaplib
import os
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ApplyRequest(BaseModel):
    threshold: int = 70


@router.get("/autoarchive/plan")
async def get_plan(threshold: int = 70):
    try:
        return await asyncio.to_thread(_do_plan, threshold)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/autoarchive/apply")
async def apply_plan(req: ApplyRequest):
    try:
        return await asyncio.to_thread(_do_apply, req.threshold)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _do_plan(threshold: int) -> dict:
    from sender_audit import fetch_unread_senders
    from inbox_audit import load_config_for_classifier, load_archived_domains, classify_domains
    from auto_archive import build_archive_plan
    from mass_archive import archive_domain

    config = load_config_for_classifier()
    archived_set = set(load_archived_domains())

    # Always scan ALL inbox mail (read + unread) — auto-archive cleans the inbox
    # regardless of read status, and archived_domain slip-throughs are often already read.
    _, domain_counter, _, total, domain_emails = fetch_unread_senders(
        include_subjects=True, unseen_only=False
    )
    classifications = classify_domains(domain_emails, config)
    to_archive, to_skip = build_archive_plan(dict(domain_counter), classifications, archived_set, threshold)

    # Replace fetched counts with a dry-run archive search so the plan shows exactly
    # how many emails will be removed per domain.
    if to_archive:
        user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
        password = os.environ.get("GMAIL_APP_PASSWORD", "")
        if password:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(user, password)
            mail.select("INBOX", readonly=True)
            for entry in to_archive:
                entry["count"] = archive_domain(mail, entry["domain"], dry_run=True)
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass

    return {
        "dry_run": True,
        "total_unread": total,
        "threshold": threshold,
        "to_archive": to_archive,
        "to_skip": to_skip,
    }


def _do_apply(threshold: int) -> dict:
    from sender_audit import fetch_unread_senders
    from inbox_audit import (
        load_config_for_classifier,
        load_archived_domains,
        classify_domains,
        append_archived_domains,
    )
    from auto_archive import build_archive_plan
    from mass_archive import archive_domain

    config = load_config_for_classifier()
    archived_set = set(load_archived_domains())

    _, domain_counter, _, total, domain_emails = fetch_unread_senders(
        include_subjects=True, unseen_only=False
    )
    classifications = classify_domains(domain_emails, config)
    to_archive, _ = build_archive_plan(dict(domain_counter), classifications, archived_set, threshold)

    if not to_archive:
        return {"total_archived": 0, "domains": {}, "newly_blocked": []}

    user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not password:
        raise RuntimeError("GMAIL_APP_PASSWORD not set")

    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(user, password)
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
        append_archived_domains(newly_blocked)

    return {
        "total_archived": sum(archived_counts.values()),
        "domains": archived_counts,
        "newly_blocked": newly_blocked,
    }
