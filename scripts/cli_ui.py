#!/usr/bin/env python3
"""
CLI UI Helpers — powered by Rich

Drop-in replacement for the hand-rolled ANSI version. Exports the same
public API (Color, colorize, bold, dim, print_header, progress_bar,
print_table, category_badge, plus the category constants) but delegates
to Rich for correct column-width handling and consistent styling.
"""

import sys
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box as rich_box


console = Console(highlight=False)


# ---------------------------------------------------------------------------
# Color constants — Rich style names
# ---------------------------------------------------------------------------

class Color:
    RESET = ""
    BOLD = "bold"
    DIM = "dim"
    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"
    BLUE = "blue"
    MAGENTA = "magenta"
    CYAN = "cyan"
    WHITE = "white"


# Category → Rich style mapping
CATEGORY_COLORS = {
    "newsletter": Color.CYAN,
    "promotion": Color.YELLOW,
    "receipt": Color.GREEN,
    "notification": Color.MAGENTA,
    "unknown": Color.DIM,
}

CATEGORY_BADGES = {
    "newsletter": "NWS",
    "promotion": "PRO",
    "receipt": "RCP",
    "notification": "NTF",
    "unknown": "---",
}

CATEGORY_ORDER = ["newsletter", "promotion", "receipt", "notification", "unknown"]

CATEGORY_NAMES = {
    "newsletter": "Newsletters",
    "promotion": "Promotions",
    "receipt": "Receipts",
    "notification": "Notifications",
    "unknown": "Uncategorized",
}


# ---------------------------------------------------------------------------
# Markup helpers
# ---------------------------------------------------------------------------

def colorize(text, *styles):
    """Wrap text in Rich markup. Returns plain text when no styles given."""
    if not styles:
        return str(text)
    style = " ".join(s for s in styles if s)
    return f"[{style}]{text}[/]"


def bold(text):
    return f"[bold]{text}[/]"


def dim(text):
    return f"[dim]{text}[/]"


# ---------------------------------------------------------------------------
# Structural output
# ---------------------------------------------------------------------------

def print_header(title, color=None):
    """Print a styled section header using Rich Rule."""
    console.print()
    title_markup = f"[bold {color}]{title}[/]" if color else f"[bold]{title}[/]"
    console.rule(title_markup, align="left")


# ---------------------------------------------------------------------------
# Progress bar — plain print with \r overwrite (bypasses Rich buffering)
# ---------------------------------------------------------------------------

def progress_bar(current, total, width=30, label=""):
    """Overwriting single-line progress bar."""
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
        print()


# ---------------------------------------------------------------------------
# Table formatting
# ---------------------------------------------------------------------------

def print_table(headers, rows, alignments=None):
    """Print a formatted table using Rich's Table for correct column widths."""
    if not rows:
        return

    col_count = len(headers)
    if alignments is None:
        alignments = ["<"] * col_count

    justify_map = {"<": "left", ">": "right"}

    table = Table(
        box=rich_box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold",
        pad_edge=True,
        show_edge=False,
    )

    for i, header in enumerate(headers):
        justify = justify_map.get(alignments[i] if i < len(alignments) else "<", "left")
        table.add_column(str(header), justify=justify, no_wrap=True)

    for row in rows:
        cells = []
        for i in range(col_count):
            cell = str(row[i]) if i < len(row) else ""
            cells.append(Text.from_markup(cell))
        table.add_row(*cells)

    console.print(table)


# ---------------------------------------------------------------------------
# Category badge
# ---------------------------------------------------------------------------

def category_badge(category_name):
    """Return a Rich markup badge like [NWS]."""
    key = (category_name or "unknown").lower()
    badge = CATEGORY_BADGES.get(key, "---")
    color = CATEGORY_COLORS.get(key, Color.DIM)
    return f"[{color} bold][{badge}][/]"
