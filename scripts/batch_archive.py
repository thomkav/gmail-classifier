#!/usr/bin/env python3
"""
Batch Archive from File

Reads a domain list from a file and archives all matching inbox emails.
Supports permanent (add to archived_domains) and one-time modes per line.

File format (one domain per line):
    domain.com          # permanent: archive + add to archived_domains
    ! domain.com        # one-time: archive only, don't add to archived_domains
    # this is a comment

Usage:
    python3 batch_archive.py domains.txt             # dry run
    python3 batch_archive.py domains.txt --apply     # apply
    python3 batch_archive.py domains.txt --apply --quiet
"""

import imaplib
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(SCRIPT_DIR)

sys.path.insert(0, SCRIPT_DIR)

from inbox_audit import load_archived_domains, append_archived_domains
from mass_archive import archive_domain


def parse_batch_file(path):
    """Parse batch file. Returns list of (domain, permanent) tuples."""
    if not os.path.exists(path):
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!"):
                domain = line[1:].split("#")[0].strip()
                if domain:
                    entries.append((domain, False))
            else:
                domain = line.split("#")[0].strip()
                if domain:
                    entries.append((domain, True))
    return entries


def connect_imap():
    user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(user, password)
    mail.select("INBOX")
    return mail


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("--"):
        print("Usage: python3 batch_archive.py <file> [--apply] [--quiet]")
        sys.exit(1)

    batch_file = args[0]
    dry_run = "--apply" not in args
    quiet = "--quiet" in args

    entries = parse_batch_file(batch_file)
    if not entries:
        print("No domains found in file.")
        return

    permanent = [(d, p) for d, p in entries if p]
    one_time = [(d, p) for d, p in entries if not p]

    print(f"{'DRY RUN — ' if dry_run else ''}Batch archive: {len(permanent)} permanent, {len(one_time)} one-time")
    print()

    if dry_run:
        if permanent:
            print("  PERMANENT (will add to archived_domains):")
            for d, _ in permanent:
                print(f"    {d}")
        if one_time:
            print("  ONE-TIME (archive only):")
            for d, _ in one_time:
                print(f"    ! {d}")
        print("\nRun with --apply to execute.")
        return

    # Connect and archive in batches, reconnecting on drop
    mail = connect_imap()
    results = {}
    newly_permanent = []

    for i, (domain, is_permanent) in enumerate(entries):
        # Reconnect every 30 domains or after a gap
        if i > 0 and i % 30 == 0:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass
            if not quiet:
                print(f"  [reconnecting...]")
            mail = connect_imap()

        try:
            count = archive_domain(mail, domain, dry_run=False)
        except Exception as e:
            if not quiet:
                print(f"  ERROR on {domain}: {e} — reconnecting...")
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass
            mail = connect_imap()
            try:
                count = archive_domain(mail, domain, dry_run=False)
            except Exception as e2:
                print(f"  FAILED {domain}: {e2}")
                results[domain] = 0
                continue

        results[domain] = count
        tag = "" if is_permanent else " [one-time]"
        if not quiet or count > 0:
            print(f"  {count:>5}  {domain}{tag}")

        if is_permanent and domain not in set(load_archived_domains()):
            newly_permanent.append(domain)

        if count > 0:
            time.sleep(0.2)

    try:
        mail.close()
        mail.logout()
    except Exception:
        pass

    # Update archived_domains for permanent entries
    if newly_permanent:
        append_archived_domains(newly_permanent)

    total = sum(results.values())
    print(f"\nArchived {total} emails across {len([v for v in results.values() if v > 0])} domains.")
    if newly_permanent:
        print(f"Added {len(newly_permanent)} domains to archived_domains in .local.md")


if __name__ == "__main__":
    main()
