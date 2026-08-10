import asyncio
import imaplib
import time
from datetime import date
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ArchiveRequest(BaseModel):
    domains: List[str]
    account_id: int | None = None


class UnsubscribeRequest(BaseModel):
    domains: List[str]
    mode: str = "auto"  # "auto" (one-click POST where available) or "open" (return URL only)
    account_id: int | None = None


class PreferenceRequest(BaseModel):
    domains: List[str]
    account_id: int | None = None


@router.post("/domains/set-auto-archive")
async def set_auto_archive_domains(req: PreferenceRequest):
    """Add domains to archived_domains list (no IMAP operation)."""
    try:
        await asyncio.to_thread(_do_set_auto_archive, req.domains, req.account_id)
        return {"ok": True, "domains": req.domains}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/domains/unset-auto-archive")
async def unset_auto_archive_domains(req: PreferenceRequest):
    """Remove domains from archived_domains list."""
    try:
        await asyncio.to_thread(_do_unset_auto_archive, req.domains, req.account_id)
        return {"ok": True, "domains": req.domains}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/domains/keep")
async def keep_domains(req: PreferenceRequest):
    try:
        await asyncio.to_thread(_do_keep, req.domains, req.account_id)
        return {"ok": True, "domains": req.domains}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/domains/un-keep")
async def un_keep_domains(req: PreferenceRequest):
    try:
        await asyncio.to_thread(_do_un_keep, req.domains, req.account_id)
        return {"ok": True, "domains": req.domains}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/domains/no-unsub")
async def no_unsub_domains(req: PreferenceRequest):
    try:
        await asyncio.to_thread(_do_no_unsub, req.domains, req.account_id)
        return {"ok": True, "domains": req.domains}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/domains/un-no-unsub")
async def un_no_unsub_domains(req: PreferenceRequest):
    try:
        await asyncio.to_thread(_do_un_no_unsub, req.domains, req.account_id)
        return {"ok": True, "domains": req.domains}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/domains/clear")
async def clear_domains(req: ArchiveRequest):
    """One-time inbox removal — does NOT add to archived_domains list."""
    try:
        results = await asyncio.to_thread(_do_archive, req.domains, req.account_id, permanent=False)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/domains/archive")
async def archive_domains(req: ArchiveRequest):
    """Remove from inbox AND add to archived_domains (auto-archive eligibility list)."""
    try:
        results = await asyncio.to_thread(_do_archive, req.domains, req.account_id, permanent=True)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/domains/unsubscribe")
async def unsubscribe_domains(req: UnsubscribeRequest):
    try:
        results = await asyncio.to_thread(_do_unsubscribe, req.domains, req.mode, req.account_id)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _connect_imap(account_id: int | None, inbox: bool = True) -> imaplib.IMAP4_SSL:
    from db import get_default_account_id
    from imap_sync import connect_account
    mail = connect_account(account_id or get_default_account_id())
    if inbox:
        mail.select("INBOX")
    else:
        mail.select('"[Gmail]/All Mail"', readonly=True)
    return mail


def _do_archive(domains: List[str], account_id: int | None, permanent: bool = True) -> list:
    from db import get_default_account_id
    from mass_archive import archive_domain
    if permanent:
        from inbox_audit import append_archived_domains

    account_id = account_id or get_default_account_id()
    mail = _connect_imap(account_id, inbox=True)
    results = []
    newly_archived = []

    for domain in domains:
        try:
            count = archive_domain(mail, domain, dry_run=False)
            results.append({"domain": domain, "success": True, "count": count})
            if count > 0:
                newly_archived.append(domain)
        except Exception as e:
            results.append({"domain": domain, "success": False, "count": 0, "error": str(e)})

    try:
        mail.close()
        mail.logout()
    except Exception:
        pass

    if permanent and newly_archived:
        from constants import config_json_for
        append_archived_domains(newly_archived, config_json_for(account_id))

    # Reflect the archive in the SQLite cache so /api/audit/cached is fresh.
    succeeded_domains = [r["domain"] for r in results if r["success"] and (r["count"] or 0) > 0]
    if succeeded_domains:
        from imap_sync import mark_domains_removed
        try:
            mark_domains_removed(account_id, succeeded_domains)
        except Exception:
            pass  # cache update failure shouldn't fail the archive

    from decision_store import save_decisions_bulk
    decision_state = "archived" if permanent else "seen"
    success_entries = [(r["domain"], decision_state, r["count"]) for r in results if r["success"]]
    if success_entries:
        save_decisions_bulk(success_entries, account_id)

    from events import publish
    publish("domain.archived", {
        "domains": succeeded_domains,
        "permanent": permanent,
        "total_emails": sum((r["count"] or 0) for r in results if r["success"]),
    })

    return results


def _do_unsubscribe(domains: List[str], mode: str, account_id: int | None) -> list:
    from constants import unsub_log_for
    from db import get_default_account_id
    from extract_unsubscribe import extract_unsubscribe_for_domain, post_one_click_unsubscribe
    from inbox_audit import load_unsubscribe_log, save_unsubscribe_log

    account_id = account_id or get_default_account_id()
    log_path = unsub_log_for(account_id)
    mail = _connect_imap(account_id, inbox=False)
    log = load_unsubscribe_log(log_path)
    results = []
    today = date.today().isoformat()

    for domain in domains:
        try:
            info = extract_unsubscribe_for_domain(mail, domain)

            if not info["email_found"]:
                results.append({"domain": domain, "success": False, "error": "No emails found"})
                log[domain] = {"date": today, "method": "none", "status": "no_link", "url": ""}
                continue

            if not info["http_links"]:
                results.append({"domain": domain, "success": False, "error": "No unsubscribe links found"})
                log[domain] = {"date": today, "method": "none", "status": "no_link", "url": ""}
                continue

            url = info["http_links"][0]

            if mode == "auto" and info["one_click"]:
                success = post_one_click_unsubscribe(url)
                results.append({"domain": domain, "success": success, "url": url, "method": "one_click"})
                log[domain] = {"date": today, "method": "one_click", "status": "success" if success else "failed", "url": url}
            else:
                # Return URL for the browser to open
                results.append({"domain": domain, "success": True, "url": url, "method": "browser", "one_click": info["one_click"]})
                log[domain] = {"date": today, "method": "browser", "status": "opened", "url": url}

            time.sleep(0.3)
        except Exception as e:
            results.append({"domain": domain, "success": False, "error": str(e)})

    try:
        mail.close()
        mail.logout()
    except Exception:
        pass

    save_unsubscribe_log(log, log_path)

    from decision_store import save_decisions_bulk
    success_entries = [(r["domain"], "unsub_pending", 0) for r in results if r["success"]]
    if success_entries:
        save_decisions_bulk(success_entries, account_id)

    from events import publish
    publish("domain.unsubscribed", {
        "domains": [r["domain"] for r in results if r["success"]],
        "mode": mode,
    })

    return results


def _do_keep(domains: List[str], account_id: int | None) -> None:
    from config_helper import append_to_preference_list
    from decision_store import save_decisions_bulk
    append_to_preference_list("keep_senders", domains, account_id)
    save_decisions_bulk([(d, "keep", 0) for d in domains], account_id)


def _do_un_keep(domains: List[str], account_id: int | None) -> None:
    from config_helper import remove_from_preference_list
    from decision_store import load_decisions, save_decisions_bulk
    remove_from_preference_list("keep_senders", domains, account_id)
    decisions = load_decisions(account_id)
    revert = [
        (d, "seen", decisions[d]["email_count"])
        for d in domains
        if d in decisions and decisions[d]["state"] == "keep"
    ]
    if revert:
        save_decisions_bulk(revert, account_id)


def _do_no_unsub(domains: List[str], account_id: int | None) -> None:
    from config_helper import append_to_preference_list
    append_to_preference_list("no_unsub", domains, account_id)


def _do_un_no_unsub(domains: List[str], account_id: int | None) -> None:
    from config_helper import remove_from_preference_list
    remove_from_preference_list("no_unsub", domains, account_id)


def _do_set_auto_archive(domains: List[str], account_id: int | None) -> None:
    from config_helper import append_to_preference_list
    from decision_store import save_decisions_bulk
    append_to_preference_list("archived_domains", domains, account_id)
    save_decisions_bulk([(d, "archived", 0) for d in domains], account_id)


def _do_unset_auto_archive(domains: List[str], account_id: int | None) -> None:
    from config_helper import remove_from_preference_list
    from decision_store import load_decisions, save_decisions_bulk
    remove_from_preference_list("archived_domains", domains, account_id)
    decisions = load_decisions(account_id)
    revert = [
        (d, "seen", decisions[d]["email_count"])
        for d in domains
        if d in decisions and decisions[d]["state"] == "archived"
    ]
    if revert:
        save_decisions_bulk(revert, account_id)
