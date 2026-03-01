#!/usr/bin/env python3
"""
CLI UI Helpers

ANSI color constants, progress bar, table formatting, and category badges.
All stdlib — no external deps. Respects NO_COLOR env var and --no-color flag.
"""

import os
import sys


# ---------------------------------------------------------------------------
# Color detection
# ---------------------------------------------------------------------------

def _color_enabled():
    """Return True if ANSI colors should be used."""
    if os.environ.get("NO_COLOR"):
        return False
    if "--no-color" in sys.argv:
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_USE_COLOR = _color_enabled()


# ---------------------------------------------------------------------------
# ANSI codes
# ---------------------------------------------------------------------------

class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


# Category → color mapping
CATEGORY_COLORS = {
    "newsletter": Color.CYAN,
    "promotion": Color.YELLOW,
    "receipt": Color.GREEN,
    "notification": Color.MAGENTA,
    "unknown": Color.DIM,
}

# Category → short badge
CATEGORY_BADGES = {
    "newsletter": "NWS",
    "promotion": "PRO",
    "receipt": "RCP",
    "notification": "NTF",
    "unknown": "---",
}

# Display order for dashboard
CATEGORY_ORDER = ["newsletter", "promotion", "receipt", "notification", "unknown"]

# Human-readable names
CATEGORY_NAMES = {
    "newsletter": "Newsletters",
    "promotion": "Promotions",
    "receipt": "Receipts",
    "notification": "Notifications",
    "unknown": "Uncategorized",
}


# ---------------------------------------------------------------------------
# Colorize helpers
# ---------------------------------------------------------------------------

def colorize(text, *codes):
    """Wrap text in ANSI codes. Returns plain text when colors disabled."""
    if not _USE_COLOR or not codes:
        return str(text)
    prefix = "".join(codes)
    return f"{prefix}{text}{Color.RESET}"


def bold(text):
    return colorize(text, Color.BOLD)


def dim(text):
    return colorize(text, Color.DIM)


# ---------------------------------------------------------------------------
# Structural output
# ---------------------------------------------------------------------------

def get_terminal_width():
    """Return terminal width with 80-col fallback."""
    try:
        return os.get_terminal_size().columns
    except (AttributeError, ValueError, OSError):
        return 80


def print_header(title, color=None):
    """Print a styled section header with rules."""
    width = min(get_terminal_width(), 70)
    rule_len = max(width - len(title) - 4, 10)
    prefix = f"{Color.BOLD}{color}" if _USE_COLOR and color else (Color.BOLD if _USE_COLOR else "")
    suffix = Color.RESET if _USE_COLOR else ""
    print(f"\n{prefix}{title} {'─' * rule_len}{suffix}")


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

def progress_bar(current, total, width=30, label=""):
    """Overwriting progress bar on a single line."""
    if total == 0:
        return
    frac = current / total
    filled = int(width * frac)
    bar = "=" * filled
    if filled < width:
        bar += ">"
        bar += " " * (width - filled - 1)
    else:
        bar = "=" * width

    line = f"  [{bar}] {current}/{total}"
    if label:
        line += f" {label}"

    print(f"\r{line}", end="", flush=True)
    if current >= total:
        print()  # newline when done


# ---------------------------------------------------------------------------
# Table formatting
# ---------------------------------------------------------------------------

def print_table(headers, rows, alignments=None):
    """Print a formatted table with column alignment.

    alignments: list of '<' (left) or '>' (right), defaults to left.
    """
    if not rows:
        return

    col_count = len(headers)
    if alignments is None:
        alignments = ["<"] * col_count

    # Calculate column widths
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < col_count:
                widths[i] = max(widths[i], len(str(cell)))

    def fmt_row(cells, is_header=False):
        parts = []
        for i, cell in enumerate(cells):
            if i >= col_count:
                break
            w = widths[i]
            s = str(cell)
            if alignments[i] == ">":
                s = s.rjust(w)
            else:
                s = s.ljust(w)
            parts.append(s)
        line = "  " + "  ".join(parts)
        if is_header and _USE_COLOR:
            return colorize(line, Color.BOLD)
        return line

    # Header
    print(fmt_row(headers, is_header=True))

    # Separator
    sep_parts = []
    for i in range(col_count):
        sep_parts.append("─" * widths[i])
    print("  " + "  ".join(sep_parts))

    # Rows
    for row in rows:
        print(fmt_row(row))


# ---------------------------------------------------------------------------
# Category badge
# ---------------------------------------------------------------------------

def category_badge(category_name):
    """Return a colored inline badge like [NWS]."""
    key = category_name.lower() if category_name else "unknown"
    badge = CATEGORY_BADGES.get(key, "---")
    color = CATEGORY_COLORS.get(key, Color.DIM)
    return colorize(f"[{badge}]", color, Color.BOLD)
