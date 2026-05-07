#!/usr/bin/env python3
"""
Auto-Archive Pipeline

Non-interactive classify + archive pipeline. Replaces the TUI for bulk cleanup.
Classifies all unread domains, applies auto-archive rules, and outputs a summary.

Usage:
    python3 auto_archive.py                    # Dry run (default)
    python3 auto_archive.py --dry-run          # Explicit dry run
    python3 auto_archive.py --apply            # Actually archive + update .local.md
    python3 auto_archive.py --threshold=80     # Override confidence cutoff (default 70)
    python3 auto_archive.py --json             # Machine-readable JSON output
"""

import imaplib
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(SCRIPT_DIR)

sys.path.insert(0, SCRIPT_DIR)

from sender_audit import fetch_unread_senders
from inbox_audit import (
    load_config_for_classifier,
    load_archived_domains,
    append_archived_domains,
    classify_domains,
)
from mass_archive import archive_domain
from classify_logic import Category, NewsletterTier


# ---------------------------------------------------------------------------
# Auto-archive decision logic
# ---------------------------------------------------------------------------

def should_auto_archive(domain, count, result, archived_set, threshold):
    """Determine if a domain should be auto-archived and return (archive, reason).

    Priority order:
    1. Already in archived_domains → re-archive (slip-through)
    2. Promotions with confidence >= threshold → archive
    3. Newsletters with LOW quality tier → archive
    4. Newsletters in archive_newsletters preference → archive
    5. Everything else → skip
    """
    if domain in archived_set:
        return True, "archived domain (slip-through)"

    if result is None:
        return False, "no classification"

    cat = result.category
    conf = result.confidence
    action = result.suggested_action

    if cat == Category.PROMOTION and conf >= threshold:
        return True, f"promotion (confidence {conf:.0f}%)"

    if cat == Category.NEWSLETTER:
        if result.tier == NewsletterTier.LOW:
            return True, f"newsletter low-quality (confidence {conf:.0f}%)"
        if action == "archive":
            return True, f"newsletter in archive list (confidence {conf:.0f}%)"

    return False, f"{cat.value} (confidence {conf:.0f}%, action={action})"


def build_archive_plan(domain_counts, classifications, archived_set, threshold):
    """Split all domains into to_archive and to_skip lists.

    Returns:
        to_archive: list of {domain, count, reason, confidence, category}
        to_skip:    list of {domain, count, reason, confidence, category}
    """
    to_archive = []
    to_skip = []

    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        result = classifications.get(domain)
        archive, reason = should_auto_archive(domain, count, result, archived_set, threshold)

        entry = {
            "domain": domain,
            "count": count,
            "reason": reason,
            "confidence": result.confidence if result else 0,
            "category": result.category.value if result else "unknown",
        }

        if archive:
            to_archive.append(entry)
        else:
            to_skip.append(entry)

    return to_archive, to_skip


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def print_plan_table(to_archive, to_skip, total_unread):
    """Print human-readable summary table."""
    archive_emails = sum(e["count"] for e in to_archive)
    skip_emails = sum(e["count"] for e in to_skip)

    print(f"\n{'='*60}")
    print(f"  Auto-Archive Dry Run")
    print(f"{'='*60}")
    print(f"  Total unread: {total_unread}")
    print(f"  Domains scanned: {len(to_archive) + len(to_skip)}")
    print()

    if to_archive:
        print(f"  TO ARCHIVE ({len(to_archive)} domains, {archive_emails} emails)")
        print(f"  {'-'*54}")
        for e in to_archive:
            print(f"  {e['domain']:<35} {e['count']:>5} emails  {e['reason']}")
        print()

    if to_skip:
        print(f"  TO SKIP ({len(to_skip)} domains, {skip_emails} emails)")
        print(f"  {'-'*54}")
        for e in to_skip[:20]:
            print(f"  {e['domain']:<35} {e['count']:>5} emails  {e['reason']}")
        if len(to_skip) > 20:
            print(f"  ... and {len(to_skip) - 20} more")
        print()

    print(f"{'='*60}")
    if to_archive:
        print(f"  Would archive {archive_emails} emails from {len(to_archive)} domains.")
    else:
        print(f"  Nothing to auto-archive.")
    print()


def print_results_table(archived_counts, newly_blocked):
    """Print results after --apply."""
    total = sum(archived_counts.values())
    print(f"\n{'='*60}")
    print(f"  Auto-Archive Complete")
    print(f"{'='*60}")
    for domain, count in sorted(archived_counts.items(), key=lambda x: -x[1]):
        print(f"  {domain:<35} {count:>5} emails archived")
    print()
    print(f"  Archived {total} total emails from {len(archived_counts)} domains.")
    if newly_blocked:
        print(f"  Added {len(newly_blocked)} new domains to archived_domains in .local.md")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    args = sys.argv[1:]
    dry_run = "--apply" not in args  # default is dry run
    json_out = "--json" in args
    threshold = 70

    for arg in args:
        if arg.startswith("--threshold="):
            try:
                threshold = int(arg.split("=", 1)[1])
            except ValueError:
                print(f"ERROR: invalid --threshold value", file=sys.stderr)
                sys.exit(1)

    return dry_run, json_out, threshold


def main():
    dry_run, json_out, threshold = parse_args()

    # --- Fetch ---
    if not json_out:
        print("Connecting to Gmail...", file=sys.stderr)

    data = fetch_unread_senders(include_subjects=True)
    sender_counts, domain_counts, sender_to_domain, total, domain_emails = data

    if total == 0:
        if json_out:
            print(json.dumps({"total_unread": 0, "to_archive": [], "to_skip": []}))
        else:
            print("Inbox zero — nothing to do.")
        return

    # --- Classify ---
    if not json_out:
        print(f"Classifying {len(domain_counts)} domains...", file=sys.stderr)

    config = load_config_for_classifier()
    classifications = classify_domains(domain_emails, config)
    archived_set = set(load_archived_domains())

    # --- Build plan ---
    to_archive, to_skip = build_archive_plan(
        dict(domain_counts), classifications, archived_set, threshold
    )

    if json_out:
        summary = {
            "dry_run": dry_run,
            "total_unread": total,
            "threshold": threshold,
            "to_archive": to_archive,
            "to_skip": to_skip,
        }
        print(json.dumps(summary, indent=2))
        return

    if dry_run:
        print_plan_table(to_archive, to_skip, total)
        return

    # --- Apply ---
    if not to_archive:
        print("Nothing to auto-archive.")
        return

    print(f"\nArchiving {len(to_archive)} domains...", file=sys.stderr)

    user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(user, password)
    mail.select("INBOX")

    archived_counts = {}
    newly_blocked = []

    for entry in to_archive:
        domain = entry["domain"]
        count = archive_domain(mail, domain, dry_run=False)
        archived_counts[domain] = count
        print(f"  archived {count:>4} from {domain}", file=sys.stderr)
        if count > 0 and domain not in archived_set:
            newly_blocked.append(domain)
        if count > 0:
            time.sleep(0.3)

    mail.close()
    mail.logout()

    if newly_blocked:
        append_archived_domains(newly_blocked)

    print_results_table(archived_counts, newly_blocked)


if __name__ == "__main__":
    main()
