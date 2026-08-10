"""Incremental IMAP → SQLite sync.

The point of this module is that *we never want to re-fetch a message header twice*.
IMAP UIDs are stable within a `UIDVALIDITY` epoch, so we keep a per-mailbox cursor
(last_uid) and only fetch UIDs above it. We also reconcile read-state for cached
messages so the UI knows when the user has already read something.

Public surface:
    sync_inbox(account_id, full_resync=False) -> SyncReport
    list_inbox_domains(account_id) -> list[dict]   # roll-up for the audit endpoint

The IMAP connection is opened/closed per sync; we don't pool yet.
"""
from __future__ import annotations

import email
import email.utils
import imaplib
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable

from db import get_conn, get_account, get_account_password, transaction

INBOX = "INBOX"
DEFAULT_BATCH = 200
SUBJECT_SAMPLE_PER_DOMAIN = 5  # how many recent subjects to surface per domain


@dataclass
class SyncReport:
    account_id: int
    mailbox: str
    full_resync: bool
    total_in_mailbox: int
    new_messages: int
    seen_state_changed: int
    removed: int
    elapsed_ms: int
    uidvalidity: int | None = None
    last_uid: int = 0
    error: str | None = None


# ── IMAP plumbing ──────────────────────────────────────────────────────────


def connect_account(account_id: int) -> imaplib.IMAP4_SSL:
    """Open an authenticated IMAP connection for the given account. Shared by
    every module that needs live IMAP access (sync, archive, unsubscribe, autoarchive)."""
    acct = get_account(account_id)
    if acct is None:
        raise RuntimeError(f"unknown account_id={account_id}")
    password = get_account_password(account_id)
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(acct["email"], password)
    return mail


def _select_inbox(mail: imaplib.IMAP4_SSL) -> int:
    """Select INBOX (read-only) and return UIDVALIDITY."""
    typ, data = mail.status(INBOX, "(UIDVALIDITY)")
    if typ != "OK":
        raise RuntimeError(f"IMAP STATUS failed: {data!r}")
    raw = data[0].decode() if isinstance(data[0], bytes) else data[0]
    # raw looks like: 'INBOX (UIDVALIDITY 12345)'
    token = raw.split("UIDVALIDITY", 1)[1].strip().rstrip(")").strip()
    uidvalidity = int(token)

    typ, data = mail.select(INBOX, readonly=True)
    if typ != "OK":
        raise RuntimeError(f"IMAP SELECT failed: {data!r}")
    return uidvalidity


def _uid_search(mail: imaplib.IMAP4_SSL, criteria: str) -> list[int]:
    typ, data = mail.uid("SEARCH", None, *criteria.split())
    if typ != "OK":
        raise RuntimeError(f"UID SEARCH {criteria!r} failed: {data!r}")
    raw = data[0] if data else b""
    if not raw:
        return []
    return [int(x) for x in raw.split()]


def _uid_fetch_headers(
    mail: imaplib.IMAP4_SSL,
    uids: list[int],
    include_flags: bool = True,
) -> list[dict]:
    """Fetch FROM/Subject/INTERNALDATE/FLAGS for each UID. Returns list of dicts."""
    if not uids:
        return []
    fetch_fields = "(UID FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])"
    out: list[dict] = []
    for i in range(0, len(uids), DEFAULT_BATCH):
        batch = uids[i : i + DEFAULT_BATCH]
        seq = ",".join(str(u) for u in batch)
        typ, response = mail.uid("FETCH", seq, fetch_fields)
        if typ != "OK":
            continue

        # imaplib returns a flat list with paired (envelope-bytes, header-bytes) tuples
        # interspersed with closing ")" bytes. We parse each tuple.
        for item in response:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            envelope = item[0]
            raw = item[1]
            if isinstance(envelope, bytes):
                envelope = envelope.decode("utf-8", errors="replace")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")

            uid = _parse_token(envelope, "UID")
            flags_token = _parse_flags(envelope)
            internal_date = _parse_internal_date(envelope)

            msg = email.message_from_string(raw)
            from_value = msg.get("From", "").strip()
            subject = msg.get("Subject", "").strip()
            name, addr = email.utils.parseaddr(from_value)
            addr = (addr or "").lower().strip()
            domain = addr.split("@")[-1] if "@" in addr else ""

            out.append({
                "uid": uid,
                "sender": from_value,
                "sender_addr": addr,
                "domain": domain,
                "subject": subject,
                "internal_date": internal_date,
                "seen": "\\Seen" in flags_token if include_flags else False,
            })
    return out


def _parse_token(envelope: str, key: str) -> int:
    # envelope is like: "12345 (UID 6789 FLAGS (\\Seen) INTERNALDATE \"...\" BODY[...] {123}"
    idx = envelope.find(key + " ")
    if idx < 0:
        return 0
    rest = envelope[idx + len(key) + 1 :]
    val = rest.split()[0].strip(")")
    try:
        return int(val)
    except ValueError:
        return 0


def _parse_flags(envelope: str) -> str:
    # Return the substring inside FLAGS (...)
    i = envelope.find("FLAGS (")
    if i < 0:
        return ""
    j = envelope.find(")", i)
    return envelope[i + len("FLAGS (") : j]


def _parse_internal_date(envelope: str) -> str | None:
    i = envelope.find('INTERNALDATE "')
    if i < 0:
        return None
    j = envelope.find('"', i + len('INTERNALDATE "'))
    if j < 0:
        return None
    raw = envelope[i + len('INTERNALDATE "') : j]
    try:
        # IMAP format: "06-May-2026 08:30:15 +0000"
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


# ── Sync ───────────────────────────────────────────────────────────────────


def _get_state(account_id: int, mailbox: str) -> tuple[int | None, int]:
    row = get_conn().execute(
        "SELECT uidvalidity, last_uid FROM mailbox_state WHERE account_id=? AND mailbox=?",
        (account_id, mailbox),
    ).fetchone()
    if row is None:
        return (None, 0)
    return (row["uidvalidity"], int(row["last_uid"] or 0))


def _save_state(account_id: int, mailbox: str, uidvalidity: int, last_uid: int) -> None:
    get_conn().execute(
        """
        INSERT INTO mailbox_state (account_id, mailbox, uidvalidity, last_uid, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(account_id, mailbox) DO UPDATE SET
            uidvalidity = excluded.uidvalidity,
            last_uid    = excluded.last_uid,
            updated_at  = CURRENT_TIMESTAMP
        """,
        (account_id, mailbox, uidvalidity, last_uid),
    )


def _wipe_mailbox_messages(account_id: int, mailbox: str) -> None:
    get_conn().execute(
        "DELETE FROM messages WHERE account_id = ? AND mailbox = ?",
        (account_id, mailbox),
    )


def _upsert_messages(
    account_id: int, mailbox: str, uidvalidity: int, rows: Iterable[dict]
) -> None:
    payload = [
        (
            account_id,
            uidvalidity,
            r["uid"],
            mailbox,
            r["sender"],
            r["sender_addr"],
            r["domain"],
            r["subject"],
            r["internal_date"],
            1 if r["seen"] else 0,
        )
        for r in rows
        if r["uid"] > 0
    ]
    if not payload:
        return
    with transaction() as conn:
        conn.executemany(
            """
            INSERT INTO messages
                (account_id, uidvalidity, uid, mailbox,
                 sender, sender_addr, domain, subject, internal_date,
                 seen, in_inbox)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(account_id, uidvalidity, uid) DO UPDATE SET
                sender        = excluded.sender,
                sender_addr   = excluded.sender_addr,
                domain        = excluded.domain,
                subject       = excluded.subject,
                internal_date = COALESCE(excluded.internal_date, messages.internal_date),
                seen          = excluded.seen,
                in_inbox      = 1,
                removed_at    = NULL
            """,
            payload,
        )


def sync_inbox(
    account_id: int,
    full_resync: bool = False,
    progress_fn: Callable[[str, int, int], None] | None = None,
) -> SyncReport:
    """Bring the local SQLite cache into sync with the live INBOX.

    Strategy:
        1. Open INBOX, read UIDVALIDITY.
        2. If UIDVALIDITY changed (or full_resync): delete cached rows for this mailbox.
        3. UID SEARCH UID <last_uid+1>:* → fetch headers for new UIDs only.
        4. UID SEARCH 1:<last_uid> UNSEEN → reconcile read-state for cached rows.
        5. Mark cached rows whose UIDs no longer exist in INBOX as removed (in_inbox=0).
        6. Persist new last_uid.
    """
    started = time.time()
    acct = get_account(account_id)
    if acct is None:
        raise RuntimeError(f"unknown account_id={account_id}")

    mail = connect_account(account_id)
    try:
        uidvalidity = _select_inbox(mail)
        prev_uidvalidity, last_uid = _get_state(account_id, INBOX)

        if full_resync or (prev_uidvalidity is not None and prev_uidvalidity != uidvalidity):
            _wipe_mailbox_messages(account_id, INBOX)
            last_uid = 0
            full_resync = True

        # 3. fetch new UIDs above last_uid.
        # IMAP quirk: `UID SEARCH UID N:*` returns the *highest* UID even when N
        # exceeds it, so we filter explicitly.
        if last_uid == 0:
            new_uids = _uid_search(mail, "ALL")
        else:
            new_uids = [u for u in _uid_search(mail, f"UID {last_uid + 1}:*") if u > last_uid]

        if progress_fn:
            progress_fn("fetch", 0, len(new_uids))

        new_count = 0
        if new_uids:
            # batch fetch with progress
            for i in range(0, len(new_uids), DEFAULT_BATCH):
                batch = new_uids[i : i + DEFAULT_BATCH]
                rows = _uid_fetch_headers(mail, batch)
                _upsert_messages(account_id, INBOX, uidvalidity, rows)
                new_count += len(rows)
                if progress_fn:
                    progress_fn("fetch", min(i + DEFAULT_BATCH, len(new_uids)), len(new_uids))
            last_uid = max(last_uid, max(new_uids))

        # 4. reconcile read-state for cached rows (only if we have any)
        seen_changed = 0
        if not full_resync and last_uid > 0:
            unseen_uids = set(_uid_search(mail, f"UID 1:{last_uid} UNSEEN"))
            cur = get_conn().execute(
                "SELECT uid, seen FROM messages WHERE account_id=? AND mailbox=? AND uidvalidity=? AND in_inbox=1",
                (account_id, INBOX, uidvalidity),
            )
            updates = []
            for row in cur:
                desired = 0 if row["uid"] in unseen_uids else 1
                if int(row["seen"]) != desired:
                    updates.append((desired, account_id, INBOX, uidvalidity, row["uid"]))
            if updates:
                with transaction() as conn:
                    conn.executemany(
                        "UPDATE messages SET seen=? WHERE account_id=? AND mailbox=? AND uidvalidity=? AND uid=?",
                        updates,
                    )
                seen_changed = len(updates)

        # 5. detect removed (archived/deleted) cached UIDs
        removed = 0
        if not full_resync and last_uid > 0:
            present = set(_uid_search(mail, f"UID 1:{last_uid}"))
            cur = get_conn().execute(
                "SELECT uid FROM messages WHERE account_id=? AND mailbox=? AND uidvalidity=? AND in_inbox=1",
                (account_id, INBOX, uidvalidity),
            )
            cached = [int(r["uid"]) for r in cur]
            gone = [u for u in cached if u not in present]
            if gone:
                with transaction() as conn:
                    conn.executemany(
                        "UPDATE messages SET in_inbox=0, removed_at=CURRENT_TIMESTAMP WHERE account_id=? AND mailbox=? AND uidvalidity=? AND uid=?",
                        [(account_id, INBOX, uidvalidity, u) for u in gone],
                    )
                removed = len(gone)

        _save_state(account_id, INBOX, uidvalidity, last_uid)
        get_conn().execute(
            "UPDATE accounts SET last_synced_at=CURRENT_TIMESTAMP WHERE id=?",
            (account_id,),
        )

        total = get_conn().execute(
            "SELECT COUNT(*) FROM messages WHERE account_id=? AND mailbox=? AND in_inbox=1",
            (account_id, INBOX),
        ).fetchone()[0]

        return SyncReport(
            account_id=account_id,
            mailbox=INBOX,
            full_resync=full_resync,
            total_in_mailbox=total,
            new_messages=new_count,
            seen_state_changed=seen_changed,
            removed=removed,
            elapsed_ms=int((time.time() - started) * 1000),
            uidvalidity=uidvalidity,
            last_uid=last_uid,
        )
    finally:
        try:
            mail.close()
        except Exception:
            pass
        try:
            mail.logout()
        except Exception:
            pass


# ── Read API for routes ────────────────────────────────────────────────────


def list_inbox_domains(
    account_id: int,
    unseen_only: bool = True,
) -> dict:
    """Roll up cached INBOX rows into the same shape the audit endpoint returns."""
    conn = get_conn()
    where = "account_id = ? AND mailbox = ? AND in_inbox = 1"
    params: list = [account_id, INBOX]
    if unseen_only:
        where += " AND seen = 0"

    rows = list(conn.execute(
        f"""SELECT domain, sender, subject, internal_date
            FROM messages
            WHERE {where}
            ORDER BY internal_date DESC""",
        params,
    ))

    domain_counter: Counter[str] = Counter()
    domain_emails: dict[str, list[dict]] = {}
    for r in rows:
        d = r["domain"] or "(unknown)"
        domain_counter[d] += 1
        if d not in domain_emails:
            domain_emails[d] = []
        if len(domain_emails[d]) < SUBJECT_SAMPLE_PER_DOMAIN:
            domain_emails[d].append({"sender": r["sender"], "subject": r["subject"], "date": r["internal_date"]})

    total = sum(domain_counter.values())

    last_synced_at = conn.execute(
        "SELECT last_synced_at FROM accounts WHERE id=?", (account_id,)
    ).fetchone()
    last_synced_at = last_synced_at["last_synced_at"] if last_synced_at else None

    return {
        "total": total,
        "domain_counter": domain_counter,
        "domain_emails": domain_emails,
        "last_synced_at": last_synced_at,
    }


def mark_domains_removed(account_id: int, domains: list[str]) -> int:
    """When the API archives via IMAP, update the cache so the UI updates instantly."""
    if not domains:
        return 0
    placeholders = ",".join(["?"] * len(domains))
    cur = get_conn().execute(
        f"""UPDATE messages
            SET in_inbox=0, removed_at=CURRENT_TIMESTAMP
            WHERE account_id=? AND mailbox=? AND in_inbox=1 AND domain IN ({placeholders})""",
        [account_id, INBOX, *domains],
    )
    return cur.rowcount or 0
