#!/usr/bin/env python3
"""
Sweep Blocked Domains from Inbox

Archives all emails in INBOX (read + unread) from every domain in archived_domains.
Useful for clearing out the historical backlog after archived_domains grows.

Usage:
    python3 sweep_blocked.py             # Dry run (default)
    python3 sweep_blocked.py --apply     # Actually archive
"""

import imaplib
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(SCRIPT_DIR)

sys.path.insert(0, SCRIPT_DIR)

from inbox_audit import load_archived_domains
from mass_archive import archive_domain


def main():
    dry_run = "--apply" not in sys.argv

    domains = load_archived_domains()
    if not domains:
        print("No archived_domains found in .local.md")
        return

    print(f"{'DRY RUN — ' if dry_run else ''}Sweeping {len(domains)} blocked domains from inbox...")

    user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(user, password)
    mail.select("INBOX")

    results = {}
    for domain in domains:
        count = archive_domain(mail, domain, dry_run=dry_run)
        if count > 0:
            results[domain] = count
            action = "would archive" if dry_run else "archived"
            print(f"  {action} {count:>4}  {domain}")
            if not dry_run:
                time.sleep(0.3)

    mail.close()
    mail.logout()

    total = sum(results.values())
    action = "Would archive" if dry_run else "Archived"
    print(f"\n{action} {total} emails across {len(results)} domains.")
    if dry_run and total > 0:
        print("Run with --apply to execute.")


if __name__ == "__main__":
    main()
