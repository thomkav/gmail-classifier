#!/usr/bin/env python3
"""
Mass Archive Unread Emails by Domain

Connects via IMAP to Gmail, searches for unread emails from specified domains,
marks them as read and archives them (removes from INBOX).

Gmail IMAP default behavior: STORE \\Deleted + EXPUNGE in INBOX = archive (not trash).
"""

import imaplib
import os
import sys
import json
import time


def archive_domain(mail, domain: str, dry_run: bool = False) -> int:
    """Archive all emails from a domain in INBOX. Returns count archived."""
    # Search for ALL emails from this domain (not just UNSEEN — audit may have marked as read)
    status, data = mail.search(None, 'FROM', f'"@{domain}"')
    if status != "OK" or not data[0]:
        return 0

    msg_ids = data[0].split()
    count = len(msg_ids)

    if count == 0 or dry_run:
        return count

    # Process in batches of 50 (smaller to avoid sequence number issues after expunge)
    batch_size = 50
    archived = 0
    while True:
        # Re-search each iteration since expunge changes sequence numbers
        status, data = mail.search(None, 'FROM', f'"@{domain}"')
        if status != "OK" or not data[0]:
            break

        msg_ids = data[0].split()
        if not msg_ids:
            break

        batch = msg_ids[:batch_size]
        batch_str = b",".join(batch)

        # Mark as read
        mail.store(batch_str, "+FLAGS", "\\Seen")
        # Mark for deletion from INBOX (Gmail archives, doesn't trash)
        mail.store(batch_str, "+FLAGS", "\\Deleted")
        # Expunge after each batch to keep sequence numbers consistent
        mail.expunge()

        archived += len(batch)

    return archived


def main():
    dry_run = "--dry-run" in sys.argv
    domains = [arg for arg in sys.argv[1:] if arg != "--dry-run"]

    if not domains:
        print("Usage: python3 mass_archive.py [--dry-run] domain1 domain2 ...")
        print("Example: python3 mass_archive.py --dry-run substack.com patreon.com")
        sys.exit(1)

    user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to imap.gmail.com...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(user, password)
    mail.select("INBOX")

    if dry_run:
        print("=== DRY RUN - No changes will be made ===\n")

    results = {}
    total_archived = 0

    for domain in domains:
        count = archive_domain(mail, domain, dry_run=dry_run)
        results[domain] = count
        total_archived += count
        action = "would archive" if dry_run else "archived"
        print(f"  {action} {count:>4} emails from {domain}")

        if not dry_run and count > 0:
            # Brief pause between domains to avoid rate limits
            time.sleep(0.5)

    print(f"\n{'Would archive' if dry_run else 'Archived'} {total_archived} total emails across {len(domains)} domains")

    # Output JSON summary
    summary = {
        "dry_run": dry_run,
        "total_archived": total_archived,
        "domains": results,
    }
    print(f"\n{json.dumps(summary)}")

    mail.close()
    mail.logout()


if __name__ == "__main__":
    main()
