#!/usr/bin/env python3
"""
Archive Old Inbox Emails (One-Time)

Archives all INBOX emails older than N months. One-time operation.

Usage:
    python3 archive_old.py                  # dry run, default 6 months
    python3 archive_old.py --apply          # archive
    python3 archive_old.py --months=12      # older than 12 months
"""

import imaplib
import os
import sys
import time
from datetime import date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


def imap_date(d):
    """Format date as DD-Mon-YYYY for IMAP BEFORE search."""
    return d.strftime("%d-%b-%Y")


def main():
    args = sys.argv[1:]
    dry_run = "--apply" not in args
    yes = "--yes" in args
    months = 6
    for arg in args:
        if arg.startswith("--months="):
            months = int(arg.split("=", 1)[1])

    cutoff = date.today() - timedelta(days=months * 30)
    cutoff_str = imap_date(cutoff)

    print(f"{'DRY RUN — ' if dry_run else ''}Archive all inbox emails before {cutoff_str} ({months} months ago)")

    user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(user, password)
    mail.select("INBOX")

    status, data = mail.search(None, "BEFORE", cutoff_str)
    if status != "OK" or not data[0]:
        print("No emails found before that date.")
        mail.logout()
        return

    msg_ids = data[0].split()
    print(f"Found {len(msg_ids):,} emails to archive.")

    if dry_run:
        print("Run with --apply to archive them.")
        mail.logout()
        return

    if not yes:
        confirm = input(f"Archive {len(msg_ids):,} emails? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            mail.logout()
            return

    batch_size = 200
    archived = 0
    total = len(msg_ids)

    for i in range(0, total, batch_size):
        batch = msg_ids[i:i + batch_size]
        batch_str = b",".join(batch)
        try:
            mail.store(batch_str, "+FLAGS", "\\Seen")
            mail.store(batch_str, "+FLAGS", "\\Deleted")
            mail.expunge()
            archived += len(batch)
            print(f"  {archived:,}/{total:,}...", end="\r")
        except Exception as e:
            print(f"\n  Connection error at {archived}, reconnecting...")
            try:
                mail.logout()
            except Exception:
                pass
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(user, password)
            mail.select("INBOX")
            # Re-search after reconnect since sequence numbers changed
            status, data = mail.search(None, "BEFORE", cutoff_str)
            if status == "OK" and data[0]:
                msg_ids = data[0].split()
                total = len(msg_ids)
            else:
                break

    print(f"\nDone. Archived {archived:,} emails older than {cutoff_str}.")

    try:
        mail.close()
        mail.logout()
    except Exception:
        pass


if __name__ == "__main__":
    main()
