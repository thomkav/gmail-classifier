---
name: auto-archive
aliases: [auto-archive-inbox]
description: Automatically classify and archive bulk mail, surfacing only ambiguous cases for review
usage: /auto-archive [--threshold=N]
examples:
  - /auto-archive
  - /auto-archive --threshold=80
help_text: |
  Runs the auto-archive pipeline: classifies all unread domains, applies
  confidence-based rules to decide what to archive, and handles bulk cleanup
  without requiring manual TUI navigation.

  Auto-archive rules (in priority order):
  - Already in archived_domains → re-archive (slip-through)
  - Promotions with confidence >= threshold (default 70%) → archive
  - Newsletters with LOW quality tier → archive
  - Newsletters in archive_newsletters preference → archive
  - Receipts, notifications, unknown, keep_senders → skip (review manually)
---

You are running the `/auto-archive` workflow. Follow these steps exactly.

## Step 1: Dry run

Run the dry-run to get the classification summary:

```bash
make -C ~/.claude/plugins/gmail-classifier auto-archive-dry-run
```

If `~/.claude/plugins/gmail-classifier` doesn't exist, use the project directory instead.

Parse the output to understand:
- How many domains will be archived vs skipped
- Total email count affected
- The reason for each archive decision

## Step 2: Present findings

Show the user a clear summary:
- N domains to archive (M emails total)
- Grouped by reason: promotions, newsletters (low quality), blocked re-archive
- Highlight anything that looks surprising or might be a false positive

Ask: "Should I apply this? You can also adjust the confidence threshold (currently 70%) or exclude specific domains."

## Step 3: Handle user response

**If user confirms (yes/apply/go/proceed):**
- Run `make -C ~/.claude/plugins/gmail-classifier auto-archive`
- Report: domains archived, email count, how many new entries added to archived_domains

**If user wants to adjust threshold:**
- Re-run dry-run with `--threshold=N`: `make -C ~/.claude/plugins/gmail-classifier auto-archive-dry-run` then `python3 scripts/auto_archive.py --dry-run --threshold=N`
- Show updated summary

**If user wants to exclude specific domains:**
- Note the exclusions
- Run apply, then explain the excluded domains can be handled via `make audit-email` for manual review

**If user declines:**
- Summarize what was found, suggest running `make audit-email` for interactive review

## Step 4: After apply

Report final results:
- "Archived X emails from N domains"
- "Added N new domains to archived_domains in .local.md"
- Offer to show which domains were skipped for manual follow-up
