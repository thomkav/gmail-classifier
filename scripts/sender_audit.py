#!/usr/bin/env python3
"""
Inbox Sender Volume Audit

Connects via IMAP to fetch FROM headers for all unread emails,
counts sender frequency, and outputs top senders by volume.
"""

import imaplib
import email
import email.utils
import os
import json
import sys
from collections import Counter


def extract_sender_info(from_header: str) -> tuple:
    """Extract display name and email address from From header"""
    name, addr = email.utils.parseaddr(from_header)
    addr = addr.lower().strip()
    domain = addr.split("@")[-1] if "@" in addr else addr
    return name, addr, domain


def fetch_unread_senders(imap_host="imap.gmail.com", imap_port=993,
                         include_subjects=False, progress_fn=None,
                         unseen_only=True):
    """Fetch FROM headers (and optionally Subject) for emails in INBOX.

    Args:
        imap_host: IMAP server hostname.
        imap_port: IMAP server port.
        include_subjects: When True, also fetch Subject headers and return
            a 5-tuple with domain_emails dict as the fifth element.
        progress_fn: Optional callback(current, total) for progress reporting.
        unseen_only: When True (default), only fetch UNSEEN emails.
            When False, fetch ALL inbox emails.

    Returns:
        4-tuple (sender_counter, domain_counter, sender_to_domain, total) when
        include_subjects is False (backward-compatible).

        5-tuple adding domain_emails: dict[str, list[dict]] when True.
        Each dict has keys: sender, subject, domain.
    """
    user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    if not progress_fn:
        print(f"Connecting to {imap_host}...", file=sys.stderr)
    mail = imaplib.IMAP4_SSL(imap_host, imap_port)
    mail.login(user, password)
    mail.select("INBOX", readonly=True)

    # Search for emails
    search_criteria = "UNSEEN" if unseen_only else "ALL"
    label = "unread" if unseen_only else "inbox"
    if not progress_fn:
        print(f"Searching for {label} emails...", file=sys.stderr)
    status, data = mail.search(None, search_criteria)
    if status != "OK":
        print(f"ERROR: Search failed: {status}", file=sys.stderr)
        sys.exit(1)

    msg_ids = data[0].split()
    total = len(msg_ids)
    if not progress_fn:
        print(f"Found {total} {label} emails. Fetching headers...", file=sys.stderr)

    sender_counter = Counter()
    domain_counter = Counter()
    sender_to_domain = {}
    domain_emails = {} if include_subjects else None
    batch_size = 200

    fetch_fields = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])" if include_subjects else "(BODY.PEEK[HEADER.FIELDS (FROM)])"

    for i in range(0, total, batch_size):
        batch = msg_ids[i:i + batch_size]
        batch_str = b",".join(batch)
        progress = min(i + batch_size, total)

        if progress_fn:
            progress_fn(progress, total)
        else:
            print(f"  Fetching {progress}/{total}...", file=sys.stderr)

        status, response = mail.fetch(batch_str, fetch_fields)
        if status != "OK":
            if not progress_fn:
                print(f"  Warning: batch fetch failed at {i}", file=sys.stderr)
            continue

        for item in response:
            if isinstance(item, tuple) and len(item) >= 2:
                raw = item[1]
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")

                # Use email.message_from_string for robust header parsing
                msg = email.message_from_string(raw)
                from_value = msg.get("From", "").strip()

                if from_value:
                    name, addr, domain = extract_sender_info(from_value)
                    display = f"{name} <{addr}>" if name else addr
                    sender_counter[display] += 1
                    domain_counter[domain] += 1
                    sender_to_domain[display] = domain

                    if include_subjects:
                        subject = msg.get("Subject", "").strip()
                        entry = {"sender": from_value, "subject": subject, "domain": domain}
                        domain_emails.setdefault(domain, []).append(entry)

    mail.close()
    mail.logout()

    if include_subjects:
        return sender_counter, domain_counter, sender_to_domain, total, domain_emails
    return sender_counter, domain_counter, sender_to_domain, total


def main():
    unseen_only = "--all" not in sys.argv
    limit = 50
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            try:
                limit = int(arg.split("=", 1)[1])
            except ValueError:
                pass
    sender_counts, domain_counts, sender_to_domain, total = fetch_unread_senders(unseen_only=unseen_only)

    # Output as JSON for programmatic use
    results = {
        "total_unread": total,
        "top_senders": [
            {"sender": sender, "count": count, "domain": sender_to_domain.get(sender, "")}
            for sender, count in sender_counts.most_common(limit)
        ],
        "top_domains": [
            {"domain": domain, "count": count}
            for domain, count in domain_counts.most_common(limit)
        ],
    }

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
