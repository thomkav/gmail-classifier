#!/usr/bin/env python3
"""
Recidivist Detection

Finds senders that are still emailing after an explicit unsubscribe request
(status: success or opened in .unsubscribe_log.json).

Note: domains in archived_domains were only archived (no Gmail filter), so
receiving new mail from them is expected — not flagged here.

Usage:
    python3 recidivist_check.py          # Formatted console report
    python3 recidivist_check.py --json   # JSON output only
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from inbox_audit import load_unsubscribe_log
from sender_audit import fetch_unread_senders
from cli_ui import Color, colorize, bold, dim, print_header, print_table, console


def find_recidivists():
    """Fetch current inbox and find senders still emailing after opt-out.

    Returns:
        dict with keys:
            'unsub_recidivists': list of dicts (domain, count, unsub_date, unsub_method, status)
            'total_unread': int
    """
    unsub_log = load_unsubscribe_log()

    print("  Connecting to Gmail...", file=sys.stderr)
    sender_counts, domain_counts, _, total = fetch_unread_senders()

    current_domains = set(domain_counts.keys())

    unsub_recidivists = []
    for domain, entry in unsub_log.items():
        if entry.get("status") in ("success", "opened") and domain in current_domains:
            unsub_recidivists.append({
                "domain": domain,
                "count": domain_counts[domain],
                "unsub_date": entry.get("date", ""),
                "unsub_method": entry.get("method", ""),
                "unsub_status": entry.get("status", ""),
            })
    unsub_recidivists.sort(key=lambda x: x["count"], reverse=True)

    return {
        "unsub_recidivists": unsub_recidivists,
        "total_unread": total,
    }


def print_report(results):
    """Print formatted console report."""
    unsub = results["unsub_recidivists"]

    print_header("Recidivist Report", Color.RED)

    if not unsub:
        console.print("  No recidivists found — all unsubscribed domains are quiet.")
        return

    console.print(f"  {bold(colorize(str(len(unsub)), Color.RED))} sender(s) still emailing after explicit opt-out:\n")

    headers = ["Domain", "Unread", "Unsub Date", "Method", "Status"]
    rows = []
    for r in unsub:
        date_short = r["unsub_date"][5:] if r["unsub_date"] else ""
        rows.append([
            colorize(r["domain"], Color.RED, Color.BOLD),
            str(r["count"]),
            date_short,
            r["unsub_method"],
            r["unsub_status"],
        ])
    print_table(headers, rows, alignments=["<", ">", "<", "<", "<"])
    print()


def main():
    json_mode = "--json" in sys.argv

    if not json_mode:
        print_header("Recidivist Check")

    results = find_recidivists()

    if json_mode:
        print(json.dumps(results, indent=2))
    else:
        print_report(results)


if __name__ == "__main__":
    main()
