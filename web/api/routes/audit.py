"""Audit endpoint — reads from the SQLite cache and rolls up by domain.

Cache write happens via `imap_sync.sync_inbox` (called explicitly via /api/sync
or implicitly by /api/audit when force=True). Reads are cheap and local.
"""
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class SyncRequest(BaseModel):
    full_resync: bool = False


@router.post("/sync")
async def run_sync(req: SyncRequest):
    """Pull new IMAP UIDs into the cache. Fast in steady state, slow on first run."""
    try:
        from db import get_default_account_id
        from imap_sync import sync_inbox
        account_id = get_default_account_id()
        rep = await asyncio.to_thread(sync_inbox, account_id, req.full_resync)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/audit")
async def run_audit(unseen_only: bool = True, force: bool = False):
    """Sync inbox if needed, then return the rolled-up audit view from cache."""
    try:
        from db import get_default_account_id
        from imap_sync import sync_inbox
        account_id = get_default_account_id()
        if force:
            await asyncio.to_thread(sync_inbox, account_id)
        else:
            # Light sync — picks up new mail since the cache was last refreshed.
            await asyncio.to_thread(sync_inbox, account_id)
        return await asyncio.to_thread(_build_audit_view, account_id, unseen_only)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/cached")
async def get_cached_audit(unseen_only: bool = True):
    """Pure cache read — no IMAP traffic. Returns 404 if cache empty."""
    try:
        from db import get_conn, get_default_account_id
        account_id = get_default_account_id()
        row = get_conn().execute(
            "SELECT COUNT(*) FROM messages WHERE account_id=? AND in_inbox=1",
            (account_id,),
        ).fetchone()
        if row[0] == 0:
            raise HTTPException(status_code=404, detail="Cache empty — POST /api/sync first.")
        return await asyncio.to_thread(_build_audit_view, account_id, unseen_only)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _build_audit_view(account_id: int, unseen_only: bool) -> dict:
    """Roll up the cached INBOX rows the same way the old endpoint did."""
    from imap_sync import list_inbox_domains
    from inbox_audit import (
        load_config_for_classifier,
        load_archived_domains,
        load_unsubscribe_log,
        classify_domains,
    )
    from config_helper import load_preference_list
    from decision_store import load_decisions, save_decisions_bulk

    config = load_config_for_classifier()
    lp = config.get("learned_preferences", {})

    archived_set = set(load_archived_domains())
    keep_set = set(lp.get("keep_senders", []))
    no_unsub_set = set(load_preference_list("no_unsub"))
    unsub_log = load_unsubscribe_log()
    decisions = load_decisions()

    rollup = list_inbox_domains(account_id, unseen_only=unseen_only)
    classifications = classify_domains(rollup["domain_emails"], config)

    domains_out = []
    for domain, count in rollup["domain_counter"].most_common():
        emails_list = rollup["domain_emails"].get(domain, [])
        cls = classifications.get(domain)
        unsub_entry = unsub_log.get(domain)
        decision = decisions.get(domain)

        domains_out.append(
            {
                "domain": domain,
                "count": count,
                "emails": [
                    {"sender": e.get("sender", ""), "subject": e.get("subject", "")}
                    for e in emails_list[:5]
                ],
                "classification": cls.to_dict() if cls else None,
                "archived": domain in archived_set,
                "keep": domain in keep_set,
                "no_unsub": domain in no_unsub_set,
                "unsubscribed_date": unsub_entry.get("date") if unsub_entry else None,
                "decision": decision,
            }
        )

    # Auto-transition unsub_pending → recidivist for domains still in inbox
    recidivist_transitions = [
        (entry["domain"], "recidivist", entry["count"])
        for entry in domains_out
        if entry["decision"] and entry["decision"]["state"] == "unsub_pending"
    ]
    if recidivist_transitions:
        save_decisions_bulk(recidivist_transitions)
        recidivist_set = {d for d, _, _ in recidivist_transitions}
        for entry in domains_out:
            if entry["domain"] in recidivist_set:
                entry["decision"] = {**entry["decision"], "state": "recidivist"}

    return {
        "total_unread": rollup["total"],
        "last_synced_at": rollup["last_synced_at"],
        "domains": domains_out,
    }
