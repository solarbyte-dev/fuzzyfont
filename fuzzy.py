import argparse
import json
import math
import sys
import subprocess
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from matplotlib import font_manager


console = Console()


# Auto-install dependencies if missing
required = ["rich", "matplotlib"]
import importlib.util
for pkg in required:
    if importlib.util.find_spec(pkg) is None:
        print(f"Installing missing dependency: {pkg}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])


# Fonts discovery & helpers
def get_all_fonts():
    """Return all system fonts as list of dicts: {'name','path'}."""
    fonts = set()
    for ext in ("ttf", "otf"):
        fonts.update(font_manager.findSystemFonts(fontext=ext))

    out = []
    seen = set()

    for f in fonts:
        try:
            prop = font_manager.FontProperties(fname=f)
            name = prop.get_name()
            if not name:
                continue
            key = (name.lower(), Path(f).resolve())
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": name, "path": str(Path(f).resolve())})
        except Exception:
            # skip unreadable fonts
            continue
    return sorted(out, key=lambda x: x["name"].lower())

# Predefined overrides for common fonts
FONT_CATEGORY_OVERRIDES = {
    "fira code": "mono",
    "ubuntu mono": "mono",
    "source code pro": "mono",
    "inconsolata": "mono",
    "courier new": "mono",
    "roboto": "sans",
    "open sans": "sans",
    "lato": "sans",
    "noto sans": "sans",
    "arial": "sans",
    "helvetica": "sans",
    "segoe ui": "sans",
    "times new roman": "serif",
    "georgia": "serif",
    "cambria": "serif",
    "palatino": "serif",
    "noto serif": "serif",
    "impact": "display",
    "stencil": "display",
    "wingdings": "symbol",
    "webdings": "symbol",
    "emoji one": "symbol",
}

# Robust classification
def classify_font(font_name, font_path=None):
    """
    Classify a font into categories: mono, serif, sans, display, symbol, other using override mapping, font family metadata and heuristic
    """
    name = font_name.lower()
    cats = set()

    # 1. Check override mapping
    for key, cat in FONT_CATEGORY_OVERRIDES.items():
        if key in name:
            cats.add(cat)
            break  # stop at first match

    # 2. Use FontProperties if path is provided
    if font_path and not cats:
        try:
            from matplotlib import font_manager
            prop = font_manager.FontProperties(fname=font_path)
            family = prop.get_family()
            if family:
                family_name = family[0].lower()
                if any(x in family_name for x in ["mono", "courier", "code", "console", "fixed", "menlo", "monaco"]):
                    cats.add("mono")
                elif any(x in family_name for x in ["serif", "times", "georgia", "cambria", "palatino"]):
                    cats.add("serif")
                elif any(x in family_name for x in ["sans", "arial", "helvetica", "segoe", "noto sans", "open sans", "roboto"]):
                    cats.add("sans")
        except Exception:
            pass  # fallback to heuristic

    # 3. Heuristic parsing of name (fallback)
    if not cats:
        if any(x in name for x in ["mono", "code", "console", "fixed", "menlo", "monaco"]):
            cats.add("mono")
        if any(x in name for x in ["serif", "times", "georgia", "cambria", "palatino"]):
            cats.add("serif")
        if any(x in name for x in ["sans", "arial", "helvetica", "segoe", "noto sans", "open sans", "roboto"]):
            cats.add("sans")
        if any(x in name for x in ["display", "poster", "impact", "headline", "stencil", "black", "grotesk"]):
            cats.add("display")
        if any(x in name for x in ["symbol", "wingdings", "dingbat", "emoji", "webdings"]):
            cats.add("symbol")

    # 4. Fallback if still nothing matched
    if not cats:
        cats.add("other")
    return cats


def attach_classification(fonts):
    """Return new list with 'cats' key (set of categories)."""
    for f in fonts:
        f["cats"] = classify_font(f["name"])
    return fonts


# Filtering, searching
def filter_fonts(fonts, mono=False, serif=False, sans=False, display=False, symbol=False):
    # If no flag requested, return fonts unchanged
    flags = {"mono": mono, "serif": serif, "sans": sans, "display": display, "symbol": symbol}
    if not any(flags.values()):
        return fonts
    want = {k for k, v in flags.items() if v}
    filtered = [f for f in fonts if f["cats"] & want]
    return filtered


# Stats
def compute_stats(fonts):
    """Return dict: counts per category + total + top examples."""
    counts = {"mono": 0, "serif": 0, "sans": 0, "display": 0, "symbol": 0, "other": 0}
    examples = {k: [] for k in counts}
    for f in fonts:
        for c in f["cats"]:
            if c in counts:
                counts[c] += 1
                if len(examples[c]) < 5:
                    examples[c].append(f["name"])
    total = len(fonts)
    return {"total": total, "counts": counts, "examples": examples}


def print_stats(stats):
    table = Table(title="Font Statistics", show_lines=False)
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right", style="green")
    table.add_column("Examples", style="magenta", overflow="fold")
    for cat, cnt in stats["counts"].items():
        ex = ", ".join(stats["examples"].get(cat, [])) or "-"
        table.add_row(cat, str(cnt), ex)
    table.add_row("total", str(stats["total"]), "")
    console.print(table)


# Display / export
def show_fonts_table(fonts, start=0, limit=None):
    """Show fonts in a rich table (optionally paginate with start and limit)."""
    subset = fonts if limit is None else fonts[start:start + limit]
    table = Table(title=f"Available Fonts ({len(fonts)}) — showing {len(subset)}", show_lines=False)
    table.add_column("#", style="dim", width=6)
    table.add_column("Font Name", style="cyan", overflow="fold")
    table.add_column("Categories", style="yellow", no_wrap=False, overflow="fold")
    table.add_column("File Path", style="dim", overflow="fold")

    for i, f in enumerate(subset, start=start + 1):
        cats = ", ".join(sorted(f["cats"]))
        table.add_row(str(i), f["name"], cats, f["path"])
    console.print(table)


def export_fonts(fonts, output_path):
    """Export font list to JSON or TXT file"""
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Convert sets to lists for JSON safety
        exportable_fonts = []
        for f in fonts:
            exportable_fonts.append({
                "name": f["name"],
                "path": f["path"],
                "categories": sorted(f.get("cats", []))
            })

        if output_path.suffix.lower() == ".json":
            with open(output_path, "w", encoding="utf-8") as fh:
                json.dump(exportable_fonts, fh, indent=2, ensure_ascii=False)
            console.print(f"[bold green]Exported {len(fonts)} fonts to {output_path}[/bold green]")
        else:
            with open(output_path, "w", encoding="utf-8") as fh:
                for f in exportable_fonts:
                    cats = ",".join(f["categories"])
                    fh.write(f"{f['name']}\t{cats}\t{f['path']}\n")
            console.print(f"[bold green]Exported {len(fonts)} fonts to {output_path}[/bold green]")

    except Exception as e:
        console.print(f"[bold red]Failed to export fonts:[/bold red] {e}")

# Textual TUI (simple)
def run_tui(all_fonts):
    """
    Simple terminal-driven interactive UI.
    Commands:
      l         -> list (paged)
      n / p     -> next / previous page while listing
      s <term>  -> search by name
      t         -> show stats
      f         -> toggle filter menu
      e <path>  -> export current list
      q         -> quit
      h         -> help
    """
    fonts = all_fonts[:]  # current working set (after filters/search)
    applied_filters = {"mono": False, "serif": False, "sans": False, "display": False, "symbol": False}
    search_term = ""
    page = 0
    page_size = 16

    def refresh_working_set():
        nonlocal fonts
        # attach classification already present
        filtered = filter_fonts(all_fonts, **applied_filters)
        if search_term:
            term = search_term.lower()
            filtered = [f for f in filtered if term in f["name"].lower()]
        fonts = filtered

    def show_menu():
        panel = Panel.fit(
            "[b]Commands[/b]\n"
            " l            List fonts (paged)\n"
            " n / p        Next / previous page while listing\n"
            " s <term>     Search fonts by name (empty to clear)\n"
            " f            Toggle filters (mono/serif/sans/display/symbol)\n"
            " t            Show statistics\n"
            " e <path>     Export current list to path (txt or .json)\n"
            " q            Quit\n"
            " h            Show this help\n\n"
            f"[b]Active filters:[/b] {', '.join(k for k, v in applied_filters.items() if v) or 'none'}\n"
            f"[b]Search:[/b] '{search_term or ''}'  [b]Matching fonts:[/b] {len(fonts)}",
            title="FuzzyFont TUI",
            subtitle="Press 'h' for help",
        )
        console.clear()
        console.print(panel)

    def toggle_filters_interactive():
        # quick text menu to toggle each filter
        while True:
            console.print("\nToggle filters (type number to toggle, Enter to return):")
            for i, k in enumerate(applied_filters.keys(), start=1):
                console.print(f"  {i}. [{ 'green' if applied_filters[k] else 'red'}]{k}[/{ 'green' if applied_filters[k] else 'red'}]")
            console.print("  0. Done")
            choice = console.input("[bold]> [/bold]").strip()
            if choice == "":
                return
            if choice == "0":
                return
            try:
                n = int(choice)
                if 1 <= n <= len(applied_filters):
                    key = list(applied_filters.keys())[n - 1]
                    applied_filters[key] = not applied_filters[key]
                    refresh_working_set()
                else:
                    console.print("[red]Invalid number[/red]")
            except ValueError:
                console.print("[red]Enter a number[/red]")

    refresh_working_set()
    show_menu()

    while True:
        cmdline = console.input("[bold cyan]TUI> [/bold cyan]").strip()
        if not cmdline:
            continue
        parts = cmdline.split(maxsplit=1)
        cmd = parts[0].lower()

        if cmd == "h":
            show_menu()
            continue

        if cmd == "q":
            console.print("[bold]Goodbye — exiting TUI.[/bold]")
            return

        if cmd == "l":
            page = 0
            total_pages = math.ceil(len(fonts) / page_size) if fonts else 1
            while True:
                start = page * page_size
                console.clear()
                console.print(Panel(Text(f"Listing fonts — page {page+1}/{total_pages} (use n/p to navigate, Enter to return)"), title="List"))
                show_fonts_table(fonts, start=start, limit=page_size)
                key = console.input("[bold cyan]list> [/bold cyan]").strip().lower()
                if key in ("n", "next"):
                    if page + 1 < total_pages:
                        page += 1
                    else:
                        console.print("[dim]Already at last page[/dim]")
                elif key in ("p", "prev"):
                    if page > 0:
                        page -= 1
                    else:
                        console.print("[dim]Already at first page[/dim]")
                elif key == "":
                    break
                else:
                    console.print("[red]Unknown command in listing. Use n / p or Enter to return.[/red]")
            show_menu()
            continue

        if cmd == "n":
            # convenience to go to next page from main loop (same behavior as inside listing)
            console.print("[dim]Use 'l' to enter listing mode and then 'n'/'p' to navigate.[/dim]")
            continue

        if cmd == "p":
            console.print("[dim]Use 'l' to enter listing mode and then 'n'/'p' to navigate.[/dim]")
            continue

        if cmd == "s":
            if len(parts) == 2:
                search_term = parts[1].strip()
            else:
                search_term = ""
            refresh_working_set()
            console.print(f"[green]Search term set to:[/green] '{search_term}' — {len(fonts)} matches")
            continue

        if cmd == "f":
            toggle_filters_interactive()
            continue

        if cmd == "t":
            st = compute_stats(fonts)
            print_stats(st)
            continue

        if cmd == "e":
            if len(parts) < 2:
                console.print("[red]Usage: e <output_path>[/red]")
                continue
            path = parts[1].strip()
            try:
                export_fonts(fonts, path)
            except Exception as exc:
                console.print(f"[red]Export failed: {exc}[/red]")
            continue

        console.print("[red]Unknown command. Type 'h' for help.[/red]")


# CLI main
def main():
    parser = argparse.ArgumentParser(description="Font Explorer – list and filter system fonts.")
    parser.add_argument("--mono", action="store_true", help="Show only monospace fonts")
    parser.add_argument("--serif", action="store_true", help="Show only serif fonts")
    parser.add_argument("--sans", action="store_true", help="Show only sans-serif fonts")
    parser.add_argument("--display", action="store_true", help="Show display/decorative fonts")
    parser.add_argument("--symbol", action="store_true", help="Show symbol/emoji fonts")
    parser.add_argument("--search", type=str, help="Search for a font name")
    parser.add_argument("--export", type=str, help="Export font list to file (txt or json)")
    parser.add_argument("--limit", type=int, help="Limit number of fonts shown", default=None)
    parser.add_argument("--stats", action="store_true", help="Show statistics (counts by category)")
    parser.add_argument("--tui", action="store_true", help="Open interactive textual UI")
    args = parser.parse_args()

    fonts = get_all_fonts()
    fonts = attach_classification(fonts)

    if args.tui:
        # TUI works on full set initially; filters/search inside TUI
        run_tui(fonts)
        return

    # non-TUI flow
    fonts = filter_fonts(fonts, args.mono, args.serif, args.sans, args.display, args.symbol)

    if args.search:
        term = args.search.lower()
        fonts = [f for f in fonts if term in f["name"].lower()]

    if args.limit:
        fonts = fonts[: args.limit]

    if not fonts:
        console.print("[red]No fonts found matching your criteria.[/red]")
        sys.exit(0)

    show_fonts_table(fonts)

    if args.stats:
        st = compute_stats(fonts)
        print_stats(st)

    if args.export:
        export_fonts(fonts, args.export)


if __name__ == "__main__":
    main()

