#!/usr/bin/env python3
"""
Interactive Inbox Audit

Single entrypoint that walks through the full audit → archive → unsubscribe flow.
Imports functions from existing scripts rather than shelling out.

Usage:
    python3 inbox_audit.py          # Full interactive flow
    python3 inbox_audit.py --force  # Allow retrying previously-attempted unsubs
"""

import json
import os
import re
import sys
import time
import webbrowser
from datetime import date

# Resolve script directory for sibling imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(SCRIPT_DIR)
LOCAL_MD = os.path.join(PLUGIN_DIR, ".local.md")
UNSUB_LOG = os.path.join(PLUGIN_DIR, ".unsubscribe_log.json")

sys.path.insert(0, SCRIPT_DIR)

from sender_audit import fetch_unread_senders
from mass_archive import archive_domain
from extract_unsubscribe import (
    connect_imap,
    extract_unsubscribe_for_domain,
    post_one_click_unsubscribe,
)


# ---------------------------------------------------------------------------
# Unsubscribe log (.unsubscribe_log.json)
# ---------------------------------------------------------------------------

def load_unsubscribe_log():
    """Read .unsubscribe_log.json → {domain: {date, method, status, url}}"""
    if not os.path.exists(UNSUB_LOG):
        return {}
    try:
        with open(UNSUB_LOG, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_unsubscribe_log(log):
    """Write log back to JSON file."""
    with open(UNSUB_LOG, "w") as f:
        json.dump(log, f, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# Blocked domains (.local.md frontmatter)
# ---------------------------------------------------------------------------

def load_blocked_domains():
    """Parse .local.md YAML frontmatter, extract blocked_domains list."""
    if not os.path.exists(LOCAL_MD):
        return []

    with open(LOCAL_MD, "r") as f:
        content = f.read()

    # Extract YAML frontmatter between --- delimiters
    match = re.match(r"^---\n(.*?\n)---", content, re.DOTALL)
    if not match:
        return []

    frontmatter = match.group(1)

    # Simple extraction: find lines under blocked_domains that start with "    - "
    domains = []
    in_blocked = False
    for line in frontmatter.splitlines():
        if re.match(r"\s*blocked_domains:", line):
            in_blocked = True
            continue
        if in_blocked:
            m = re.match(r"\s+-\s+(\S+)", line)
            if m:
                domains.append(m.group(1))
            elif line.strip() and not line.strip().startswith("#"):
                # Hit a new YAML key, stop
                if re.match(r"\s*\w+:", line):
                    break
    return domains


def append_blocked_domains(new_domains):
    """Insert new entries into .local.md blocked_domains before closing ---."""
    if not new_domains or not os.path.exists(LOCAL_MD):
        return

    with open(LOCAL_MD, "r") as f:
        content = f.read()

    existing = set(load_blocked_domains())
    to_add = [d for d in new_domains if d not in existing]
    if not to_add:
        return

    # Build the insertion block
    today = date.today().strftime("%Y-%m-%d")
    block = f"    # Added {today}\n"
    for d in to_add:
        block += f"    - {d}\n"

    # Find the closing --- of frontmatter and insert before it
    # Strategy: find blocked_domains section end, insert before the next top-level key or ---
    lines = content.split("\n")
    insert_idx = None
    in_blocked = False
    last_blocked_line = None

    for i, line in enumerate(lines):
        if re.match(r"\s*blocked_domains:", line):
            in_blocked = True
            continue
        if in_blocked:
            if re.match(r"\s+-\s+\S+", line) or line.strip().startswith("#"):
                last_blocked_line = i
            elif line.strip() == "---" or (line.strip() and re.match(r"\w+:", line.strip())):
                insert_idx = i
                break

    if insert_idx is None and last_blocked_line is not None:
        insert_idx = last_blocked_line + 1

    if insert_idx is not None:
        lines.insert(insert_idx, block.rstrip())
        with open(LOCAL_MD, "w") as f:
            f.write("\n".join(lines))
        print(f"  Updated .local.md: added {len(to_add)} domain(s) to blocked_domains")


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def domain_status(domain, blocked_set, unsub_log):
    """Return a status string for a domain."""
    if domain in blocked_set:
        return "[blocked]"

    entry = unsub_log.get(domain)
    if entry:
        status = entry.get("status", "")
        if status in ("success", "opened"):
            d = entry.get("date", "")
            short_date = d[5:] if d else ""  # "02/19" from "2026-02-19"
            return f"[unsub'd {short_date}]"
        if status == "failed":
            return "[unsub failed]"

    return ""


def display_audit_table(domain_counts, blocked_set, unsub_log):
    """Print numbered table with domain, count, status. Returns ordered domain list."""
    domains = []
    print()
    print(f"  {'#':>3}  {'Domain':<40} {'Count':>5}  Status")
    print(f"  {'─'*3}  {'─'*40} {'─'*5}  {'─'*20}")

    for i, (domain, count) in enumerate(domain_counts, 1):
        status = domain_status(domain, blocked_set, unsub_log)
        print(f"  {i:>3}  {domain:<40} {count:>5}  {status}")
        domains.append(domain)

    print()
    return domains


# ---------------------------------------------------------------------------
# Domain selection
# ---------------------------------------------------------------------------

def select_domains(prompt_text, domain_list, blocked_set, unsub_log):
    """Parse user input like '1,3,5' or 'all' or 'all-new' → domain list."""
    while True:
        choice = input(prompt_text).strip().lower()

        if not choice or choice == "q":
            return []

        if choice == "all":
            return list(domain_list)

        if choice == "all-new":
            return [
                d for d in domain_list
                if d not in blocked_set
                and unsub_log.get(d, {}).get("status") not in ("success", "opened")
            ]

        # Parse comma-separated numbers
        try:
            indices = []
            for part in choice.split(","):
                part = part.strip()
                if "-" in part and not part.startswith("-"):
                    # Range like 1-5
                    start, end = part.split("-", 1)
                    indices.extend(range(int(start), int(end) + 1))
                else:
                    indices.append(int(part))
            selected = []
            for idx in indices:
                if 1 <= idx <= len(domain_list):
                    d = domain_list[idx - 1]
                    if d not in selected:
                        selected.append(d)
                else:
                    print(f"  Invalid number: {idx} (valid: 1-{len(domain_list)})")
            if selected:
                return selected
        except ValueError:
            print("  Enter numbers like 1,3,5 or 'all' or 'all-new' or 'q' to skip")


# ---------------------------------------------------------------------------
# Archive flow
# ---------------------------------------------------------------------------

def run_archive_flow(domains, mail):
    """Dry run → confirm → archive → return archived counts."""
    print("\n── Archive: Dry Run ──")
    counts = {}
    for domain in domains:
        count = archive_domain(mail, domain, dry_run=True)
        counts[domain] = count
        print(f"  would archive {count:>4} emails from {domain}")

    total = sum(counts.values())
    if total == 0:
        print("  No emails found to archive.")
        return counts

    confirm = input(f"\nArchive {total} emails across {len(domains)} domains? [y/N] ").strip().lower()
    if confirm != "y":
        print("  Skipped.")
        return {}

    print("\n── Archiving ──")
    archived_counts = {}
    for domain in domains:
        count = archive_domain(mail, domain, dry_run=False)
        archived_counts[domain] = count
        print(f"  archived {count:>4} emails from {domain}")
        if count > 0:
            time.sleep(0.5)

    total_archived = sum(archived_counts.values())
    print(f"\n  Archived {total_archived} total emails.")
    return archived_counts


# ---------------------------------------------------------------------------
# Unsubscribe flow
# ---------------------------------------------------------------------------

def run_unsubscribe_flow(domains, unsub_log, force=False):
    """Extract links → skip logged → auto/open → update log."""
    # Filter out already-succeeded domains unless --force
    if not force:
        skipped = []
        eligible = []
        for d in domains:
            entry = unsub_log.get(d, {})
            if entry.get("status") in ("success", "opened"):
                skipped.append(d)
            else:
                eligible.append(d)
        if skipped:
            print(f"  Skipping {len(skipped)} already-processed: {', '.join(skipped)}")
        domains = eligible

    if not domains:
        print("  No domains to unsubscribe from.")
        return unsub_log

    print("\n── Extracting unsubscribe links ──")
    mail = connect_imap(readonly=True)

    results = []
    for domain in domains:
        print(f"  Checking {domain}...", end="", flush=True)
        result = extract_unsubscribe_for_domain(mail, domain)
        results.append(result)

        if not result["email_found"]:
            print(" no emails found")
        elif not result["http_links"]:
            print(" no unsub link")
        else:
            tag = " (one-click)" if result["one_click"] else ""
            print(f" found {len(result['http_links'])} link(s){tag}")
        time.sleep(0.3)

    mail.close()
    mail.logout()

    # Categorize results
    one_click = [r for r in results if r["one_click"] and r["http_links"]]
    browser_only = [r for r in results if r["http_links"] and not r["one_click"]]
    no_link = [r for r in results if not r["http_links"]]

    today = date.today().isoformat()

    # Auto one-click unsubscribe
    if one_click:
        print(f"\n  {len(one_click)} domain(s) support one-click unsubscribe:")
        for r in one_click:
            print(f"    - {r['domain']}")

        confirm = input(f"\n  Auto-unsubscribe from these {len(one_click)} domains? [Y/n] ").strip().lower()
        if confirm in ("", "y"):
            for r in one_click:
                url = r["http_links"][0]
                print(f"    POSTing {r['domain']}...", end="", flush=True)
                success = post_one_click_unsubscribe(url)
                status = "success" if success else "failed"
                print(f" {status}")
                unsub_log[r["domain"]] = {
                    "date": today,
                    "method": "one_click",
                    "status": status,
                    "url": url,
                }
                time.sleep(0.3)

    # Browser-based unsubscribe
    if browser_only:
        print(f"\n  {len(browser_only)} domain(s) require browser unsubscribe:")
        for r in browser_only:
            url = r["http_links"][0]
            short_url = url[:70] + "..." if len(url) > 70 else url
            print(f"    - {r['domain']}: {short_url}")

        confirm = input(f"\n  Open these {len(browser_only)} links in browser? [Y/n] ").strip().lower()
        if confirm in ("", "y"):
            for r in browser_only:
                url = r["http_links"][0]
                print(f"    Opening {r['domain']}...")
                webbrowser.open(url)
                unsub_log[r["domain"]] = {
                    "date": today,
                    "method": "browser",
                    "status": "opened",
                    "url": url,
                }
                time.sleep(0.5)

    # Log domains with no link
    for r in no_link:
        if r["domain"] not in unsub_log:
            unsub_log[r["domain"]] = {
                "date": today,
                "method": "no_link",
                "status": "no_link",
                "url": "",
            }

    return unsub_log


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    force = "--force" in sys.argv

    # Step 1: Audit
    print("── Inbox Audit ──")
    sender_counts, domain_counts, sender_to_domain, total = fetch_unread_senders()
    print(f"\n  {total} unread emails across {len(domain_counts)} domains\n")

    if total == 0:
        print("  Inbox zero! Nothing to do.")
        return

    # Load state
    blocked_set = set(load_blocked_domains())
    unsub_log = load_unsubscribe_log()

    # Step 2: Display top domains
    top_domains = domain_counts.most_common(50)
    domain_list = display_audit_table(top_domains, blocked_set, unsub_log)

    # Step 3: Action loop
    while True:
        print("  Actions: [a]rchive  [u]nsubscribe  [b]oth  [q]uit")
        action = input("  > ").strip().lower()

        if action == "q" or not action:
            break

        selected = []

        if action in ("a", "b"):
            selected = select_domains(
                "  Domains to archive (numbers, 'all', 'all-new', 'q'): ",
                domain_list, blocked_set, unsub_log,
            )
            if selected:
                # Need a writable IMAP connection for archiving
                import imaplib
                user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
                password = os.environ.get("GMAIL_APP_PASSWORD", "")
                print("  Connecting for archive...", flush=True)
                mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
                mail.login(user, password)
                mail.select("INBOX")

                archived = run_archive_flow(selected, mail)

                mail.close()
                mail.logout()

                # Update blocked_domains in .local.md
                if archived:
                    newly_archived = [d for d, c in archived.items() if c > 0]
                    if newly_archived:
                        append_blocked_domains(newly_archived)
                        blocked_set.update(newly_archived)

            if action == "a":
                continue

        if action in ("u", "b"):
            # For 'b', reuse the same selection from archive step
            if action == "u" or not selected:
                selected = select_domains(
                    "  Domains to unsubscribe (numbers, 'all', 'all-new', 'q'): ",
                    domain_list, blocked_set, unsub_log,
                )

            if selected:
                unsub_log = run_unsubscribe_flow(selected, unsub_log, force=force)
                save_unsubscribe_log(unsub_log)
                print("  Unsubscribe log saved.")

            continue

        print(f"  Unknown action: {action}")

    print("\nDone.")


if __name__ == "__main__":
    main()
