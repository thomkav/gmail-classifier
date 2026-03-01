#!/usr/bin/env python3
"""
Interactive Inbox Audit

Category-first navigation with classification, rich terminal output,
and archive/unsubscribe flows.

Usage:
    python3 inbox_audit.py                    # Full interactive flow
    python3 inbox_audit.py --force            # Retry previously-attempted unsubs
    python3 inbox_audit.py --category=newsletters  # Jump to category
    python3 inbox_audit.py --no-color         # Disable ANSI colors
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
from classify_logic import EmailClassifier, Category
from cli_ui import (
    Color,
    CATEGORY_COLORS,
    CATEGORY_ORDER,
    CATEGORY_NAMES,
    colorize,
    bold,
    dim,
    print_header,
    progress_bar,
    print_table,
    category_badge,
)


# ---------------------------------------------------------------------------
# Unsubscribe log (.unsubscribe_log.json)
# ---------------------------------------------------------------------------

def load_unsubscribe_log():
    """Read .unsubscribe_log.json -> {domain: {date, method, status, url}}"""
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
# Config parsing (.local.md frontmatter)
# ---------------------------------------------------------------------------

def _parse_frontmatter():
    """Parse .local.md YAML frontmatter into raw text."""
    if not os.path.exists(LOCAL_MD):
        return ""
    with open(LOCAL_MD, "r") as f:
        content = f.read()
    match = re.match(r"^---\n(.*?\n)---", content, re.DOTALL)
    return match.group(1) if match else ""


def load_blocked_domains():
    """Parse .local.md YAML frontmatter, extract blocked_domains list."""
    frontmatter = _parse_frontmatter()
    if not frontmatter:
        return []

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
                if re.match(r"\s*\w+:", line):
                    break
    return domains


def load_config_for_classifier():
    """Parse .local.md frontmatter into the dict format EmailClassifier expects.

    Returns dict with 'categories' and 'learned_preferences' keys.
    """
    frontmatter = _parse_frontmatter()
    if not frontmatter:
        return {"categories": {}, "learned_preferences": {}}

    config = {"categories": {}, "learned_preferences": {}}

    # State machine for parsing shallow YAML
    current_section = None       # "categories" or "learned_preferences"
    current_subsection = None    # e.g. "receipts", "newsletters", "keep_senders"
    current_key = None           # e.g. "patterns", "common_domains"

    for line in frontmatter.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Top-level keys (no indent)
        top_match = re.match(r"^(\w[\w_]*):", line)
        if top_match:
            key = top_match.group(1)
            if key == "categories":
                current_section = "categories"
                current_subsection = None
                current_key = None
            elif key == "learned_preferences":
                current_section = "learned_preferences"
                current_subsection = None
                current_key = None
            else:
                current_section = None
            continue

        if current_section == "categories":
            # 2-space indent: subsection like "receipts:", "newsletters:"
            sub_match = re.match(r"^  (\w[\w_]*):", line)
            if sub_match:
                current_subsection = sub_match.group(1)
                config["categories"].setdefault(current_subsection, {})
                current_key = None
                continue

            # 4-space indent: key like "patterns:", "common_domains:", or scalar
            key_match = re.match(r"^    (\w[\w_]*):\s*(.*)", line)
            if key_match and current_subsection:
                k = key_match.group(1)
                v = key_match.group(2).strip().strip('"').strip("'")
                if v:
                    config["categories"][current_subsection][k] = v
                    current_key = None
                else:
                    current_key = k
                    config["categories"][current_subsection].setdefault(k, [])
                continue

            # 6-space indent: list item under current_key
            item_match = re.match(r"^\s+-\s+(.+)", line)
            if item_match and current_subsection and current_key:
                val = item_match.group(1).strip().strip('"').strip("'")
                if val:
                    config["categories"][current_subsection].setdefault(current_key, [])
                    config["categories"][current_subsection][current_key].append(val)
                continue

        elif current_section == "learned_preferences":
            # 2-space indent: subsection like "keep_senders:"
            sub_match = re.match(r"^  (\w[\w_]*):", line)
            if sub_match:
                current_subsection = sub_match.group(1)
                config["learned_preferences"].setdefault(current_subsection, [])
                continue

            # 4-space indent: list items
            item_match = re.match(r"^\s+-\s+(\S+)", line)
            if item_match and current_subsection:
                val = item_match.group(1).strip()
                if val:
                    config["learned_preferences"].setdefault(current_subsection, [])
                    config["learned_preferences"][current_subsection].append(val)
                continue

    return config


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

    today = date.today().strftime("%Y-%m-%d")
    block = f"    # Added {today}\n"
    for d in to_add:
        block += f"    - {d}\n"

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
# Classification integration
# ---------------------------------------------------------------------------

def classify_domains(domain_emails, config):
    """Classify each domain using the most recent email's headers.

    Returns dict[str, ClassificationResult].
    """
    classifier = EmailClassifier(config)
    results = {}

    for domain, emails in domain_emails.items():
        # Pick the most recent email (last in list)
        sample = emails[-1] if emails else {}
        result = classifier.classify({
            "sender": sample.get("sender", ""),
            "subject": sample.get("subject", ""),
            "preview": "",  # We only have headers, not body preview
        })
        results[domain] = result

    return results


def group_by_category(top_domains, classifications):
    """Group domains into categories, sorted by count descending.

    Args:
        top_domains: list of (domain, count) tuples from Counter.most_common()
        classifications: dict[str, ClassificationResult]

    Returns:
        dict[str, list[tuple[str, int, ClassificationResult]]]
        Keys are category value strings (e.g. "newsletter", "promotion").
    """
    groups = {cat: [] for cat in CATEGORY_ORDER}

    for domain, count in top_domains:
        result = classifications.get(domain)
        if result:
            cat = result.category.value
        else:
            cat = "unknown"
        if cat not in groups:
            cat = "unknown"
        groups[cat].append((domain, count, result))

    # Remove empty categories
    return {k: v for k, v in groups.items() if v}


# ---------------------------------------------------------------------------
# Display: Dashboard
# ---------------------------------------------------------------------------

def display_dashboard(category_groups, total, blocked_set, unsub_log):
    """Print the category summary table."""
    print_header("Dashboard")
    print(f"  {bold(str(total))} unread across {bold(str(sum(len(v) for v in category_groups.values())))} domains\n")

    headers = ["", "Category", "Domains", "Emails", "Top Domain"]
    rows = []

    idx = 0
    for cat in CATEGORY_ORDER:
        if cat not in category_groups:
            continue
        idx += 1
        items = category_groups[cat]
        domain_count = len(items)
        email_count = sum(count for _, count, _ in items)
        top_domain, top_count, _ = items[0]
        badge = category_badge(cat)
        name = CATEGORY_NAMES.get(cat, cat.title())

        rows.append([
            f"  {idx}",
            f"{badge} {name}",
            str(domain_count),
            str(email_count),
            f"{top_domain} ({top_count})",
        ])

    print_table(headers, rows, alignments=["<", "<", ">", ">", "<"])
    print()


# ---------------------------------------------------------------------------
# Display: Category view
# ---------------------------------------------------------------------------

def display_category_view(category_name, items, blocked_set, unsub_log):
    """Print the domain table for a specific category.

    Returns ordered list of domains for selection indexing.
    """
    email_count = sum(count for _, count, _ in items)
    color = CATEGORY_COLORS.get(category_name, "")
    name = CATEGORY_NAMES.get(category_name, category_name.title())

    print_header(f"{name} ({len(items)} domains, {email_count} emails)", color)

    domains = []
    headers = ["#", "Domain", "Count", "Status"]
    rows = []

    for i, (domain, count, result) in enumerate(items, 1):
        status = domain_status(domain, blocked_set, unsub_log)
        is_new = not status
        marker = colorize("*", Color.GREEN, Color.BOLD) if is_new else " "
        num_str = f"{marker}{i:>3}"
        rows.append([num_str, domain, str(count), status])
        domains.append(domain)

    print_table(headers, rows, alignments=["<", "<", ">", "<"])
    print(dim("  * = new (not blocked, not unsubscribed)"))
    print()

    return domains


# ---------------------------------------------------------------------------
# Domain status helper
# ---------------------------------------------------------------------------

def domain_status(domain, blocked_set, unsub_log):
    """Return a status string for a domain."""
    if domain in blocked_set:
        return dim("[blocked]")

    entry = unsub_log.get(domain)
    if entry:
        status = entry.get("status", "")
        if status in ("success", "opened"):
            d = entry.get("date", "")
            short_date = d[5:] if d else ""
            return dim(f"[unsub'd {short_date}]")
        if status == "failed":
            return colorize("[unsub failed]", Color.RED)

    return ""


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def prompt_category_selection(category_groups):
    """Numbered category menu.

    Returns category key string, "all", or None (quit).
    """
    # Build ordered list of available categories
    available = [cat for cat in CATEGORY_ORDER if cat in category_groups]
    total_cats = len(available)

    prompt_parts = []
    for i, cat in enumerate(available, 1):
        prompt_parts.append(str(i))
    range_str = f"1-{total_cats}" if total_cats > 1 else "1"

    choice = input(f"  > Category [{range_str}], [a]ll, [q]uit: ").strip().lower()

    if not choice or choice == "q":
        return None
    if choice == "a":
        return "all"

    try:
        idx = int(choice)
        if 1 <= idx <= total_cats:
            return available[idx - 1]
    except ValueError:
        # Try matching by name prefix
        for cat in available:
            if cat.startswith(choice):
                return cat

    print(f"  Invalid choice: {choice}")
    return "retry"


def interactive_select(domain_list, domain_counts_map, blocked_set, unsub_log):
    """Enhanced domain selection with summary and confirmation.

    Accepts numbers, ranges (1-5), 'all', 'all-new'. Shows summary before confirming.
    Returns list[str] of selected domains.
    """
    while True:
        choice = input("  Select (1,3,5 / 1-5 / all / all-new / q): ").strip().lower()

        if not choice or choice == "q":
            return []

        selected = []

        if choice == "all":
            selected = list(domain_list)
        elif choice == "all-new":
            selected = [
                d for d in domain_list
                if d not in blocked_set
                and unsub_log.get(d, {}).get("status") not in ("success", "opened")
            ]
        else:
            # Parse comma-separated numbers and ranges
            try:
                indices = []
                for part in choice.split(","):
                    part = part.strip()
                    if "-" in part and not part.startswith("-"):
                        start, end = part.split("-", 1)
                        indices.extend(range(int(start), int(end) + 1))
                    else:
                        indices.append(int(part))
                for idx in indices:
                    if 1 <= idx <= len(domain_list):
                        d = domain_list[idx - 1]
                        if d not in selected:
                            selected.append(d)
                    else:
                        print(f"  Invalid number: {idx} (valid: 1-{len(domain_list)})")
            except ValueError:
                print("  Enter numbers (1,3,5), ranges (1-5), 'all', 'all-new', or 'q'")
                continue

        if not selected:
            print("  No domains selected.")
            continue

        # Print summary
        total_emails = sum(domain_counts_map.get(d, 0) for d in selected)
        summaries = [f"{d} ({domain_counts_map.get(d, 0)})" for d in selected[:5]]
        if len(selected) > 5:
            summaries.append(f"...and {len(selected) - 5} more")
        print(f"  Selected: {', '.join(summaries)} — {bold(str(total_emails))} emails")

        confirm = input(f"  Confirm? [Y/n/c(lear)] ").strip().lower()
        if confirm in ("", "y"):
            return selected
        elif confirm == "c":
            continue  # re-prompt
        else:
            return []


# ---------------------------------------------------------------------------
# Archive flow
# ---------------------------------------------------------------------------

def run_archive_flow(domains, mail, domain_counts_map):
    """Dry run -> confirm -> archive -> return archived counts."""
    print_header("Archive: Dry Run")

    headers = ["Domain", "Emails"]
    rows = []
    counts = {}
    for domain in domains:
        count = archive_domain(mail, domain, dry_run=True)
        counts[domain] = count
        rows.append([domain, str(count)])

    print_table(headers, rows, alignments=["<", ">"])

    total = sum(counts.values())
    if total == 0:
        print("  No emails found to archive.")
        return counts

    confirm = input(f"\n  Archive {bold(str(total))} emails across {len(domains)} domains? [y/N] ").strip().lower()
    if confirm != "y":
        print("  Skipped.")
        return {}

    print_header("Archiving")
    archived_counts = {}
    for i, domain in enumerate(domains, 1):
        count = archive_domain(mail, domain, dry_run=False)
        archived_counts[domain] = count
        progress_bar(i, len(domains), label=f"{domain} ({count})")
        if count > 0:
            time.sleep(0.5)

    total_archived = sum(archived_counts.values())
    print(f"\n  Archived {bold(str(total_archived))} total emails.")
    return archived_counts


# ---------------------------------------------------------------------------
# Unsubscribe flow
# ---------------------------------------------------------------------------

def run_unsubscribe_flow(domains, unsub_log, force=False):
    """Extract links -> skip logged -> auto/open -> update log."""
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
            print(f"  Skipping {len(skipped)} already-processed: {', '.join(skipped[:5])}"
                  + (f" +{len(skipped)-5} more" if len(skipped) > 5 else ""))
        domains = eligible

    if not domains:
        print("  No domains to unsubscribe from.")
        return unsub_log

    print_header("Extracting unsubscribe links")
    mail = connect_imap(readonly=True)

    results = []
    for i, domain in enumerate(domains, 1):
        progress_bar(i, len(domains), label=f"{domain}")
        result = extract_unsubscribe_for_domain(mail, domain)
        results.append(result)
        time.sleep(0.3)

    print()  # Clear progress bar line

    mail.close()
    mail.logout()

    # Summarize findings
    one_click = [r for r in results if r["one_click"] and r["http_links"]]
    browser_only = [r for r in results if r["http_links"] and not r["one_click"]]
    no_link = [r for r in results if not r["http_links"]]

    if no_link:
        print(dim(f"  {len(no_link)} domain(s) had no unsubscribe link"))

    today = date.today().isoformat()

    # Auto one-click unsubscribe
    if one_click:
        print(f"\n  {bold(str(len(one_click)))} domain(s) support one-click unsubscribe:")
        for r in one_click:
            print(f"    - {r['domain']}")

        confirm = input(f"\n  Auto-unsubscribe from these {len(one_click)} domains? [Y/n] ").strip().lower()
        if confirm in ("", "y"):
            for i, r in enumerate(one_click, 1):
                url = r["http_links"][0]
                progress_bar(i, len(one_click), label=f"{r['domain']}")
                success = post_one_click_unsubscribe(url)
                status = "success" if success else "failed"
                unsub_log[r["domain"]] = {
                    "date": today,
                    "method": "one_click",
                    "status": status,
                    "url": url,
                }
                time.sleep(0.3)
            print()  # Clear progress bar

    # Browser-based unsubscribe
    if browser_only:
        print(f"\n  {bold(str(len(browser_only)))} domain(s) require browser unsubscribe:")
        for r in browser_only:
            url = r["http_links"][0]
            short_url = url[:70] + "..." if len(url) > 70 else url
            print(f"    - {r['domain']}: {dim(short_url)}")

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
# Legacy flat view (for "all" option)
# ---------------------------------------------------------------------------

def display_flat_table(top_domains, blocked_set, unsub_log):
    """Print numbered table with domain, count, status. Returns ordered domain list."""
    domains = []
    headers = ["#", "Domain", "Count", "Status"]
    rows = []

    for i, (domain, count) in enumerate(top_domains, 1):
        status = domain_status(domain, blocked_set, unsub_log)
        is_new = not status
        marker = colorize("*", Color.GREEN, Color.BOLD) if is_new else " "
        rows.append([f"{marker}{i:>3}", domain, str(count), status])
        domains.append(domain)

    print_table(headers, rows, alignments=["<", "<", ">", "<"])
    print(dim("  * = new (not blocked, not unsubscribed)"))
    print()
    return domains


# ---------------------------------------------------------------------------
# CLI flag parsing
# ---------------------------------------------------------------------------

def parse_flag(name):
    """Parse a --flag=value from sys.argv. Returns value or None."""
    prefix = f"{name}="
    for arg in sys.argv[1:]:
        if arg.startswith(prefix):
            return arg[len(prefix):]
    return None


# ---------------------------------------------------------------------------
# Action menu within a category or flat view
# ---------------------------------------------------------------------------

def run_action_menu(domain_list, domain_counts_map, blocked_set, unsub_log, force):
    """Show action menu, run selected action. Returns updated (blocked_set, unsub_log)."""
    print("  [a]rchive  [u]nsubscribe  [b]oth  [d]ashboard  [q]uit")
    action = input("  > ").strip().lower()

    if action in ("d", "q", ""):
        return action, blocked_set, unsub_log

    selected = []

    if action in ("a", "b"):
        selected = interactive_select(domain_list, domain_counts_map, blocked_set, unsub_log)
        if selected:
            import imaplib
            user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
            password = os.environ.get("GMAIL_APP_PASSWORD", "")
            print("  Connecting for archive...", flush=True)
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(user, password)
            mail.select("INBOX")

            archived = run_archive_flow(selected, mail, domain_counts_map)

            mail.close()
            mail.logout()

            if archived:
                newly_archived = [d for d, c in archived.items() if c > 0]
                if newly_archived:
                    append_blocked_domains(newly_archived)
                    blocked_set.update(newly_archived)

        if action == "a":
            return "stay", blocked_set, unsub_log

    if action in ("u", "b"):
        if action == "u" or not selected:
            selected = interactive_select(domain_list, domain_counts_map, blocked_set, unsub_log)

        if selected:
            unsub_log = run_unsubscribe_flow(selected, unsub_log, force=force)
            save_unsubscribe_log(unsub_log)
            print("  Unsubscribe log saved.")

        return "stay", blocked_set, unsub_log

    if action not in ("a", "u", "b", "d", "q"):
        print(f"  Unknown action: {action}")
        return "stay", blocked_set, unsub_log

    return action, blocked_set, unsub_log


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    force = "--force" in sys.argv
    category_flag = parse_flag("--category")

    # --- Fetch ---
    print_header("Inbox Audit")
    print("  Connecting to Gmail...")

    def on_progress(current, total):
        progress_bar(current, total, label="emails fetched")

    data = fetch_unread_senders(include_subjects=True, progress_fn=on_progress)
    sender_counts, domain_counts, sender_to_domain, total, domain_emails = data

    if total == 0:
        print(f"\n  Inbox zero! Nothing to do.")
        return

    # --- Classify ---
    print(f"  Classifying {len(domain_counts)} domains...")
    config = load_config_for_classifier()
    classifications = classify_domains(domain_emails, config)

    # --- Group ---
    top_domains = domain_counts.most_common(100)
    category_groups = group_by_category(top_domains, classifications)

    # Build domain -> count map for selection summaries
    domain_counts_map = dict(top_domains)

    # Load state
    blocked_set = set(load_blocked_domains())
    unsub_log = load_unsubscribe_log()

    # --- Direct category jump ---
    if category_flag:
        # Normalize flag value
        cat_key = category_flag.lower().rstrip("s")  # "newsletters" -> "newsletter"
        if cat_key not in category_groups:
            # Try with 's' suffix
            for key in category_groups:
                if key.startswith(cat_key):
                    cat_key = key
                    break
            else:
                print(f"  Category '{category_flag}' not found. Available: {', '.join(category_groups.keys())}")
                return

        items = category_groups[cat_key]
        domain_list = display_category_view(cat_key, items, blocked_set, unsub_log)

        while True:
            nav, blocked_set, unsub_log = run_action_menu(
                domain_list, domain_counts_map, blocked_set, unsub_log, force
            )
            if nav in ("q", None, ""):
                break
            if nav == "d":
                break  # Fall through to dashboard loop below
            # "stay" -> re-display and loop
            domain_list = display_category_view(cat_key, items, blocked_set, unsub_log)

        if nav != "d":
            print("\nDone.")
            return

    # --- Main loop: dashboard -> category -> actions -> back ---
    current_view = "dashboard"

    while True:
        if current_view == "dashboard":
            display_dashboard(category_groups, total, blocked_set, unsub_log)
            choice = prompt_category_selection(category_groups)

            if choice is None:
                break
            if choice == "retry":
                continue
            if choice == "all":
                current_view = "all"
            else:
                current_view = choice

        elif current_view == "all":
            # Flat legacy view
            print_header(f"All Domains ({len(top_domains)} domains, {total} emails)")
            domain_list = display_flat_table(top_domains, blocked_set, unsub_log)

            nav, blocked_set, unsub_log = run_action_menu(
                domain_list, domain_counts_map, blocked_set, unsub_log, force
            )
            if nav in ("q", None, ""):
                break
            if nav == "d":
                current_view = "dashboard"
            # "stay" -> loop to re-display

        else:
            # Category view
            cat_key = current_view
            if cat_key not in category_groups:
                current_view = "dashboard"
                continue

            items = category_groups[cat_key]
            domain_list = display_category_view(cat_key, items, blocked_set, unsub_log)

            nav, blocked_set, unsub_log = run_action_menu(
                domain_list, domain_counts_map, blocked_set, unsub_log, force
            )
            if nav in ("q", None, ""):
                break
            if nav == "d":
                current_view = "dashboard"
            # "stay" -> loop to re-display

    print("\nDone.")


if __name__ == "__main__":
    main()
