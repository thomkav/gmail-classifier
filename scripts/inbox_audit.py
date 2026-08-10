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
CONFIG_JSON = os.path.join(PLUGIN_DIR, "config.json")
UNSUB_LOG = os.path.join(PLUGIN_DIR, ".unsubscribe_log.json")

sys.path.insert(0, SCRIPT_DIR)

from sender_audit import fetch_unread_senders
from mass_archive import archive_domain
from extract_unsubscribe import (
    connect_imap,
    extract_unsubscribe_for_domain,
    post_one_click_unsubscribe,
)
from classify_logic import EmailClassifier, Category, ClassificationResult
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
    console,
)


# ---------------------------------------------------------------------------
# Unsubscribe log (.unsubscribe_log.json)
# ---------------------------------------------------------------------------

def load_unsubscribe_log(path=None):
    """Read .unsubscribe_log.json -> {domain: {date, method, status, url}}.
    `path` lets callers (e.g. the web app, per account) point at a different file;
    defaults to the single-account CLI location."""
    path = path or UNSUB_LOG
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_unsubscribe_log(log, path=None):
    """Write log back to JSON file."""
    with open(path or UNSUB_LOG, "w") as f:
        json.dump(log, f, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# Config loading (config.json)
# ---------------------------------------------------------------------------

def _load_config_json(path=None) -> dict:
    path = path or CONFIG_JSON
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_config_json(cfg: dict, path=None) -> None:
    with open(path or CONFIG_JSON, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def load_archived_domains(path=None) -> list:
    cfg = _load_config_json(path)
    return list(cfg.get("preferences", {}).get("archived_domains", []))


def load_config_for_classifier(path=None) -> dict:
    """Return config in the shape EmailClassifier expects:
    {'categories': {...}, 'learned_preferences': {...}, 'manual_classifications': {...}, 'llm_classifications': {...}}
    `path` lets callers (e.g. the web app, per account) point at a different config.json.
    """
    cfg = _load_config_json(path)
    return {
        "categories": cfg.get("categories", {}),
        "learned_preferences": cfg.get("preferences", {}),
        "manual_classifications": cfg.get("manual_classifications", {}),
        "llm_classifications": cfg.get("llm_classifications", {}),
    }


def append_archived_domains(new_domains: list, path=None) -> None:
    """Append new entries to preferences.archived_domains in config.json."""
    if not new_domains:
        return
    cfg = _load_config_json(path)
    prefs = cfg.setdefault("preferences", {})
    existing = set(prefs.get("archived_domains", []))
    to_add = [d for d in new_domains if d not in existing]
    if not to_add:
        return
    prefs.setdefault("archived_domains", []).extend(to_add)
    _save_config_json(cfg, path)
    print(f"  Updated config.json: added {len(to_add)} domain(s) to archived_domains")


# ---------------------------------------------------------------------------
# Classification integration
# ---------------------------------------------------------------------------

_LLM_CAT_ACTION = {
    "newsletter": "review",
    "promotion": "archive",
    "receipt": "archive",
    "notification": "keep",
}


def classify_domains(domain_emails, config):
    """Classify each domain, applying manual and LLM overrides after programmatic.

    Returns dict[str, ClassificationResult].
    """
    classifier = EmailClassifier(config)
    manual_cls = config.get("manual_classifications", {})
    llm_cls = config.get("llm_classifications", {})
    results = {}

    for domain, emails in domain_emails.items():
        sample = emails[-1] if emails else {}
        result = classifier.classify({
            "sender": sample.get("sender", ""),
            "subject": sample.get("subject", ""),
            "preview": "",
        })

        if domain in manual_cls:
            m = manual_cls[domain]
            cat_str = m.get("category", "unknown")
            try:
                cat = Category(cat_str)
            except ValueError:
                cat = Category.UNKNOWN
            result = ClassificationResult(
                category=cat,
                confidence=100,
                tier=result.tier,
                reasoning=f"Manual: {cat_str}",
                suggested_action=_LLM_CAT_ACTION.get(cat_str, result.suggested_action),
                source="manual",
            )
        elif result.category == Category.UNKNOWN and domain in llm_cls:
            llm = llm_cls[domain]
            cat_str = llm.get("category", "unknown")
            confidence = llm.get("confidence", 0)
            if cat_str not in ("unknown", "personal") and confidence >= 50:
                try:
                    cat = Category(cat_str)
                    result = ClassificationResult(
                        category=cat,
                        confidence=confidence,
                        tier=result.tier,
                        reasoning=f"LLM: {llm.get('reasoning', '')}",
                        suggested_action=_LLM_CAT_ACTION.get(cat_str, "review"),
                        source="llm",
                    )
                except ValueError:
                    pass

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
# Recidivist detection
# ---------------------------------------------------------------------------

def find_recidivists(domain_counts, archived_set, unsub_log):
    """Find domains where we explicitly unsubscribed but are still emailing.

    Note: domains in archived_set were just archived (no Gmail filter), so
    receiving new mail from them is expected — not recidivism.

    Returns:
        dict with:
            'unsub': set of domains (explicitly unsubscribed, still emailing)
    """
    current_domains = set(domain_counts.keys())

    unsub = set()
    for domain, entry in unsub_log.items():
        if entry.get("status") in ("success", "opened") and domain in current_domains:
            unsub.add(domain)

    return {"unsub": unsub}


# ---------------------------------------------------------------------------
# Display: Dashboard
# ---------------------------------------------------------------------------

def display_dashboard(category_groups, total, archived_set, unsub_log, recidivists=None):
    """Print the category summary table."""
    print_header("Dashboard")
    console.print(f"  {bold(str(total))} unread across {bold(str(sum(len(v) for v in category_groups.values())))} domains\n")

    # Recidivist warning block
    if recidivists:
        n_unsub = len(recidivists.get("unsub", set()))
        if n_unsub > 0:
            warning = colorize(
                f"  ⚠  {n_unsub} unsubscribe{'s' if n_unsub != 1 else ''} ignored: "
                f"still emailing after opt-out",
                Color.RED, Color.BOLD
            )
            console.print(warning)
            console.print(colorize("     Select [r] at the category prompt to review", Color.RED))
            console.print()

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

def display_category_view(category_name, items, archived_set, unsub_log, recidivists=None):
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
        status = domain_status(domain, archived_set, unsub_log, recidivists)
        is_new = not status
        marker = colorize("*", Color.GREEN, Color.BOLD) if is_new else " "
        num_str = f"{marker}{i:>3}"
        rows.append([num_str, domain, str(count), status])
        domains.append(domain)

    print_table(headers, rows, alignments=["<", "<", ">", "<"])
    console.print(dim("  * = new (not blocked, not unsubscribed)"))

    return domains


# ---------------------------------------------------------------------------
# Domain status helper
# ---------------------------------------------------------------------------

def domain_status(domain, archived_set, unsub_log, recidivists=None):
    """Return a status string for a domain."""
    if recidivists:
        if domain in recidivists.get("unsub", set()):
            return colorize("[recidivist!]", Color.RED, Color.BOLD)

    if domain in archived_set:
        return dim("[archived]")

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

def prompt_category_selection(category_groups, has_recidivists=False):
    """Numbered category menu.

    Returns category key string, "all", "recidivists", or None (quit).
    """
    # Build ordered list of available categories
    available = [cat for cat in CATEGORY_ORDER if cat in category_groups]
    total_cats = len(available)

    range_str = f"1-{total_cats}" if total_cats > 1 else "1"
    recidivist_opt = ", [r]ecidivists" if has_recidivists else ""

    choice = input(f"  > Category [{range_str}], [a]ll{recidivist_opt}, [q]uit: ").strip().lower()

    if not choice or choice == "q":
        return None
    if choice == "a":
        return "all"
    if choice == "r" and has_recidivists:
        return "recidivists"

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


def interactive_select(domain_list, domain_counts_map, archived_set, unsub_log):
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
                if d not in archived_set
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
        console.print(f"  Selected: {', '.join(summaries)} — {bold(str(total_emails))} emails")

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

    confirm = input(f"\n  Archive {len(domains)} domains ({total} emails)? [y/N] ").strip().lower()
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
    console.print(f"\n  Archived {bold(str(total_archived))} total emails.")
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
        console.print(dim(f"  {len(no_link)} domain(s) had no unsubscribe link"))

    today = date.today().isoformat()

    # Auto one-click unsubscribe
    if one_click:
        console.print(f"\n  {bold(str(len(one_click)))} domain(s) support one-click unsubscribe:")
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
        console.print(f"\n  {bold(str(len(browser_only)))} domain(s) require browser unsubscribe:")
        for r in browser_only:
            url = r["http_links"][0]
            short_url = url[:70] + "..." if len(url) > 70 else url
            console.print(f"    - {r['domain']}: {dim(short_url)}")

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

def display_flat_table(top_domains, archived_set, unsub_log, recidivists=None):
    """Print numbered table with domain, count, status. Returns ordered domain list."""
    domains = []
    headers = ["#", "Domain", "Count", "Status"]
    rows = []

    for i, (domain, count) in enumerate(top_domains, 1):
        status = domain_status(domain, archived_set, unsub_log, recidivists)
        is_new = not status
        marker = colorize("*", Color.GREEN, Color.BOLD) if is_new else " "
        rows.append([f"{marker}{i:>3}", domain, str(count), status])
        domains.append(domain)

    print_table(headers, rows, alignments=["<", "<", ">", "<"])
    console.print(dim("  * = new (not blocked, not unsubscribed)"))
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

def run_action_menu(domain_list, domain_counts_map, archived_set, unsub_log, force):
    """Show action menu, run selected action. Returns updated (archived_set, unsub_log)."""
    print("  [a]rchive  [u]nsubscribe  [b]oth  [d]ashboard  [q]uit")
    action = input("  > ").strip().lower()

    if action in ("d", "q", ""):
        return action, archived_set, unsub_log

    selected = []

    if action in ("a", "b"):
        selected = interactive_select(domain_list, domain_counts_map, archived_set, unsub_log)
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
                    append_archived_domains(newly_archived)
                    archived_set.update(newly_archived)

        if action == "a":
            return "stay", archived_set, unsub_log

    if action in ("u", "b"):
        if action == "u" or not selected:
            selected = interactive_select(domain_list, domain_counts_map, archived_set, unsub_log)

        if selected:
            unsub_log = run_unsubscribe_flow(selected, unsub_log, force=force)
            save_unsubscribe_log(unsub_log)
            print("  Unsubscribe log saved.")

        return "stay", archived_set, unsub_log

    if action not in ("a", "u", "b", "d", "q"):
        print(f"  Unknown action: {action}")
        return "stay", archived_set, unsub_log

    return action, archived_set, unsub_log


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
    archived_set = set(load_archived_domains())
    unsub_log = load_unsubscribe_log()

    # --- Recidivist detection ---
    recidivists = find_recidivists(domain_counts, archived_set, unsub_log)
    has_recidivists = bool(recidivists["unsub"])

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
        domain_list = display_category_view(cat_key, items, archived_set, unsub_log, recidivists)

        while True:
            nav, archived_set, unsub_log = run_action_menu(
                domain_list, domain_counts_map, archived_set, unsub_log, force
            )
            if nav in ("q", None, ""):
                break
            if nav == "d":
                break  # Fall through to dashboard loop below
            # "stay" -> re-display and loop
            domain_list = display_category_view(cat_key, items, archived_set, unsub_log, recidivists)

        if nav != "d":
            print("\nDone.")
            return

    # --- Main loop: dashboard -> category -> actions -> back ---
    current_view = "dashboard"

    while True:
        if current_view == "dashboard":
            display_dashboard(category_groups, total, archived_set, unsub_log, recidivists)
            choice = prompt_category_selection(category_groups, has_recidivists)

            if choice is None:
                break
            if choice == "retry":
                continue
            if choice == "all":
                current_view = "all"
            elif choice == "recidivists":
                current_view = "recidivists"
            else:
                current_view = choice

        elif current_view == "recidivists":
            # Recidivist view: show offending domains as a flat table
            recid_domains = [
                (d, domain_counts_map[d])
                for d in sorted(recidivists["unsub"],
                                key=lambda x: domain_counts_map.get(x, 0), reverse=True)
                if d in domain_counts_map
            ]
            print_header(f"Recidivists ({len(recid_domains)} domains)", Color.RED)
            if recid_domains:
                headers = ["#", "Domain", "Unread", "Prior Action"]
                rows = []
                for i, (domain, count) in enumerate(recid_domains, 1):
                    if domain in recidivists["unsub"]:
                        entry = unsub_log.get(domain, {})
                        date_short = entry.get("date", "")[5:] or ""
                        action = f"unsubscribed {date_short}" if date_short else "unsubscribed"
                    else:
                        action = "blocked"
                    rows.append([
                        f"  {i}",
                        colorize(domain, Color.RED, Color.BOLD),
                        str(count),
                        action,
                    ])
                print_table(headers, rows, alignments=["<", "<", ">", "<"])

            domain_list = [d for d, _ in recid_domains]
            nav, archived_set, unsub_log = run_action_menu(
                domain_list, domain_counts_map, archived_set, unsub_log, force
            )
            if nav in ("q", None, ""):
                break
            if nav == "d":
                current_view = "dashboard"
            # "stay" -> loop to re-display

        elif current_view == "all":
            # Flat legacy view
            print_header(f"All Domains ({len(top_domains)} domains, {total} emails)")
            domain_list = display_flat_table(top_domains, archived_set, unsub_log, recidivists)

            nav, archived_set, unsub_log = run_action_menu(
                domain_list, domain_counts_map, archived_set, unsub_log, force
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
            domain_list = display_category_view(cat_key, items, archived_set, unsub_log, recidivists)

            nav, archived_set, unsub_log = run_action_menu(
                domain_list, domain_counts_map, archived_set, unsub_log, force
            )
            if nav in ("q", None, ""):
                break
            if nav == "d":
                current_view = "dashboard"
            # "stay" -> loop to re-display

    print("\nDone.")


if __name__ == "__main__":
    main()
