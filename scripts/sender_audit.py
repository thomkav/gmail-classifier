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


def fetch_unread_senders(imap_host="imap.gmail.com", imap_port=993):
    """Fetch FROM headers for all unread emails in INBOX"""
    user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to {imap_host}...", file=sys.stderr)
    mail = imaplib.IMAP4_SSL(imap_host, imap_port)
    mail.login(user, password)
    mail.select("INBOX", readonly=True)

    # Search for unread emails
    print("Searching for unread emails...", file=sys.stderr)
    status, data = mail.search(None, "UNSEEN")
    if status != "OK":
        print(f"ERROR: Search failed: {status}", file=sys.stderr)
        sys.exit(1)

    msg_ids = data[0].split()
    total = len(msg_ids)
    print(f"Found {total} unread emails. Fetching FROM headers...", file=sys.stderr)

    sender_counter = Counter()
    domain_counter = Counter()
    sender_to_domain = {}
    batch_size = 200

    for i in range(0, total, batch_size):
        batch = msg_ids[i:i + batch_size]
        batch_str = b",".join(batch)
        progress = min(i + batch_size, total)
        print(f"  Fetching {progress}/{total}...", file=sys.stderr)

        status, response = mail.fetch(batch_str, "(BODY.PEEK[HEADER.FIELDS (FROM)])")
        if status != "OK":
            print(f"  Warning: batch fetch failed at {i}", file=sys.stderr)
            continue

        for item in response:
            if isinstance(item, tuple) and len(item) >= 2:
                header = item[1]
                if isinstance(header, bytes):
                    header = header.decode("utf-8", errors="replace")
                from_value = header.replace("From: ", "").replace("from: ", "").strip()
                if from_value:
                    name, addr, domain = extract_sender_info(from_value)
                    display = f"{name} <{addr}>" if name else addr
                    sender_counter[display] += 1
                    domain_counter[domain] += 1
                    sender_to_domain[display] = domain

    mail.close()
    mail.logout()

    return sender_counter, domain_counter, sender_to_domain, total


def main():
    sender_counts, domain_counts, sender_to_domain, total = fetch_unread_senders()

    # Output as JSON for programmatic use
    results = {
        "total_unread": total,
        "top_senders": [
            {"sender": sender, "count": count, "domain": sender_to_domain.get(sender, "")}
            for sender, count in sender_counts.most_common(50)
        ],
        "top_domains": [
            {"domain": domain, "count": count}
            for domain, count in domain_counts.most_common(50)
        ],
    }

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
